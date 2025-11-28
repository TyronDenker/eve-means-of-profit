"""OAuth callback server for EVE SSO authentication.

This module provides a simple HTTP server to catch OAuth callbacks
during the PKCE authentication flow.
"""

import html
import logging
import queue
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from threading import Event, Thread

logger = logging.getLogger(__name__)


class CallbackHandler(BaseHTTPRequestHandler):
    """HTTP request handler for OAuth callbacks.

    Important: This handler uses class-level shared state to communicate
    callback data. Only ONE authentication flow should be active at a time.
    Concurrent authentication attempts may overwrite each other's data.

    For the single-instance desktop application use case (one app with
    multiple potential characters authenticating sequentially), this design
    is appropriate and simpler than per-flow state management.
    """

    # Shared storage and synchronization primitives for callbacks
    callback_data: dict[str, str] | None = None
    callback_event: Event = Event()
    callback_queue: "queue.Queue[dict[str, str]]" = queue.Queue(1)

    def do_GET(self):
        """Handle GET request (OAuth callback)."""
        # Parse query parameters
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        # Extract code and state
        code = params.get("code", [None])[0]
        state = params.get("state", [None])[0]
        error = params.get("error", [None])[0]

        # Defensive check: warn if a callback arrives while event is already set
        # (indicates potential concurrent authentication attempts)
        if CallbackHandler.callback_event.is_set():
            logger.warning(
                "OAuth callback received while previous callback still pending. "
                "Concurrent authentication flows are not supported and may cause issues."
            )

        # Store callback data in a small queue and signal waiters.
        data = {"code": code, "state": state, "error": error, "url": self.path}
        try:
            # If queue is full, replace the oldest value so the latest callback is kept.
            try:
                CallbackHandler.callback_queue.put_nowait(data)
            except queue.Full:
                try:
                    _ = CallbackHandler.callback_queue.get_nowait()
                except queue.Empty:
                    pass
                CallbackHandler.callback_queue.put_nowait(data)
        finally:
            CallbackHandler.callback_data = data
            CallbackHandler.callback_event.set()

        # Send response to browser
        if error:
            self.send_response(400)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            safe_error = html.escape(error) if error else ""
            html_body = f"""
            <html>
            <head><title>Authentication Failed</title></head>
            <body>
                <h1>Authentication Failed</h1>
                <p>Error: {safe_error}</p>
                <p>You can close this window now.</p>
            </body>
            </html>
            """
            self.wfile.write(html_body.encode())
        else:
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            success_html = """
            <html>
            <head><title>Authentication Success</title></head>
            <body>
                <h1>Authentication Successful!</h1>
                <p>You have successfully authenticated with EVE Online.</p>
                <p>You can close this window and return to the application.</p>
            </body>
            </html>
            """
            self.wfile.write(success_html.encode())

        logger.info(
            "Received OAuth callback: code=%s state=%s",
            "present" if code else "missing",
            state,
        )

    def log_message(self, format, *args):  # noqa: A002
        """Suppress default HTTP server logging."""
        # Route default HTTP server logging through module logger at debug level
        try:
            logger.debug("%s - - %s", self.client_address[0], format % args)
        except Exception:
            # Avoid raising from logging
            logger.debug("HTTP log: %s %s", self.client_address[0], format)


class CallbackServer:
    """OAuth callback server manager.

    Important: Designed for sequential authentication flows in single-instance
    desktop applications. Only one authentication should be active at a time.
    Starting a new server while an old one is running may cause undefined behavior.

    Use the context manager protocol (with statement) or explicitly call start()/stop()
    to manage the server lifecycle.
    """

    def __init__(self, host: str = "localhost", port: int = 8080):
        """Initialize callback server.

        Args:
            host: Host to bind to (default: localhost)
            port: Port to bind to (default: 8080)
        """
        self.host = host
        self.port = port
        self.server: HTTPServer | None = None
        self.thread: Thread | None = None

    def start(self):
        """Start the callback server in a background thread."""
        if self.server:
            logger.warning("Server already running")
            return

        # Reset callback data
        CallbackHandler.callback_data = None
        # Reset synchronization primitives/state
        CallbackHandler.callback_event.clear()
        CallbackHandler.callback_queue = queue.Queue(1)

        # Create and start server (use a threaded server so callbacks don't block)
        try:
            self.server = ThreadingHTTPServer((self.host, self.port), CallbackHandler)
        except OSError as exc:
            logger.error(
                "Failed to start callback server on %s:%s: %s",
                self.host,
                self.port,
                exc,
            )
            self.server = None
            raise

        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

        bound_address = self.server.server_address
        logger.info(
            "OAuth callback server started on http://%s:%s",
            bound_address[0],
            bound_address[1],
        )

    def stop(self):
        """Stop the callback server and wait for thread to complete."""
        if self.server:
            try:
                self.server.shutdown()
                self.server.server_close()
            finally:
                if self.thread:
                    try:
                        # Increased timeout from 1s to 5s for cleaner shutdown
                        # Server should stop quickly after shutdown() call
                        self.thread.join(timeout=5)
                        if self.thread.is_alive():
                            logger.warning(
                                "Callback server thread did not stop within 5 seconds"
                            )
                    except Exception as e:
                        logger.debug("Exception during thread join: %s", e)
                self.server = None
                self.thread = None
                logger.info("OAuth callback server stopped")

    def wait_for_callback(self, timeout: int = 300) -> dict[str, str] | None:
        """Wait for OAuth callback.

        Args:
            timeout: Maximum time to wait in seconds (default: 300)

        Returns:
            Callback data dict with 'code', 'state', 'error', 'url' keys
            or None if timeout reached
        """
        # Wait on the event which is signalled by the handler when a callback arrives.
        signaled = CallbackHandler.callback_event.wait(timeout)
        if not signaled:
            return None

        # Try to get the newest data from the queue, fall back to callback_data
        try:
            data = CallbackHandler.callback_queue.get_nowait()
        except queue.Empty:
            data = CallbackHandler.callback_data

        # Prepare for future waits
        CallbackHandler.callback_event.clear()

        return data

    def get_code(
        self, expected_state: str | None = None, timeout: int = 300
    ) -> str | None:
        """Convenience helper: wait for a callback and return the authorization code.

        If expected_state is provided, the function will verify the returned state
        and return None if it doesn't match.
        """
        data = self.wait_for_callback(timeout=timeout)
        if not data:
            return None
        if expected_state is not None and data.get("state") != expected_state:
            logger.warning(
                "State mismatch in callback: expected=%s received=%s",
                expected_state,
                data.get("state"),
            )
            return None
        return data.get("code")

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()

"""Authentication dialog for adding characters."""

import asyncio
import logging

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QGroupBox,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from qasync import asyncSlot

from services.character_service import CharacterService
from ui.signal_bus import get_signal_bus
from ui.styles import AppStyles
from utils import global_config

logger = logging.getLogger(__name__)


class AuthDialog(QDialog):
    """Dialog for authenticating a new character."""

    def __init__(self, character_service: CharacterService, parent=None):
        """Initialize authentication dialog.

        Args:
            character_service: Service for character operations
            parent: Parent widget
        """
        super().__init__(parent)
        self._service = character_service
        self._signal_bus = get_signal_bus()
        self._checkboxes: dict[str, QCheckBox] = {}

        self.setWindowTitle("Add Character")
        self.setMinimumWidth(500)
        self.setMinimumHeight(600)

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Setup user interface."""
        layout = QVBoxLayout(self)

        # Instructions
        instructions = QLabel(
            "Select the ESI scopes you want to authorize for this character.\n"
            "The selected scopes determine what data the application can access."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        # Scopes section
        scopes_group = QGroupBox("ESI Scopes")
        scopes_group.setStyleSheet(AppStyles.GROUP_BOX)
        scopes_layout = QVBoxLayout(scopes_group)

        # Create scroll area for scopes
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(AppStyles.SCROLL_AREA + AppStyles.SCROLLBAR)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        # Get available scopes from config
        available_scopes = global_config.esi.available_scopes
        default_scopes = global_config.esi.default_scopes

        # Create checkbox for each scope
        for scope, description in available_scopes.items():
            checkbox = QCheckBox(f"{scope}\n{description}")
            checkbox.setChecked(scope in default_scopes)
            checkbox.setStyleSheet(AppStyles.CHECKBOX)
            self._checkboxes[scope] = checkbox
            scroll_layout.addWidget(checkbox)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        scopes_layout.addWidget(scroll)

        layout.addWidget(scopes_group)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self.progress_bar.setStyleSheet(AppStyles.PROGRESS_BAR)
        layout.addWidget(self.progress_bar)

        # Status label
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setVisible(False)
        layout.addWidget(self.status_label)

        # Buttons
        button_layout = QVBoxLayout()

        self.auth_button = QPushButton("Start Authentication")
        self.auth_button.setStyleSheet(AppStyles.BUTTON_PRIMARY)
        self.auth_button.clicked.connect(self._on_auth_clicked)
        button_layout.addWidget(self.auth_button)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setStyleSheet(AppStyles.BUTTON_SECONDARY)
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)

        layout.addLayout(button_layout)

    @asyncSlot()
    async def _on_auth_clicked(self) -> None:
        """Handle authentication button click."""
        # Get selected scopes
        selected_scopes = [
            scope
            for scope, checkbox in self._checkboxes.items()
            if checkbox.isChecked()
        ]

        if not selected_scopes:
            self._signal_bus.error_occurred.emit("Please select at least one scope")
            return

        # Show progress
        self.auth_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.status_label.setVisible(True)
        self.status_label.setText("Opening browser for authentication...")

        self._signal_bus.auth_started.emit()

        try:
            # Get existing characters BEFORE authentication to check for duplicates
            existing_characters = await self._service.get_authenticated_characters(
                use_cache_only=True
            )
            existing_character_ids = {char.character_id for char in existing_characters}

            # Authenticate character
            character_info = await self._service.authenticate_character(selected_scopes)

            # Check if the newly authenticated character is a duplicate of an ALREADY EXISTING character
            # (not a duplicate of itself from the token write)
            if character_info.character_id in existing_character_ids:
                # Show inline warning for duplicate character - DO NOT ADD
                self.status_label.setStyleSheet("color: #FFA500; font-weight: bold;")
                self.status_label.setText(
                    f"⚠ Character '{character_info.character_name}' is already added.\n"
                    f"The existing character's token has been updated. No duplicate created."
                )
                logger.warning(
                    "Duplicate character detected and blocked: %s (ID: %d)",
                    character_info.character_name,
                    character_info.character_id,
                )
                # Emit auth_completed to update token, but NOT character_added
                self._signal_bus.auth_completed.emit(character_info.model_dump())

                # Wait longer to show warning message
                await asyncio.sleep(3)
                self.accept()
                return

            # Success - new character
            self.status_label.setStyleSheet("")
            self.status_label.setText(
                f"Successfully authenticated as {character_info.character_name}"
            )
            self._signal_bus.auth_completed.emit(character_info.model_dump())
            self._signal_bus.character_added.emit(character_info.model_dump())

            # Wait a moment to show success message
            await asyncio.sleep(1)

            self.accept()

        except TimeoutError:
            self.status_label.setStyleSheet("")
            self.status_label.setText("Authentication timeout - please try again")
            self._signal_bus.auth_failed.emit("Authentication timeout")
            logger.warning("Authentication timeout")
        except ValueError as e:
            error_msg = str(e)
            self.status_label.setStyleSheet("")
            if "State mismatch" in error_msg:
                self.status_label.setText(
                    "Authentication failed: Security error (state mismatch)"
                )
            elif "CSRF" in error_msg:
                self.status_label.setText(
                    "Authentication failed: Security error (CSRF detected)"
                )
            elif "OAuth error" in error_msg:
                self.status_label.setText(f"Authentication failed: {error_msg}")
            else:
                self.status_label.setText(f"Authentication failed: {error_msg}")
            self._signal_bus.auth_failed.emit(error_msg)
            logger.error("Authentication failed: %s", error_msg)
        except Exception as e:
            error_msg = f"Authentication error: {e}"
            self.status_label.setStyleSheet("")
            self.status_label.setText(error_msg)
            self._signal_bus.auth_failed.emit(str(e))
            logger.exception("Authentication error")
        finally:
            self.auth_button.setEnabled(True)
            self.progress_bar.setVisible(False)

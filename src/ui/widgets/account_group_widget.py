"""Account group widget for displaying characters grouped by account."""

from __future__ import annotations

# mypy: ignore-errors
# pyright: reportIncompatibleMethodOverride=false
# pyright: reportGeneralTypeIssues=false
import logging
from datetime import UTC, datetime

from PyQt6.QtCore import QEvent, QMimeData, Qt, pyqtSignal
from PyQt6.QtGui import (
    QDrag,
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QMouseEvent,
    QPainter,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ui.styles import COLORS, AppStyles
from utils.settings_manager import get_settings_manager

logger = logging.getLogger(__name__)


def _abbrev(value: int) -> str:
    """Return a human-readable abbreviated string for PLEX counts.

    Shows the full number up to 4 digits; afterwards uses k/m/b suffixes
    with a single decimal place when useful.
    """

    try:
        n = int(value)
    except Exception:
        return str(value)

    if abs(n) < 10_000:
        return str(n)

    thresholds = [
        (1_000_000_000, "b"),
        (1_000_000, "m"),
        (1_000, "k"),
    ]
    for thresh, suffix in thresholds:
        if abs(n) >= thresh:
            short = n / thresh
            # Avoid trailing .0 for whole numbers
            return f"{short:.1f}{suffix}" if short % 1 else f"{int(short)}{suffix}"
    return str(n)


class ModifierAwarePushButton(QPushButton):
    """Push button that captures modifier keys on click for more reliable detection.

    This button class emits two signals:
    - clicked: Standard clicked signal (inherited)
    - modifier_clicked: Custom signal with (modifiers: Qt.KeyboardModifiers)
    """

    modifier_clicked = pyqtSignal(object)  # Emits Qt.KeyboardModifiers

    def mousePressEvent(self, event):  # type: ignore[override]  # noqa: N802
        """Capture the modifier state at the moment of click."""
        modifiers = event.modifiers()
        # Emit custom signal with modifiers
        self.modifier_clicked.emit(modifiers)
        # Let the normal click handling proceed
        super().mousePressEvent(event)


class PlexSpinBox(QSpinBox):
    """Spinbox with compact width and abbreviated display for large values."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Keep wheel steps small but allow big numbers
        self.setMinimum(0)
        self.setMaximum(10_000_000)
        # Remove built-in arrow buttons to avoid duplicate controls; rely on +/-
        try:
            self.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        except Exception:
            pass
        self._force_full_display = False

    def focusInEvent(self, event):  # type: ignore[override]  # noqa: N802
        self._force_full_display = True
        super().focusInEvent(event)
        try:
            self.lineEdit().selectAll()
        except Exception:
            pass
        self.update()

    def focusOutEvent(self, event):  # type: ignore[override]  # noqa: N802
        super().focusOutEvent(event)
        self._force_full_display = False
        self.update()

    def textFromValue(self, value: int) -> str:  # type: ignore[override]  # noqa: N802
        # Show the full number while focused/editing; otherwise show abbreviated
        if self._force_full_display or self.hasFocus():
            return str(value)
        return _abbrev(value)

    def valueFromText(self, text: str) -> int:  # type: ignore[override]  # noqa: N802
        # Accept raw ints or abbreviated suffixes
        try:
            cleaned = text.strip().lower()
            if cleaned.endswith("k"):
                return int(float(cleaned[:-1]) * 1_000)
            if cleaned.endswith("m"):
                return int(float(cleaned[:-1]) * 1_000_000)
            if cleaned.endswith("b"):
                return int(float(cleaned[:-1]) * 1_000_000_000)
            return int(float(cleaned))
        except Exception:
            return self.value()


class CharacterCard(QFrame):
    """Individual draggable character card."""

    clicked = pyqtSignal(int)  # Emits character_id
    context_menu_requested = pyqtSignal(int, object)  # character_id, global_pos

    def __init__(self, character_id: int, character_widget: QWidget, parent=None):
        super().__init__(parent)
        self.character_id = character_id
        self.character_widget = character_widget

        # Enable context menu
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)

        # Basic styling using unified AppStyles
        self.setFrameStyle(QFrame.Shape.Box)
        self.setLineWidth(1)
        self.setStyleSheet(AppStyles.CHARACTER_CARD)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.addWidget(character_widget)

        # Use sizeHint for initial sizing and keep a fixed horizontal width so
        # that the account group layout maintains consistent columns.
        size_hint = character_widget.sizeHint()
        self.setMinimumHeight(size_hint.height())
        # Use Fixed horizontal policy so cards do not expand unpredictably.
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        try:
            # Allow wider cards when networth is visible (up to 480px for full content)
            # Use the actual size hint width, capped at 480, without a minimum floor
            # to allow tight wrapping when networth is hidden.
            bounded_width = min(size_hint.width(), 480)
            self.setMinimumWidth(bounded_width)
            self.setMaximumWidth(bounded_width)
        except Exception:
            self.setMaximumWidth(480)

    def update_size_constraints(self) -> None:
        """Update card size constraints based on the inner widget's current size hint.

        Call this after the inner widget's content changes (e.g., networth visibility toggle).
        """
        size_hint = self.character_widget.sizeHint()
        self.setMinimumHeight(size_hint.height())
        try:
            # Use the actual size hint width, capped at 480, without a minimum floor
            bounded_width = min(size_hint.width(), 480)
            self.setMinimumWidth(bounded_width)
            self.setMaximumWidth(bounded_width)
        except Exception:
            self.setMaximumWidth(480)
        self.updateGeometry()

    def _on_context_menu(self, pos):
        """Handle context menu request."""
        global_pos = self.mapToGlobal(pos)
        self.context_menu_requested.emit(self.character_id, global_pos)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]  # noqa: N802
        """Handle mouse press for drag initiation."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]  # noqa: N802
        """Initiate drag operation."""
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if (event.pos() - self._drag_start_pos).manhattanLength() < 10:
            return

        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setText(str(self.character_id))
        mime_data.setData("application/x-character-id", str(self.character_id).encode())
        drag.setMimeData(mime_data)

        # Create drag pixmap
        pixmap = QPixmap(self.size())
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setOpacity(0.7)
        self.render(painter)
        painter.end()
        drag.setPixmap(pixmap)
        drag.setHotSpot(event.pos())

        drag.exec(Qt.DropAction.MoveAction)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]  # noqa: N802
        """Handle click for selection."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.character_id)
        super().mouseReleaseEvent(event)


class EmptyAccountWidget(QFrame):
    """Compact widget for empty accounts (no characters assigned)."""

    character_dropped = pyqtSignal(int, object)  # character_id, target_account_id
    account_refresh_requested = pyqtSignal(object)  # account_id

    def __init__(
        self,
        account_id: int,
        account_name: str,
        plex_units: int = 0,
        parent=None,
    ):
        super().__init__(parent)
        self.account_id = account_id
        self.account_name = account_name
        self.plex_units = plex_units
        self.character_cards: list[
            CharacterCard
        ] = []  # Always empty but needed for compatibility

        # Enable drops
        self.setAcceptDrops(True)

        # Compact styling
        self.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)
        self.setLineWidth(1)
        self.setStyleSheet(f"""
            EmptyAccountWidget {{
                background-color: {COLORS.BG_DARK};
                border: 1px solid {COLORS.BORDER_DARK};
                border-radius: 4px;
                padding: 4px;
            }}
            EmptyAccountWidget:hover {{
                border: 1px solid {COLORS.PRIMARY};
                background-color: {COLORS.BG_MEDIUM};
            }}
        """)

        # Single row horizontal layout for compact display
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(6, 4, 6, 4)
        main_layout.setSpacing(8)

        # Account name
        account_label = QLabel(f"<b>{account_name}</b>")
        account_label.setStyleSheet(f"font-size: 12px; color: {COLORS.TEXT_SECONDARY};")
        main_layout.addWidget(account_label)

        # PLEX display with inline editing (hidden until focus/hover)
        settings_mgr = get_settings_manager()
        plex_update_time = settings_mgr.get_account_plex_update_time(account_id)

        plex_text = QLabel("PLEX:")
        plex_text.setStyleSheet(f"font-size: 11px; color: {COLORS.TEXT_MUTED};")
        main_layout.addWidget(plex_text)

        # Wrapper so we can toggle editable controls on hover/focus
        self._plex_container = QWidget()
        container_layout = QHBoxLayout(self._plex_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(2)

        self._plex_display = QLabel(_abbrev(plex_units))
        self._plex_display.setStyleSheet(
            f"font-size: 11px; color: #ddd; padding: 0 2px; border-bottom: 1px dashed {COLORS.BORDER_MEDIUM};"
        )
        self._plex_display.setCursor(Qt.CursorShape.PointingHandCursor)
        self._plex_display.setToolTip(
            "Click to edit PLEX amount. Use +/- buttons with modifiers: Shift=±10, Ctrl=±100, Ctrl+Shift=±500."
        )
        container_layout.addWidget(self._plex_display)

        self._plex_minus_btn = ModifierAwarePushButton("-")
        self._plex_minus_btn.setFixedSize(20, 20)
        self._plex_minus_btn.setToolTip(
            "Decrease PLEX: -1 (Shift: -10, Ctrl: -100, Ctrl+Shift: -500)"
        )
        self._plex_minus_btn.setStyleSheet(AppStyles.BUTTON_PLEX_MINUS)
        self._plex_minus_btn.clicked.connect(lambda: self._nudge_plex_simple(-1))
        self._plex_minus_btn.hide()
        container_layout.addWidget(self._plex_minus_btn)

        self.plex_spinbox = PlexSpinBox()
        self.plex_spinbox.setKeyboardTracking(False)
        self.plex_spinbox.setValue(plex_units)
        self.plex_spinbox.setToolTip(
            "Edit PLEX vault amount (Ctrl: ±10, Shift: ±100). Full value shown while typing."
        )
        self.plex_spinbox.setStyleSheet(AppStyles.SPINBOX)
        self.plex_spinbox.hide()
        self.plex_spinbox.installEventFilter(self)
        self.plex_spinbox.editingFinished.connect(self._on_plex_changed)
        self.plex_spinbox.valueChanged.connect(self._update_plex_display_text)
        container_layout.addWidget(self.plex_spinbox)

        self._plex_plus_btn = ModifierAwarePushButton("+")
        self._plex_plus_btn.setFixedSize(20, 20)
        self._plex_plus_btn.setToolTip(
            "Increase PLEX: +1 (Shift: +10, Ctrl: +100, Ctrl+Shift: +500)"
        )
        self._plex_plus_btn.setStyleSheet(AppStyles.BUTTON_PLEX_PLUS)
        self._plex_plus_btn.clicked.connect(lambda: self._nudge_plex_simple(1))
        self._plex_plus_btn.hide()
        container_layout.addWidget(self._plex_plus_btn)

        self._plex_hint = QLabel("Shift=±10  Ctrl=±100  Ctrl+Shift=±500")
        self._plex_hint.setStyleSheet(f"color: {COLORS.TEXT_MUTED}; font-size: 9px;")
        self._plex_hint.hide()
        container_layout.addWidget(self._plex_hint)

        self._plex_container.setToolTip(
            "PLEX total. Click to edit; hold Shift/Ctrl/Ctrl+Shift when using +/- for larger steps."
        )
        self._plex_container.installEventFilter(self)
        self._plex_display.mousePressEvent = lambda evt: self._show_plex_editor()
        main_layout.addWidget(self._plex_container)

        # Timestamp (compact)
        self.timestamp_label = QLabel()
        self._update_timestamp_display(plex_update_time)
        main_layout.addWidget(self.timestamp_label)

        main_layout.addStretch()

        # Refresh button (smaller)
        refresh_btn = QPushButton("↻")
        refresh_btn.setFixedSize(24, 24)
        refresh_btn.setToolTip("Refresh Account")
        refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS.PRIMARY};
                color: white;
                border: none;
                border-radius: 12px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {COLORS.PRIMARY_HOVER};
            }}
        """)
        refresh_btn.clicked.connect(
            lambda: self.account_refresh_requested.emit(self.account_id)
        )
        main_layout.addWidget(refresh_btn)

        # Compact size
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setMaximumHeight(40)

    # --- PLEX UI helpers -------------------------------------------------
    def _show_plex_editor(self):
        self._plex_display.hide()
        self.plex_spinbox.show()
        self._plex_minus_btn.show()
        self._plex_plus_btn.show()
        self._plex_hint.show()
        self._plex_editor_active = True
        try:
            self.plex_spinbox.setFocus()
            self.plex_spinbox.selectAll()
        except Exception:
            pass

    def _hide_plex_editor(self):
        # Only hide if focus is outside both spinbox and +/- buttons
        if self.plex_spinbox.hasFocus():
            return
        if self._plex_minus_btn.hasFocus() or self._plex_plus_btn.hasFocus():
            return
        self._plex_editor_active = False
        self.plex_spinbox.hide()
        self._plex_minus_btn.hide()
        self._plex_plus_btn.hide()
        self._plex_hint.hide()
        self._update_plex_display_text()
        self._plex_display.show()

    def _update_plex_display_text(self, value: int | None = None) -> None:
        val = value if value is not None else self.plex_spinbox.value()
        text = str(val) if self.plex_spinbox.hasFocus() else _abbrev(val)
        self._plex_display.setText(text)

    def _persist_plex_value(self, new_value: int) -> None:
        settings = get_settings_manager()
        settings.set_account_plex_units(self.account_id, new_value)
        timestamp = datetime.now(UTC).isoformat()
        settings.set_account_plex_update_time(self.account_id, timestamp)
        self.plex_units = new_value
        self._update_timestamp_display(timestamp)
        self._update_plex_display_text(new_value)

    def _nudge_plex_simple(self, direction: int) -> None:
        """Handle PLEX nudge using QApplication.keyboardModifiers() at click time.

        Args:
            direction: -1 for decrease, +1 for increase
        """
        step = 1
        # Read modifiers from QGuiApplication at the moment of click
        try:
            from PyQt6.QtWidgets import QApplication

            mods = QApplication.keyboardModifiers()
            ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
            shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
            if ctrl and shift:
                step = 500
            elif ctrl:
                step = 100
            elif shift:
                step = 10
        except Exception:
            logger.debug("Failed to read keyboard modifiers", exc_info=True)
            step = 1

        delta = step * direction
        new_val = max(0, self.plex_spinbox.value() + delta)
        if new_val == self.plex_units:
            self.plex_spinbox.setValue(new_val)
            self._update_plex_display_text(new_val)
            return
        self.plex_spinbox.setValue(new_val)
        self._persist_plex_value(new_val)
        # Keep focus on spinbox so editor doesn't close
        try:
            self.plex_spinbox.setFocus()
        except Exception:
            pass

    def eventFilter(self, obj, event):  # noqa: N802
        if obj in (self._plex_container, self.plex_spinbox):
            if event.type() == QEvent.Type.Leave:
                # Delay hide check to allow button clicks to maintain focus
                from PyQt6.QtCore import QTimer

                QTimer.singleShot(50, self._check_and_hide_plex_editor)
        return super().eventFilter(obj, event)

    def _check_and_hide_plex_editor(self) -> None:
        """Check if editor should be hidden after a delay."""
        if not getattr(self, "_plex_editor_active", False):
            return
        if self.plex_spinbox.hasFocus():
            return
        if self._plex_minus_btn.hasFocus() or self._plex_plus_btn.hasFocus():
            return
        self._hide_plex_editor()

    def _update_timestamp_display(self, plex_update_time: str | None) -> None:
        """Update the timestamp label with formatted time."""
        if plex_update_time:
            try:
                dt = datetime.fromisoformat(plex_update_time)
                timestamp_str = dt.strftime("%m/%d %H:%M")
            except Exception:
                timestamp_str = ""
            self.timestamp_label.setText(f"({timestamp_str})")
            self.timestamp_label.setStyleSheet(
                f"font-size: 9px; color: {COLORS.TEXT_DISABLED};"
            )
        else:
            self.timestamp_label.setText("")

    def _on_plex_changed(self) -> None:
        """Handle PLEX spinbox value change."""
        new_value = self.plex_spinbox.value()
        if new_value != self.plex_units:
            self._persist_plex_value(new_value)
        # Always collapse back to display mode even if unchanged
        self._hide_plex_editor()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # type: ignore[override]  # noqa: N802
        """Accept drag enter if it's a character."""
        mime = event.mimeData()
        if mime is not None and mime.hasFormat("application/x-character-id"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:  # type: ignore[override]  # noqa: N802
        """Accept drag move."""
        mime = event.mimeData()
        if mime is not None and mime.hasFormat("application/x-character-id"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:  # type: ignore[override]  # noqa: N802
        """Handle character drop."""
        mime = event.mimeData()
        if mime is not None and mime.hasFormat("application/x-character-id"):
            char_id_bytes = mime.data("application/x-character-id")
            try:
                character_id = int(char_id_bytes.data().decode())
                self.character_dropped.emit(character_id, self.account_id)
                event.acceptProposedAction()
            except Exception:
                logger.exception("Failed to parse dropped character ID")
                event.ignore()
        else:
            event.ignore()


class AccountGroupWidget(QFrame):
    """Widget displaying an account with its characters."""

    character_dropped = pyqtSignal(int, object)  # character_id, target_account_id
    character_reordered = pyqtSignal(object, list)  # account_id, new_order_list
    character_clicked = pyqtSignal(int)  # character_id
    character_context_menu = pyqtSignal(int, object)  # character_id, global_pos
    account_refresh_requested = pyqtSignal(object)  # account_id

    def __init__(
        self,
        account_id: int | None,
        account_name: str,
        plex_units: int = 0,
        parent=None,
    ):
        super().__init__(parent)
        self.account_id = account_id
        self.account_name = account_name
        self.plex_units = plex_units
        self.character_cards: list[CharacterCard] = []

        # Enable drops
        self.setAcceptDrops(True)

        # Styling for group box using unified AppStyles
        self.setFrameStyle(QFrame.Shape.StyledPanel | QFrame.Shadow.Raised)
        self.setLineWidth(2)
        self.setStyleSheet(AppStyles.ACCOUNT_GROUP)

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(2, 2, 2, 2)
        main_layout.setSpacing(2)

        # Header with account name, PLEX, and refresh button
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        account_label = QLabel(f"<b>{account_name}</b>")
        account_label.setStyleSheet(f"font-size: 14px; color: {COLORS.TEXT_PRIMARY};")
        header_layout.addWidget(account_label)

        if account_id is not None:
            # PLEX section: click-to-edit spinbox + timestamp
            settings_mgr = get_settings_manager()
            plex_update_time = settings_mgr.get_account_plex_update_time(account_id)

            # PLEX label
            plex_text_label = QLabel("PLEX:")
            plex_text_label.setStyleSheet(
                f"font-size: 12px; color: {COLORS.TEXT_MUTED};"
            )
            header_layout.addWidget(plex_text_label)

            # Wrapper controls
            self._plex_container = QWidget()
            plex_layout = QHBoxLayout(self._plex_container)
            plex_layout.setContentsMargins(0, 0, 0, 0)
            plex_layout.setSpacing(2)

            self._plex_display = QLabel(_abbrev(plex_units))
            self._plex_display.setStyleSheet(
                f"font-size: 12px; color: #ddd; padding: 0 3px; border-bottom: 1px dashed {COLORS.BORDER_LIGHT};"
            )
            self._plex_display.setCursor(Qt.CursorShape.PointingHandCursor)
            self._plex_display.setToolTip(
                "Click to edit PLEX amount. Use +/- buttons with modifiers: Shift=±10, Ctrl=±100, Ctrl+Shift=±500."
            )
            plex_layout.addWidget(self._plex_display)

            self._plex_minus_btn = ModifierAwarePushButton("-")
            self._plex_minus_btn.setFixedSize(20, 20)
            self._plex_minus_btn.setToolTip(
                "Decrease PLEX: -1 (Shift: -10, Ctrl: -100, Ctrl+Shift: -500)"
            )
            self._plex_minus_btn.setStyleSheet(AppStyles.BUTTON_PLEX_MINUS)
            self._plex_minus_btn.clicked.connect(lambda: self._nudge_plex_simple(-1))
            self._plex_minus_btn.hide()
            plex_layout.addWidget(self._plex_minus_btn)

            self.plex_spinbox = PlexSpinBox()
            self.plex_spinbox.setKeyboardTracking(False)
            self.plex_spinbox.setValue(plex_units)
            self.plex_spinbox.setToolTip(
                "Edit PLEX vault amount (Ctrl: ±10, Shift: ±100). Full value while typing."
            )
            self.plex_spinbox.setStyleSheet(AppStyles.SPINBOX)
            self.plex_spinbox.hide()
            self.plex_spinbox.installEventFilter(self)
            self.plex_spinbox.editingFinished.connect(self._on_plex_changed)
            self.plex_spinbox.valueChanged.connect(self._update_plex_display_text)
            plex_layout.addWidget(self.plex_spinbox)

            self._plex_plus_btn = ModifierAwarePushButton("+")
            self._plex_plus_btn.setFixedSize(20, 20)
            self._plex_plus_btn.setToolTip(
                "Increase PLEX: +1 (Shift: +10, Ctrl: +100, Ctrl+Shift: +500)"
            )
            self._plex_plus_btn.setStyleSheet(AppStyles.BUTTON_PLEX_PLUS)
            self._plex_plus_btn.clicked.connect(lambda: self._nudge_plex_simple(1))
            self._plex_plus_btn.hide()
            plex_layout.addWidget(self._plex_plus_btn)

            self._plex_hint = QLabel("Shift=±10  Ctrl=±100  Ctrl+Shift=±500")
            self._plex_hint.setStyleSheet(
                f"color: {COLORS.TEXT_MUTED}; font-size: 10px;"
            )
            self._plex_hint.hide()
            plex_layout.addWidget(self._plex_hint)

            self._plex_container.setToolTip(
                "PLEX total. Click to edit; hold Shift/Ctrl/Ctrl+Shift when using +/- for larger steps."
            )
            self._plex_container.installEventFilter(self)
            self._plex_display.mousePressEvent = lambda evt: self._show_plex_editor()
            header_layout.addWidget(self._plex_container)

            # Store references
            self.account_id = account_id
            self.plex_value = plex_units

            # Update timestamp label
            self.timestamp_label = QLabel()
            self._update_timestamp_display(plex_update_time)
            header_layout.addWidget(self.timestamp_label)

        header_layout.addStretch()

        # Refresh button for this account
        refresh_btn = QPushButton("↻ Refresh Account")
        refresh_btn.setMaximumWidth(140)
        refresh_btn.setStyleSheet(AppStyles.BUTTON_PRIMARY)
        refresh_btn.clicked.connect(
            lambda: self.account_refresh_requested.emit(self.account_id)
        )
        header_layout.addWidget(refresh_btn)

        main_layout.addLayout(header_layout)

        # Characters container with single-row layout
        self.characters_container = QWidget()
        self.characters_layout = QHBoxLayout(self.characters_container)
        self.characters_layout.setContentsMargins(0, 0, 0, 0)
        self.characters_layout.setSpacing(1)
        self.characters_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        # Maximum horizontally so the container does not aggressively expand
        # and stretch card cells; keep vertical expansion allowed.
        self.characters_container.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.MinimumExpanding
        )

        main_layout.addWidget(self.characters_container)

        # Set size policy - Maximum allows the group to shrink naturally
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)

    def _update_timestamp_display(self, plex_update_time: str | None) -> None:
        """Update the timestamp label with formatted time (e.g., '5m ago')."""
        if not hasattr(self, "timestamp_label"):
            return

        if not plex_update_time:
            self.timestamp_label.setText("")
            return

        try:
            dt = datetime.fromisoformat(plex_update_time)
            now = datetime.now(UTC)
            delta = now - dt
            if delta.days >= 365:
                ago = f"{delta.days // 365}y"
            elif delta.days >= 30:
                ago = f"{delta.days // 30}mo"
            elif delta.days >= 1:
                ago = f"{delta.days}d"
            elif delta.seconds >= 3600:
                ago = f"{delta.seconds // 3600}h"
            elif delta.seconds >= 60:
                ago = f"{delta.seconds // 60}m"
            else:
                ago = f"{delta.seconds}s"
            timestamp_str = f"{ago} ago"

        except Exception:
            timestamp_str = ""

        self.timestamp_label.setText(f"(updated: {timestamp_str})")
        self.timestamp_label.setStyleSheet(
            f"font-size: 10px; color: {COLORS.TEXT_DISABLED};"
        )

    # --- PLEX UI helpers -------------------------------------------------
    def _show_plex_editor(self) -> None:
        if not hasattr(self, "plex_spinbox"):
            return
        self._plex_display.hide()
        self.plex_spinbox.show()
        self._plex_minus_btn.show()
        self._plex_plus_btn.show()
        if hasattr(self, "_plex_hint"):
            self._plex_hint.show()
        self._plex_editor_active = True
        try:
            self.plex_spinbox.setFocus()
            self.plex_spinbox.selectAll()
        except Exception:
            pass

    def _hide_plex_editor(self) -> None:
        if not hasattr(self, "plex_spinbox"):
            return
        # Only hide if focus is outside both spinbox and +/- buttons
        if self.plex_spinbox.hasFocus():
            return
        if self._plex_minus_btn.hasFocus() or self._plex_plus_btn.hasFocus():
            return
        self._plex_editor_active = False
        self.plex_spinbox.hide()
        self._plex_minus_btn.hide()
        self._plex_plus_btn.hide()
        if hasattr(self, "_plex_hint"):
            self._plex_hint.hide()
        self._update_plex_display_text()
        self._plex_display.show()

    def _update_plex_display_text(self, value: int | None = None) -> None:
        if not hasattr(self, "plex_spinbox"):
            return
        val = value if value is not None else self.plex_spinbox.value()
        text = str(val) if self.plex_spinbox.hasFocus() else _abbrev(val)
        self._plex_display.setText(text)

    def _persist_plex_value(self, new_value: int) -> None:
        if not hasattr(self, "account_id") or self.account_id is None:
            return
        settings = get_settings_manager()
        account_id_int = int(self.account_id)
        settings.set_account_plex_units(account_id_int, new_value)
        timestamp = datetime.now(UTC).isoformat()
        settings.set_account_plex_update_time(account_id_int, timestamp)
        self.plex_value = new_value
        self._update_timestamp_display(timestamp)
        self._update_plex_display_text(new_value)

    def _nudge_plex_simple(self, direction: int) -> None:
        """Handle PLEX nudge using QApplication.keyboardModifiers() at click time.

        Args:
            direction: -1 for decrease, +1 for increase
        """
        if not hasattr(self, "plex_spinbox"):
            return

        step = 1
        # Read modifiers from QGuiApplication at the moment of click
        try:
            from PyQt6.QtWidgets import QApplication

            mods = QApplication.keyboardModifiers()
            ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
            shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
            if ctrl and shift:
                step = 500
            elif ctrl:
                step = 100
            elif shift:
                step = 10
        except Exception:
            logger.debug("Failed to read keyboard modifiers", exc_info=True)
            step = 1

        delta = step * direction
        new_val = max(0, self.plex_spinbox.value() + delta)
        if new_val == getattr(self, "plex_value", None):
            self.plex_spinbox.setValue(new_val)
            self._update_plex_display_text(new_val)
            return
        self.plex_spinbox.setValue(new_val)
        self._persist_plex_value(new_val)
        # Keep focus on spinbox so editor doesn't close
        try:
            self.plex_spinbox.setFocus()
        except Exception:
            pass

    def eventFilter(self, obj, event):  # noqa: N802
        if hasattr(self, "_plex_container") and obj in (
            self._plex_container,
            getattr(self, "plex_spinbox", None),
        ):
            if event.type() == QEvent.Type.Leave:
                # Delay hide check to allow button clicks to maintain focus
                from PyQt6.QtCore import QTimer

                QTimer.singleShot(50, self._check_and_hide_plex_editor)
        return super().eventFilter(obj, event)

    def _check_and_hide_plex_editor(self) -> None:
        """Check if editor should be hidden after a delay."""
        if not hasattr(self, "plex_spinbox"):
            return
        if not getattr(self, "_plex_editor_active", False):
            return
        if self.plex_spinbox.hasFocus():
            return
        if self._plex_minus_btn.hasFocus() or self._plex_plus_btn.hasFocus():
            return
        self._hide_plex_editor()

    def _on_plex_changed(self) -> None:
        """Handle PLEX spinbox value change - save immediately."""
        if not hasattr(self, "account_id") or self.account_id is None:
            return
        if not hasattr(self, "plex_spinbox"):
            return

        new_value = self.plex_spinbox.value()
        if new_value != self.plex_value:
            self._persist_plex_value(new_value)
        # Always collapse editor after leaving
        self._hide_plex_editor()

    def add_character(self, character_id: int, character_widget: QWidget):
        """Add a character card to this group."""
        card = CharacterCard(character_id, character_widget, self)
        card.clicked.connect(self.character_clicked.emit)
        card.context_menu_requested.connect(self.character_context_menu.emit)
        self.character_cards.append(card)
        self._relayout()

    def remove_character(self, character_id: int):
        """Remove a character card from this group."""
        for card in list(self.character_cards):
            if card.character_id == character_id:
                self._remove_card_widget(card)
                card.deleteLater()
                break

    def clear_characters(self):
        """Remove all character cards."""
        for card in list(self.character_cards):
            self._remove_card_widget(card)
            card.deleteLater()
        self.character_cards.clear()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # type: ignore[override]  # noqa: N802
        """Accept drag enter if it's a character."""
        mime = event.mimeData()
        if mime is not None and mime.hasFormat("application/x-character-id"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:  # type: ignore[override]  # noqa: N802
        """Accept drag move."""
        mime = event.mimeData()
        if mime is not None and mime.hasFormat("application/x-character-id"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:  # type: ignore[override]  # noqa: N802
        """Handle character drop - supports both reassignment and reordering."""
        mime = event.mimeData()
        if mime is not None and mime.hasFormat("application/x-character-id"):
            char_id_bytes = mime.data("application/x-character-id")
            try:
                character_id = int(char_id_bytes.data().decode())

                # Check if this is a reorder (character already in this account)
                is_reorder = any(
                    card.character_id == character_id for card in self.character_cards
                )

                if is_reorder and self.account_id is not None:
                    # Handle reordering within the same account
                    # Find the drop position
                    drop_pos = (
                        event.position().toPoint()
                        if hasattr(event.position(), "toPoint")
                        else event.pos()
                    )

                    # Find which card we're dropping near
                    target_index = len(self.character_cards)  # Default to end
                    for i, card in enumerate(self.character_cards):
                        card_center = card.geometry().center()
                        if drop_pos.x() < card_center.x():
                            target_index = i
                            break

                    # Move the card in the list
                    current_index = next(
                        i
                        for i, card in enumerate(self.character_cards)
                        if card.character_id == character_id
                    )

                    if current_index != target_index:
                        # Reorder the list
                        card = self.character_cards.pop(current_index)
                        # Adjust target if we removed from before it
                        if current_index < target_index:
                            target_index -= 1
                        self.character_cards.insert(target_index, card)

                        # Relayout and emit signal
                        self._relayout()
                        new_order = [card.character_id for card in self.character_cards]
                        self.character_reordered.emit(self.account_id, new_order)

                    event.acceptProposedAction()
                else:
                    # Handle moving to different account
                    self.character_dropped.emit(character_id, self.account_id)
                    event.acceptProposedAction()
            except Exception:
                logger.exception("Failed to handle character drop")
                event.ignore()
        else:
            event.ignore()

    def _remove_card_widget(self, card: CharacterCard) -> None:
        try:
            if card in self.character_cards:
                self.character_cards.remove(card)
        except Exception:
            logger.debug("Card removal bookkeeping failed", exc_info=True)
        try:
            self.characters_layout.removeWidget(card)
        except Exception:
            logger.debug("Failed to detach card widget from layout", exc_info=True)
        card.setParent(None)
        card.hide()
        self._relayout()

    def _relayout(self) -> None:
        """Arrange character cards in a single horizontal row."""
        try:
            while self.characters_layout.count():
                item = self.characters_layout.takeAt(0)
                widget = item.widget() if item is not None else None
                if widget is not None:
                    widget.setParent(self.characters_container)

            for card in self.character_cards:
                self.characters_layout.addWidget(card)
            try:
                self.characters_container.updateGeometry()
                self.characters_container.adjustSize()
            except Exception:
                pass
            try:
                self.updateGeometry()
            except Exception:
                pass
        except Exception:
            logger.debug("Failed to relayout account group", exc_info=True)

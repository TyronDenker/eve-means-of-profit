from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

if TYPE_CHECKING:
    from PyQt6.QtGui import QCloseEvent

from ui.signal_bus import get_signal_bus
from ui.styles import COLORS, AppStyles
from utils.settings_manager import get_settings_manager

logger = logging.getLogger(__name__)


class AccountManagerDialog(QDialog):
    """Simple manager for user-defined accounts and PLEX vault units.

    - Create/update account name
    - Set account PLEX units (vault)
    - Delete accounts
    - Assign selected character to an account (enforces max 3 per account)
    """

    def __init__(
        self,
        parent=None,
        character_id: int | None = None,
        character_names: dict[int, str] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Manage Accounts & PLEX Vault")
        self.resize(550, 450)
        self._settings = get_settings_manager()
        self._signal_bus = get_signal_bus()
        self._character_id = character_id
        self._character_names = character_names or {}
        self._changes_made = False

        main = QVBoxLayout(self)

        # Account list
        self.account_list = QListWidget()
        self.account_list.setStyleSheet(AppStyles.LIST_WIDGET + AppStyles.SCROLLBAR)
        main.addWidget(self.account_list)

        # Form to edit selected account
        form = QFormLayout()
        self.txt_account_id = QLineEdit()
        self.txt_account_id.setPlaceholderText("Leave blank to auto-assign next ID")
        self.txt_account_name = QLineEdit()
        self.txt_account_name.setPlaceholderText("Account name (optional)")
        self.spin_plex_units = QSpinBox()
        self.spin_plex_units.setRange(0, 10_000_000)
        self.spin_plex_units.setToolTip("PLEX units stored in vault for this account")
        form.addRow("Account ID", self.txt_account_id)
        form.addRow("Name", self.txt_account_name)
        form.addRow("PLEX Units", self.spin_plex_units)
        main.addLayout(form)

        # Main action buttons
        buttons_layout = QHBoxLayout()

        self.btn_new_account = QPushButton("+ New Account")
        self.btn_new_account.setStyleSheet(AppStyles.BUTTON_PRIMARY)
        buttons_layout.addWidget(self.btn_new_account)

        self.btn_save_account = QPushButton("Save Account")
        self.btn_save_account.setStyleSheet(AppStyles.BUTTON_SECONDARY)
        buttons_layout.addWidget(self.btn_save_account)

        self.btn_delete_account = QPushButton("Delete Account")
        self.btn_delete_account.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS.ERROR};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
            }}
            QPushButton:hover {{ background-color: {COLORS.ERROR_HOVER}; }}
            QPushButton:pressed {{ background-color: #a03030; }}
        """)
        buttons_layout.addWidget(self.btn_delete_account)

        main.addLayout(buttons_layout)

        # Character assignment row (only if character_id provided)
        if self._character_id is not None:
            assign_layout = QHBoxLayout()
            char_name = self._character_names.get(
                self._character_id, str(self._character_id)
            )
            self.btn_assign_character = QPushButton(
                f"Assign '{char_name}' to Selected Account"
            )
            self.btn_assign_character.setStyleSheet(AppStyles.BUTTON_WARNING)
            assign_layout.addWidget(self.btn_assign_character)
            main.addLayout(assign_layout)

        # Close
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.button_box.rejected.connect(self._on_close)
        main.addWidget(self.button_box)

        self._wire()
        self._load_accounts()

    def _wire(self) -> None:
        self.btn_new_account.clicked.connect(self._on_new_account)
        self.btn_save_account.clicked.connect(self._on_save_account)
        self.btn_delete_account.clicked.connect(self._on_delete_account)
        if hasattr(self, "btn_assign_character"):
            self.btn_assign_character.clicked.connect(self._on_assign_character)
        self.account_list.itemSelectionChanged.connect(self._on_account_selected)

    def _load_accounts(self) -> None:
        try:
            self.account_list.clear()
            accounts = self._settings.get_accounts()
            for acc_id, acc in sorted(accounts.items()):
                # Render character names instead of IDs when available
                chars = [int(x) for x in acc.get("characters", [])]
                char_names = [self._character_names.get(cid, str(cid)) for cid in chars]
                acc_name = acc.get("name") or f"Account {acc_id}"
                char_str = ", ".join(char_names) if char_names else "(empty)"
                item = QListWidgetItem(
                    f"{acc_id} - {acc_name} | PLEX: {acc.get('plex_units', 0)} | Chars: {char_str}"
                )
                item.setData(Qt.ItemDataRole.UserRole, acc_id)
                self.account_list.addItem(item)
        except Exception:
            logger.exception("Failed to load accounts")

    def _on_account_selected(self) -> None:
        item = self.account_list.currentItem()
        if not item:
            return
        acc_id = int(item.data(Qt.ItemDataRole.UserRole))
        acc = self._settings.get_accounts().get(acc_id, {})
        self.txt_account_id.setText(str(acc_id))
        self.txt_account_name.setText(acc.get("name") or "")
        self.spin_plex_units.setValue(int(acc.get("plex_units", 0)))

    def _on_new_account(self) -> None:
        """Clear form for new account entry."""
        self.txt_account_id.clear()
        self.txt_account_name.clear()
        self.spin_plex_units.setValue(0)
        self.account_list.clearSelection()

    def _on_save_account(self) -> None:
        try:
            acc_id_text = self.txt_account_id.text().strip()
            if not acc_id_text:
                # Auto-assign next available account id
                existing = sorted(self._settings.get_accounts().keys())
                acc_id = (existing[-1] + 1) if existing else 0
            elif acc_id_text.isdigit():
                acc_id = int(acc_id_text)
            else:
                QMessageBox.warning(self, "Invalid ID", "Account ID must be a number.")
                return
            self._settings.set_account(acc_id, self.txt_account_name.text().strip())
            self._settings.set_account_plex_units(
                acc_id, int(self.spin_plex_units.value())
            )
            self._changes_made = True
            self._load_accounts()
            # Select the saved account
            for i in range(self.account_list.count()):
                item = self.account_list.item(i)
                if item and item.data(Qt.ItemDataRole.UserRole) == acc_id:
                    self.account_list.setCurrentItem(item)
                    break
        except Exception:
            logger.exception("Failed to save account")

    def _on_delete_account(self) -> None:
        """Delete the selected account."""
        try:
            item = self.account_list.currentItem()
            if not item:
                QMessageBox.information(
                    self, "No Selection", "Please select an account to delete."
                )
                return

            acc_id = int(item.data(Qt.ItemDataRole.UserRole))
            acc = self._settings.get_accounts().get(acc_id, {})
            chars = acc.get("characters", [])

            # Confirm deletion
            msg = f"Delete account {acc_id}?"
            if chars:
                msg += f"\n\nThis will unassign {len(chars)} character(s) from this account."

            reply = QMessageBox.question(
                self,
                "Confirm Delete",
                msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )

            if reply == QMessageBox.StandardButton.Yes:
                # Unassign all characters first
                for char_id in chars:
                    try:
                        self._settings.unassign_character_from_account(
                            int(char_id), acc_id
                        )
                    except Exception:
                        pass
                # Delete the account
                self._settings.delete_account(acc_id)
                self._changes_made = True
                self._load_accounts()
                self._on_new_account()  # Clear form
        except Exception:
            logger.exception("Failed to delete account")

    def _on_assign_character(self) -> None:
        try:
            if self._character_id is None:
                return
            item = self.account_list.currentItem()
            if not item:
                QMessageBox.information(
                    self, "No Selection", "Please select an account first."
                )
                return
            acc_id = int(item.data(Qt.ItemDataRole.UserRole))

            # Unassign from previous account if any
            prev_acc = self._settings.get_account_for_character(self._character_id)
            if prev_acc is not None:
                self._settings.unassign_character_from_account(
                    self._character_id, prev_acc
                )

            ok = self._settings.assign_character_to_account(self._character_id, acc_id)
            if not ok:
                QMessageBox.warning(
                    self,
                    "Limit Reached",
                    "This account already has 3 characters (EVE maximum).",
                )
                return
            self._changes_made = True
            self._load_accounts()
            self._signal_bus.character_assigned.emit(self._character_id, acc_id)
        except Exception:
            logger.exception("Failed to assign character to account")

    def _on_close(self) -> None:
        """Handle dialog close - emit signal if changes were made."""
        if self._changes_made:
            self._signal_bus.account_changed.emit()
        self.reject()

    def closeEvent(self, event: QCloseEvent) -> None:  # type: ignore[override]
        """Handle window close button."""
        if self._changes_made:
            self._signal_bus.account_changed.emit()
        super().closeEvent(event)

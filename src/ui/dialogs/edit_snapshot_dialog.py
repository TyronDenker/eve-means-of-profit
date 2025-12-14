"""Dialog for editing networth snapshot values."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from models.app import NetWorthSnapshot
from ui.styles import COLORS, AppStyles

if TYPE_CHECKING:
    from models.app import CharacterInfo

logger = logging.getLogger(__name__)


class EditSnapshotDialog(QDialog):
    """Dialog to edit a networth snapshot's values."""

    def __init__(
        self,
        snapshot: NetWorthSnapshot,
        parent=None,
        characters: list[CharacterInfo] | None = None,
        snapshots_by_character: dict[int, NetWorthSnapshot] | None = None,
        group_metadata: dict | None = None,
        networth_service=None,
        accounts: dict[int, dict] | None = None,
        plex_snapshots_by_account: dict[int, dict] | None = None,
    ) -> None:
        super().__init__(parent)
        self.snapshot = snapshot
        self._original_snapshot = snapshot
        self._characters = characters or []
        self._character_map: dict[int, str] = {}  # character_id -> character_name
        # Map of character_id -> snapshot for that character at the same time
        self._snapshots_by_character = snapshots_by_character or {}
        self._group_metadata = group_metadata or {}
        self._networth_service = networth_service
        self._accounts = accounts or {}  # account_id -> {name, plex_units}
        self._plex_snapshots_by_account = plex_snapshots_by_account or {}
        self._edited_plex_snapshots: dict[
            int, dict
        ] = {}  # account_id -> {units, price}

        self.setWindowTitle("Edit Snapshot")
        self.setModal(True)
        self.setMinimumWidth(450)

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Build character map for display names
        for char in self._characters:
            cid = getattr(char, "character_id", None)
            name = getattr(char, "character_name", None)
            if cid is not None and name is not None:
                self._character_map[cid] = name

        # Get snapshot source info
        refresh_source = self._group_metadata.get("refresh_source", "unknown")
        account_id = self._group_metadata.get("account_id")
        snapshot_time = self.snapshot.snapshot_time

        # Get account name if available
        account_name = None
        try:
            from utils.settings_manager import get_settings_manager

            settings = get_settings_manager()
            if account_id:
                account_name = settings.get_account_name(account_id)
        except Exception:
            pass

        # Build source display
        if refresh_source == "refresh_all":
            source_display = "Refresh All"
        elif refresh_source == "account":
            source_display = account_name if account_name else f"Account {account_id}"
        elif refresh_source == "character":
            source_display = "Single Character"
        else:
            source_display = refresh_source

        # Header with source and time
        header_label = QLabel(
            f"<h3>Datapoint: {source_display}</h3>"
            f"<b>Time:</b> {snapshot_time.strftime('%Y-%m-%d %H:%M:%S UTC')}"
        )
        header_label.setStyleSheet(f"color: {COLORS.TEXT_PRIMARY}; padding: 10px;")
        header_label.setWordWrap(True)
        layout.addWidget(header_label)

        # Character selector (if multiple characters available)
        if self._characters:
            char_layout = QHBoxLayout()
            char_label = QLabel("Character:")
            char_label.setMinimumWidth(100)
            self.character_combo = QComboBox()
            self.character_combo.setStyleSheet(AppStyles.COMBOBOX)

            # Add characters to combo box
            for char in self._characters:
                cid = getattr(char, "character_id", None)
                name = getattr(char, "character_name", str(cid))
                if cid is not None:
                    # Check if this character's snapshot is from the same group or older
                    char_snapshot = self._snapshots_by_character.get(cid)
                    age_suffix = ""
                    if char_snapshot and hasattr(char_snapshot, "snapshot_time"):
                        time_diff = snapshot_time - char_snapshot.snapshot_time
                        if time_diff.total_seconds() > 60:  # More than 1 minute old
                            hours = int(time_diff.total_seconds() / 3600)
                            minutes = int((time_diff.total_seconds() % 3600) / 60)
                            if hours > 0:
                                age_suffix = f" ({hours}h {minutes}m old)"
                            else:
                                age_suffix = f" ({minutes}m old)"

                    self.character_combo.addItem(f"{name}{age_suffix}", cid)

            # Pre-select the snapshot's character
            for i in range(self.character_combo.count()):
                if self.character_combo.itemData(i) == self.snapshot.character_id:
                    self.character_combo.setCurrentIndex(i)
                    break

            char_layout.addWidget(char_label)
            char_layout.addWidget(self.character_combo, stretch=1)
            layout.addLayout(char_layout)

            # Connect signal to load character data when selection changes
            self.character_combo.currentIndexChanged.connect(self._on_character_changed)
        else:
            self.character_combo = None

        # Form for editing values
        form = QFormLayout()

        self.wallet_spin = QDoubleSpinBox()
        self.wallet_spin.setRange(0, 1e15)
        self.wallet_spin.setDecimals(2)
        self.wallet_spin.setValue(self.snapshot.wallet_balance)
        self.wallet_spin.setSuffix(" ISK")
        self.wallet_spin.setStyleSheet(AppStyles.DOUBLE_SPINBOX)
        form.addRow("Wallet Balance:", self.wallet_spin)

        self.assets_spin = QDoubleSpinBox()
        self.assets_spin.setRange(0, 1e15)
        self.assets_spin.setDecimals(2)
        self.assets_spin.setValue(self.snapshot.total_asset_value)
        self.assets_spin.setSuffix(" ISK")
        self.assets_spin.setStyleSheet(AppStyles.DOUBLE_SPINBOX)
        form.addRow("Total Assets:", self.assets_spin)

        self.escrow_spin = QDoubleSpinBox()
        self.escrow_spin.setRange(0, 1e15)
        self.escrow_spin.setDecimals(2)
        self.escrow_spin.setValue(self.snapshot.market_escrow)
        self.escrow_spin.setStyleSheet(AppStyles.DOUBLE_SPINBOX)
        self.escrow_spin.setSuffix(" ISK")
        form.addRow("Market Escrow:", self.escrow_spin)

        self.sell_spin = QDoubleSpinBox()
        self.sell_spin.setRange(0, 1e15)
        self.sell_spin.setDecimals(2)
        self.sell_spin.setValue(self.snapshot.market_sell_value)
        self.sell_spin.setSuffix(" ISK")
        self.sell_spin.setStyleSheet(AppStyles.DOUBLE_SPINBOX)
        form.addRow("Sell Orders:", self.sell_spin)

        self.collateral_spin = QDoubleSpinBox()
        self.collateral_spin.setRange(0, 1e15)
        self.collateral_spin.setDecimals(2)
        self.collateral_spin.setValue(self.snapshot.contract_collateral)
        self.collateral_spin.setSuffix(" ISK")
        self.collateral_spin.setStyleSheet(AppStyles.DOUBLE_SPINBOX)
        form.addRow("Contract Collateral:", self.collateral_spin)

        self.contract_spin = QDoubleSpinBox()
        self.contract_spin.setRange(0, 1e15)
        self.contract_spin.setDecimals(2)
        self.contract_spin.setValue(self.snapshot.contract_value)
        self.contract_spin.setSuffix(" ISK")
        self.contract_spin.setStyleSheet(AppStyles.DOUBLE_SPINBOX)
        form.addRow("Contract Value:", self.contract_spin)

        self.industry_spin = QDoubleSpinBox()
        self.industry_spin.setRange(0, 1e15)
        self.industry_spin.setDecimals(2)
        self.industry_spin.setValue(self.snapshot.industry_job_value)
        self.industry_spin.setSuffix(" ISK")
        self.industry_spin.setStyleSheet(AppStyles.DOUBLE_SPINBOX)
        form.addRow("Industry Jobs:", self.industry_spin)

        layout.addLayout(form)

        # PLEX section (account-level, separate from character data)
        plex_label = QLabel("<b>Account PLEX</b> (separate from character data)")
        plex_label.setStyleSheet(f"color: {COLORS.TEXT_SECONDARY}; margin-top: 10px;")
        layout.addWidget(plex_label)

        # Account selector for PLEX
        if self._accounts:
            self.plex_account_combo = QComboBox()
            self.plex_account_combo.setStyleSheet(AppStyles.COMBOBOX)

            # Add accounts to combo box
            for account_id, account_data in self._accounts.items():
                account_name = account_data.get("name", f"Account {account_id}")
                self.plex_account_combo.addItem(account_name, account_id)

            # Connect signal to load PLEX data when account selection changes
            self.plex_account_combo.currentIndexChanged.connect(
                self._on_plex_account_changed
            )

            plex_account_layout = QHBoxLayout()
            plex_account_label = QLabel("Select Account:")
            plex_account_label.setMinimumWidth(100)
            plex_account_layout.addWidget(plex_account_label)
            plex_account_layout.addWidget(self.plex_account_combo, stretch=1)
            layout.addLayout(plex_account_layout)

            # PLEX value form
            plex_form = QFormLayout()

            self.plex_units_spin = QSpinBox()
            self.plex_units_spin.setRange(0, 1000000)
            self.plex_units_spin.setValue(0)
            self.plex_units_spin.setStyleSheet(AppStyles.DOUBLE_SPINBOX)
            plex_form.addRow("PLEX Units:", self.plex_units_spin)

            self.plex_price_spin = QDoubleSpinBox()
            self.plex_price_spin.setRange(0, 1e15)
            self.plex_price_spin.setDecimals(2)
            self.plex_price_spin.setValue(0.0)
            self.plex_price_spin.setSuffix(" ISK")
            self.plex_price_spin.setStyleSheet(AppStyles.DOUBLE_SPINBOX)
            plex_form.addRow("Price per PLEX:", self.plex_price_spin)

            self.plex_total_label = QLabel()
            self.plex_total_label.setStyleSheet(
                f"font-weight: bold; color: {COLORS.TEXT_PRIMARY};"
            )
            plex_form.addRow("PLEX Total Value:", self.plex_total_label)

            layout.addLayout(plex_form)

            # Connect spinboxes to update PLEX total
            self.plex_units_spin.valueChanged.connect(self._update_plex_total)
            self.plex_price_spin.valueChanged.connect(self._update_plex_total)

            # Load first account's PLEX data if available
            if self.plex_account_combo.count() > 0:
                self._on_plex_account_changed(0)
        else:
            plex_note = QLabel("No accounts configured for PLEX editing")
            plex_note.setStyleSheet(
                f"color: {COLORS.TEXT_MUTED}; font-style: italic; margin-bottom: 10px;"
            )
            layout.addWidget(plex_note)
            self.plex_account_combo = None
            self.plex_units_spin = None
            self.plex_price_spin = None
            self.plex_total_label = None

        # Total display (character data only, PLEX is separate)
        self.total_label = QLabel()
        self.total_label.setStyleSheet(
            f"font-weight: bold; font-size: 14pt; color: {COLORS.TEXT_PRIMARY};"
        )
        self.total_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._update_total()
        layout.addWidget(self.total_label)

        # Connect spinboxes to update total
        for spin in [
            self.wallet_spin,
            self.assets_spin,
            self.escrow_spin,
            self.sell_spin,
            self.collateral_spin,
            self.contract_spin,
            self.industry_spin,
        ]:
            spin.valueChanged.connect(self._update_total)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.accept)
        button_layout.addWidget(save_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)

    def _update_total(self) -> None:
        """Update the total display (character data only)."""
        total = (
            self.wallet_spin.value()
            + self.assets_spin.value()
            + self.escrow_spin.value()
            + self.sell_spin.value()
            + self.collateral_spin.value()
            + self.contract_spin.value()
            + self.industry_spin.value()
        )
        self.total_label.setText(f"Character Total: {total:,.2f} ISK")

    def _update_plex_total(self) -> None:
        """Update the PLEX total value display."""
        if self.plex_total_label is None:
            return
        units = self.plex_units_spin.value()
        price = self.plex_price_spin.value()
        total = units * price
        self.plex_total_label.setText(f"{total:,.2f} ISK")

    def _on_plex_account_changed(self, index: int) -> None:
        """Handle PLEX account selection change - load that account's PLEX data."""
        if self.plex_account_combo is None or index < 0:
            return

        selected_account_id = self.plex_account_combo.itemData(index)
        if selected_account_id is None:
            return

        # Load the PLEX snapshot for this account if available
        if selected_account_id in self._plex_snapshots_by_account:
            plex_snap = self._plex_snapshots_by_account[selected_account_id]
            self._load_plex_values(selected_account_id, plex_snap)
        else:
            # No existing PLEX snapshot for this account
            self.plex_units_spin.setValue(0)
            self.plex_price_spin.setValue(0.0)

    def _load_plex_values(self, account_id: int, plex_snap: dict) -> None:
        """Load PLEX values from a snapshot into the spinboxes."""
        # Block signals to prevent redundant total updates
        for spinbox in [self.plex_units_spin, self.plex_price_spin]:
            spinbox.blockSignals(True)

        plex_units = int(plex_snap.get("plex_units", 0) or 0)
        plex_price = float(plex_snap.get("plex_unit_price", 0.0) or 0.0)

        self.plex_units_spin.setValue(plex_units)
        self.plex_price_spin.setValue(plex_price)

        # Store this for later saving
        self._edited_plex_snapshots[account_id] = {
            "units": plex_units,
            "price": plex_price,
        }

        # Unblock signals
        for spinbox in [self.plex_units_spin, self.plex_price_spin]:
            spinbox.blockSignals(False)

        # Update total after loading
        self._update_plex_total()

    def get_selected_character_id(self) -> int:
        """Get the currently selected character ID from the dropdown."""
        if self.character_combo is not None:
            return int(self.character_combo.currentData())
        return self.snapshot.character_id

    def _on_character_changed(self, index: int) -> None:
        """Handle character selection change - load that character's snapshot data."""
        if self.character_combo is None or index < 0:
            return

        selected_char_id = self.character_combo.itemData(index)
        if selected_char_id is None:
            return

        # Load the snapshot for this character if available
        if selected_char_id in self._snapshots_by_character:
            snap = self._snapshots_by_character[selected_char_id]
            self._load_snapshot_values(snap)
        elif selected_char_id == self._original_snapshot.character_id:
            # Load original snapshot values
            self._load_snapshot_values(self._original_snapshot)

    def _load_snapshot_values(self, snap: NetWorthSnapshot) -> None:
        """Load values from a snapshot into the spinboxes."""
        # Block signals to prevent redundant total updates
        for spinbox in [
            self.wallet_spin,
            self.assets_spin,
            self.escrow_spin,
            self.sell_spin,
            self.collateral_spin,
            self.contract_spin,
            self.industry_spin,
        ]:
            spinbox.blockSignals(True)

        self.wallet_spin.setValue(snap.wallet_balance)
        self.assets_spin.setValue(snap.total_asset_value)
        self.escrow_spin.setValue(snap.market_escrow)
        self.sell_spin.setValue(snap.market_sell_value)
        self.collateral_spin.setValue(snap.contract_collateral)
        self.contract_spin.setValue(snap.contract_value)
        self.industry_spin.setValue(snap.industry_job_value)

        # Unblock signals
        for spinbox in [
            self.wallet_spin,
            self.assets_spin,
            self.escrow_spin,
            self.sell_spin,
            self.collateral_spin,
            self.contract_spin,
            self.industry_spin,
        ]:
            spinbox.blockSignals(False)

        # Update total after loading
        self._update_total()

    def get_updated_snapshot(self) -> NetWorthSnapshot:
        """Get the snapshot with updated values."""
        # Use selected character if combo exists, otherwise original
        character_id = self.get_selected_character_id()

        return NetWorthSnapshot(
            snapshot_id=self.snapshot.snapshot_id,
            character_id=character_id,
            account_id=self.snapshot.account_id,
            snapshot_group_id=self.snapshot.snapshot_group_id,
            snapshot_time=self.snapshot.snapshot_time,
            wallet_balance=self.wallet_spin.value(),
            total_asset_value=self.assets_spin.value(),
            market_escrow=self.escrow_spin.value(),
            market_sell_value=self.sell_spin.value(),
            contract_collateral=self.collateral_spin.value(),
            contract_value=self.contract_spin.value(),
            industry_job_value=self.industry_spin.value(),
            plex_vault=0.0,  # PLEX is account-level, not character-level
        )

    def get_edited_plex_snapshots(self) -> dict[int, dict]:
        """Get PLEX snapshots that were edited in this dialog.

        Returns:
            Dict mapping account_id -> {units, price, snapshot_data} for edited accounts
        """
        result = {}

        # Collect all PLEX snapshots that were modified
        for account_id, plex_snap in self._plex_snapshots_by_account.items():
            if account_id in self._edited_plex_snapshots:
                edited = self._edited_plex_snapshots[account_id]
                original_units = int(plex_snap.get("plex_units", 0) or 0)
                original_price = float(plex_snap.get("plex_unit_price", 0.0) or 0.0)

                # Only include if values changed
                if (
                    edited["units"] != original_units
                    or edited["price"] != original_price
                ):
                    result[account_id] = {
                        "plex_snapshot_id": plex_snap.get("plex_snapshot_id"),
                        "units": edited["units"],
                        "price": edited["price"],
                        "snapshot_data": plex_snap,  # Original snapshot data for reference
                    }

        return result

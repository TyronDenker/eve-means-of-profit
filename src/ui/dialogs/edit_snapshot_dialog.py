"""Dialog for editing networth snapshot values."""

from __future__ import annotations

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
    QVBoxLayout,
)

from models.app import NetWorthSnapshot
from ui.styles import COLORS, AppStyles

if TYPE_CHECKING:
    from models.app import CharacterInfo


class EditSnapshotDialog(QDialog):
    """Dialog to edit a networth snapshot's values."""

    def __init__(
        self,
        snapshot: NetWorthSnapshot,
        parent=None,
        characters: list[CharacterInfo] | None = None,
        snapshots_by_character: dict[int, NetWorthSnapshot] | None = None,
    ) -> None:
        super().__init__(parent)
        self.snapshot = snapshot
        self._original_snapshot = snapshot
        self._characters = characters or []
        self._character_map: dict[int, str] = {}  # character_id -> character_name
        # Map of character_id -> snapshot for that character at the same time
        self._snapshots_by_character = snapshots_by_character or {}
        self.setWindowTitle(
            f"Edit Snapshot - {snapshot.snapshot_time.strftime('%Y-%m-%d %H:%M')}"
        )
        self.setModal(True)
        self.setMinimumWidth(400)

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Build character map for display names
        for char in self._characters:
            cid = getattr(char, "character_id", None)
            name = getattr(char, "character_name", None)
            if cid is not None and name is not None:
                self._character_map[cid] = name

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
                    self.character_combo.addItem(name, cid)

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

        # Get character display name
        char_display = self._character_map.get(
            self.snapshot.character_id, str(self.snapshot.character_id)
        )

        # Context info section with detailed timing and source information
        context_lines = [
            f"<b>Character:</b> {char_display}",
            f"<b>Snapshot Time:</b> {self.snapshot.snapshot_time.strftime('%Y-%m-%d %H:%M:%S UTC')}",
        ]

        # Add snapshot group info if available
        if self.snapshot.snapshot_group_id:
            context_lines.append(
                f"<b>Snapshot Group ID:</b> {self.snapshot.snapshot_group_id}"
            )

        # Add account info if available
        if self.snapshot.account_id:
            context_lines.append(f"<b>Account ID:</b> {self.snapshot.account_id}")

        # Determine snapshot source based on group and account info
        source = "Unknown"
        if self.snapshot.snapshot_group_id:
            if self.snapshot.account_id is None:
                source = "Refresh All (grouped)"
            else:
                source = f"Refresh Account {self.snapshot.account_id} (grouped)"
        else:
            if self.snapshot.account_id:
                source = f"Character (Account {self.snapshot.account_id})"
            else:
                source = "Character (standalone)"

        context_lines.append(f"<b>Source:</b> {source}")

        # Build the info label with all context
        info_label = QLabel("<br>".join(context_lines))
        info_label.setStyleSheet(AppStyles.LABEL_INFO)
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

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

        self.plex_spin = QDoubleSpinBox()
        self.plex_spin.setRange(0, 1e15)
        self.plex_spin.setDecimals(2)
        self.plex_spin.setValue(self.snapshot.plex_vault)
        self.plex_spin.setSuffix(" ISK")
        self.plex_spin.setStyleSheet(AppStyles.DOUBLE_SPINBOX)
        form.addRow("PLEX Vault:", self.plex_spin)

        layout.addLayout(form)

        # Total display
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
            self.plex_spin,
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
        """Update the total display."""
        total = (
            self.wallet_spin.value()
            + self.assets_spin.value()
            + self.escrow_spin.value()
            + self.sell_spin.value()
            + self.collateral_spin.value()
            + self.contract_spin.value()
            + self.industry_spin.value()
            + self.plex_spin.value()
        )
        self.total_label.setText(f"Total Net Worth: {total:,.2f} ISK")

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
            self.plex_spin,
        ]:
            spinbox.blockSignals(True)

        self.wallet_spin.setValue(snap.wallet_balance)
        self.assets_spin.setValue(snap.total_asset_value)
        self.escrow_spin.setValue(snap.market_escrow)
        self.sell_spin.setValue(snap.market_sell_value)
        self.collateral_spin.setValue(snap.contract_collateral)
        self.contract_spin.setValue(snap.contract_value)
        self.industry_spin.setValue(snap.industry_job_value)
        self.plex_spin.setValue(snap.plex_vault)

        # Unblock signals
        for spinbox in [
            self.wallet_spin,
            self.assets_spin,
            self.escrow_spin,
            self.sell_spin,
            self.collateral_spin,
            self.contract_spin,
            self.industry_spin,
            self.plex_spin,
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
            plex_vault=self.plex_spin.value(),
        )

"""Industry slots view showing available manufacturing and research slots."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from services.character_service import CharacterService
from services.industry_service import IndustryService
from ui.menus.context_menu_factory import ContextMenuFactory
from ui.signal_bus import get_signal_bus
from ui.widgets.advanced_table_widget import AdvancedTableView
from utils.settings_manager import get_settings_manager

if TYPE_CHECKING:
    from data.clients import ESIClient

logger = logging.getLogger(__name__)

# Activity name mapping
ACTIVITY_NAMES = {
    1: "Manufacturing",
    3: "Research Time Efficiency",
    4: "Research Material Efficiency",
    5: "Copy",
    7: "Reverse Engineering",
    8: "Invention",
    9: "Reaction",
}

# Skill type IDs for industry slots
# Mass Production: 3387 (+1 manufacturing slot per level)
# Advanced Mass Production: 24625 (+1 manufacturing slot per level)
# Laboratory Operation: 3406 (+1 research slot per level)
# Advanced Laboratory Operation: 24624 (+1 research slot per level)
SKILL_MASS_PRODUCTION = 3387
SKILL_ADVANCED_MASS_PRODUCTION = 24625
SKILL_LABORATORY_OPERATION = 3406
SKILL_ADVANCED_LABORATORY_OPERATION = 24624
# Reaction slot skills
SKILL_MASS_REACTIONS = 45748
SKILL_ADVANCED_MASS_REACTIONS = 45749


class IndustrySlotsTab(QWidget):
    """Industry slots overview per character with modern grid display."""

    def __init__(
        self,
        character_service: CharacterService,
        industry_service: IndustryService,
        esi_client: ESIClient,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._signal_bus = get_signal_bus()
        self._character_service = character_service
        self._industry_service = industry_service
        self._esi_client = esi_client
        self._settings = get_settings_manager()
        self._context_menu_factory = ContextMenuFactory(self._settings)
        self._background_tasks: set[asyncio.Task] = set()
        self._current_characters: list = []
        self._skills_cache: dict[int, dict[str, Any]] = {}
        self._rows_cache: list[dict[str, Any]] = []

        # Column specifications for AdvancedTableView
        self._columns: list[tuple[str, str]] = [
            ("character_name", "Character"),
            ("activity_type", "Activity Type"),
            ("active_slots", "Active"),
            ("max_slots", "Max"),
            ("available_slots", "Available"),
        ]

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Setup UI layout and widgets."""
        main_layout = QVBoxLayout(self)

        # Toolbar
        toolbar_layout = QHBoxLayout()
        self._refresh_btn = QPushButton("Refresh")
        toolbar_layout.addWidget(self._refresh_btn)
        toolbar_layout.addStretch()
        main_layout.addLayout(toolbar_layout)

        # Summary section
        summary_layout = QHBoxLayout()
        summary_layout.addWidget(QLabel("Manufacturing:"))
        self._mfg_label = QLabel("-- slots")
        summary_layout.addWidget(self._mfg_label)

        summary_layout.addWidget(QLabel("Research:"))
        self._research_label = QLabel("-- slots")
        summary_layout.addWidget(self._research_label)

        summary_layout.addWidget(QLabel("Reactions:"))
        self._reactions_label = QLabel("-- slots")
        summary_layout.addWidget(self._reactions_label)

        summary_layout.addStretch()
        main_layout.addLayout(summary_layout)

        # Table widget using AdvancedTableView
        self._table = AdvancedTableView()
        self._table.setup(self._columns)
        self._table.set_context_menu_builder(self._build_context_menu)
        main_layout.addWidget(self._table)

    def _connect_signals(self) -> None:
        """Connect signals to slots."""
        self._signal_bus.characters_loaded.connect(self._on_characters_loaded)
        self._signal_bus.skills_refreshed.connect(self._on_skills_refreshed)
        self._refresh_btn.clicked.connect(self._on_refresh_clicked)

    def _on_characters_loaded(self, characters: list) -> None:
        """Handle characters loaded signal."""
        self._current_characters = self._dedupe_characters(characters)
        self._on_refresh_clicked()

    def _on_skills_refreshed(self, character_id: int) -> None:
        """Handle skills refreshed signal - invalidate cache for the character."""
        if character_id in self._skills_cache:
            del self._skills_cache[character_id]
        # Refresh table to show updated slot counts
        self._on_refresh_clicked()

    def _dedupe_characters(self, characters: list) -> list:
        """Return list without duplicate character_ids."""
        seen: set[int] = set()
        unique: list = []
        for char in characters:
            cid = getattr(char, "character_id", None)
            if cid in seen:
                continue
            if cid is not None:
                seen.add(cid)
            unique.append(char)
        return unique

    def _on_refresh_clicked(self) -> None:
        """Handle refresh button click."""
        task = asyncio.create_task(self._do_refresh())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _do_refresh(self) -> None:
        """Async refresh of industry slots."""
        try:
            self._refresh_btn.setEnabled(False)
            self._refresh_btn.setText("Loading...")

            # Reset row cache for this refresh run
            self._rows_cache = []

            if not self._current_characters:
                self._mfg_label.setText("No characters")
                self._research_label.setText("No characters")
                self._reactions_label.setText("No characters")
                self._table.set_rows([])
                return

            # Track totals across all characters
            total_mfg_active = 0
            total_mfg_max = 0
            total_research_active = 0
            total_research_max = 0
            total_reaction_active = 0
            total_reaction_max = 0

            # Process each character
            for char in self._current_characters:
                char_id = getattr(char, "character_id", None)
                char_name = getattr(char, "character_name", None)
                if not char_name:
                    char_name = getattr(char, "name", f"Character {char_id}")

                if not char_id:
                    continue

                try:
                    # Get active job counts by activity
                    slot_counts = (
                        await self._industry_service.get_active_job_count_by_activity(
                            character_id=char_id
                        )
                    )

                    # Manufacturing slot calc (activity 1)
                    mfg_active = slot_counts.get(1, 0)
                    mfg_max = await self._calculate_manufacturing_slots(char_id)
                    mfg_available = max(0, mfg_max - mfg_active)

                    # Research slots (activities 3, 4, 5)
                    research_active = sum(
                        slot_counts.get(activity_id, 0) for activity_id in [3, 4, 5]
                    )
                    research_max = await self._calculate_research_slots(char_id)
                    research_available = max(0, research_max - research_active)

                    # Reaction slots (activity 9)
                    reaction_active = slot_counts.get(9, 0)
                    reaction_max = await self._calculate_reaction_slots(char_id)
                    reaction_available = max(0, reaction_max - reaction_active)

                    # Add manufacturing row
                    self._rows_cache.append(
                        {
                            "character_name": str(char_name),
                            "activity_type": "Manufacturing",
                            "active_slots": str(mfg_active),
                            "max_slots": str(mfg_max),
                            "available_slots": str(mfg_available),
                        }
                    )

                    # Add research row
                    self._rows_cache.append(
                        {
                            "character_name": str(char_name),
                            "activity_type": "Research",
                            "active_slots": str(research_active),
                            "max_slots": str(research_max),
                            "available_slots": str(research_available),
                        }
                    )

                    # Add reactions row
                    self._rows_cache.append(
                        {
                            "character_name": str(char_name),
                            "activity_type": "Reactions",
                            "active_slots": str(reaction_active),
                            "max_slots": str(reaction_max),
                            "available_slots": str(reaction_available),
                        }
                    )

                    # Update totals
                    total_mfg_active += mfg_active
                    total_mfg_max += mfg_max
                    total_research_active += research_active
                    total_research_max += research_max
                    total_reaction_active += reaction_active
                    total_reaction_max += reaction_max

                except Exception as e:
                    logger.error(
                        "Failed to get slots for character %s: %s",
                        char_id,
                        e,
                        exc_info=True,
                    )

            # Update table
            self._table.set_rows(self._rows_cache)

            # Update summary labels
            self._mfg_label.setText(
                f"{total_mfg_active}/{total_mfg_max} ({max(0, total_mfg_max - total_mfg_active)} available)"
            )
            self._research_label.setText(
                f"{total_research_active}/{total_research_max} ({max(0, total_research_max - total_research_active)} available)"
            )
            self._reactions_label.setText(
                f"{total_reaction_active}/{total_reaction_max} ({max(0, total_reaction_max - total_reaction_active)} available)"
            )

        except Exception as e:
            logger.error("Error refreshing industry slots: %s", e, exc_info=True)
            self._signal_bus.error_occurred.emit(str(e))
        finally:
            self._refresh_btn.setEnabled(True)
            self._refresh_btn.setText("Refresh")

    async def _get_skill_level(self, character_id: int, skill_id: int) -> int:
        """Get the trained level of a skill for a character.

        Caches per-refresh to avoid repeated ESI calls for the same character.
        """
        try:
            skills = await self._get_skills(character_id)
            for skill in skills:
                if skill.get("skill_id") == skill_id:
                    return skill.get("trained_skill_level", 0)
            return 0
        except Exception as e:
            logger.warning(
                "Failed to get skill %d for character %d: %s", skill_id, character_id, e
            )
            return 0

    async def _get_skills(self, character_id: int) -> list[dict[str, Any]]:
        """Fetch and cache skills list for a character."""
        if character_id in self._skills_cache:
            return self._skills_cache[character_id].get("skills", [])

        try:
            skills_data, _ = await self._esi_client.skills.get_skills(
                character_id, use_cache=True
            )
        except Exception:
            logger.warning("Failed to fetch skills for character %d", character_id)
            skills_data = {}

        self._skills_cache[character_id] = skills_data
        return skills_data.get("skills", [])

    async def _calculate_manufacturing_slots(self, character_id: int) -> int:
        """Calculate total manufacturing slots for a character.

        Base: 1 slot
        Mass Production: +1 per level (max 5)
        Advanced Mass Production: +1 per level (max 5)

        Args:
            character_id: Character ID

        Returns:
            Total manufacturing slots (1-11)
        """
        base_slots = 1
        mass_production_level = await self._get_skill_level(
            character_id, SKILL_MASS_PRODUCTION
        )
        advanced_mass_production_level = await self._get_skill_level(
            character_id, SKILL_ADVANCED_MASS_PRODUCTION
        )

        total = base_slots + mass_production_level + advanced_mass_production_level
        logger.debug(
            "Character %d manufacturing slots: %d (base=%d, MP=%d, AMP=%d)",
            character_id,
            total,
            base_slots,
            mass_production_level,
            advanced_mass_production_level,
        )
        return total

    async def _calculate_research_slots(self, character_id: int) -> int:
        """Calculate total research slots for a character.

        Base: 1 slot
        Laboratory Operation: +1 per level (max 5)
        Advanced Laboratory Operation: +1 per level (max 5)

        Args:
            character_id: Character ID

        Returns:
            Total research slots (1-11)
        """
        base_slots = 1
        lab_operation_level = await self._get_skill_level(
            character_id, SKILL_LABORATORY_OPERATION
        )
        advanced_lab_operation_level = await self._get_skill_level(
            character_id, SKILL_ADVANCED_LABORATORY_OPERATION
        )

        total = base_slots + lab_operation_level + advanced_lab_operation_level
        logger.debug(
            "Character %d research slots: %d (base=%d, LO=%d, ALO=%d)",
            character_id,
            total,
            base_slots,
            lab_operation_level,
            advanced_lab_operation_level,
        )
        return total

    async def _calculate_reaction_slots(self, character_id: int) -> int:
        """Calculate total reaction slots for a character.

        Base: 0 slot
        Mass Reactions: +1 per level (type 45748)
        Advanced Mass Reactions: +1 per level (type 45749)
        """

        base_slots = 0
        mass_reactions_level = await self._get_skill_level(
            character_id, SKILL_MASS_REACTIONS
        )
        advanced_mass_reactions_level = await self._get_skill_level(
            character_id, SKILL_ADVANCED_MASS_REACTIONS
        )

        total = base_slots + mass_reactions_level + advanced_mass_reactions_level
        logger.debug(
            "Character %d reaction slots: %d (base=%d, MR=%d, AMR=%d)",
            character_id,
            total,
            base_slots,
            mass_reactions_level,
            advanced_mass_reactions_level,
        )
        return total

    def _build_context_menu(self, selected_rows: list[dict[str, Any]]):
        """Build context menu for selected rows."""
        return self._context_menu_factory.build_table_menu(
            self,
            selected_rows,
            self._columns,
            enable_copy=True,
            enable_custom_price=False,  # Slots don't have type IDs to customize
            enable_custom_location=False,  # Slots don't have location IDs
        )

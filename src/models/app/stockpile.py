"""Stockpile definition models for tracking target inventory quantities."""

from __future__ import annotations

from pydantic import BaseModel, Field


class StockpileTarget(BaseModel):
    """Represents a single item target in a stockpile."""

    target_id: int = Field(..., description="Unique target ID")
    stockpile_id: int = Field(..., description="Parent stockpile ID")
    type_id: int = Field(..., description="EVE item type ID")
    type_name: str | None = Field(None, description="Item type name (resolved)")
    target_quantity: int = Field(..., description="Target quantity to maintain")
    current_quantity: int = Field(default=0, description="Current quantity in stock")
    parent_target_id: int | None = Field(
        None, description="Parent target ID (for substockpiles)"
    )

    @property
    def shortfall(self) -> int:
        """Calculate shortfall (negative = surplus)."""
        return self.target_quantity - self.current_quantity


class Stockpile(BaseModel):
    """Represents a complete stockpile with targets."""

    stockpile_id: int = Field(..., description="Unique stockpile ID")
    character_id: int = Field(..., description="Character who owns this stockpile")
    name: str = Field(..., description="Stockpile name (e.g., 'Main Stockpile')")
    location_id: int = Field(..., description="Primary location ID")
    location_name: str | None = Field(None, description="Location name (resolved)")
    notes: str | None = Field(None, description="User notes")
    targets: list[StockpileTarget] = Field(
        default_factory=list, description="List of targets"
    )
    substockpiles: list[Stockpile] = Field(
        default_factory=list, description="Nested stockpiles"
    )

    @property
    def total_target_value(self) -> float:
        """Calculate total target ISK value (would need pricing data)."""
        # This is a placeholder - actual implementation would use market prices
        return 0.0

    @property
    def total_current_value(self) -> float:
        """Calculate total current ISK value."""
        return 0.0

    @property
    def total_shortfall_value(self) -> float:
        """Calculate total shortfall ISK value."""
        return 0.0

    def get_shortfall_items(self) -> list[StockpileTarget]:
        """Get all targets with shortfalls."""
        return [t for t in self.targets if t.shortfall > 0]

    def get_surplus_items(self) -> list[StockpileTarget]:
        """Get all targets with surplus."""
        return [t for t in self.targets if t.shortfall < 0]

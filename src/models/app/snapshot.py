"""EVE Online snapshot and history data models."""

from datetime import datetime

from pydantic import BaseModel, Field, computed_field


class NetWorthSnapshot(BaseModel):
    """Represents an aggregate net worth snapshot for a character."""

    snapshot_id: int = Field(..., description="Unique snapshot identifier")
    character_id: int = Field(..., description="Character who owns these assets")
    account_id: int | None = Field(
        None, description="Owning account for this character (if assigned)"
    )
    snapshot_group_id: int | None = Field(
        None,
        description="Group identifier to associate simultaneous snapshots across characters",
    )
    snapshot_time: datetime = Field(..., description="When the snapshot was taken")

    total_asset_value: float = Field(..., ge=0, description="Total value of all items")
    wallet_balance: float = Field(..., ge=0, description="ISK in wallet")
    market_escrow: float = Field(..., ge=0, description="ISK in buy order escrow")
    market_sell_value: float = Field(
        ..., ge=0, description="Value of items in sell orders"
    )
    contract_collateral: float = Field(
        ..., ge=0, description="ISK locked in collateral"
    )
    contract_value: float = Field(
        ..., ge=0, description="Estimated value of items in contracts"
    )
    industry_job_value: float = Field(
        ..., ge=0, description="Estimated output value of active jobs"
    )
    plex_vault: float = Field(
        0.0, ge=0, description="Value of PLEX in vault (quantity * price)"
    )

    @computed_field  # type: ignore[misc]
    @property
    def total_net_worth(self) -> float:
        """Calculate total net worth from all components."""
        return (
            self.wallet_balance
            + self.market_escrow
            + self.market_sell_value
            + self.contract_collateral
            + self.contract_value
            + self.total_asset_value
            + self.industry_job_value
            + self.plex_vault
        )


class AssetSnapshot(BaseModel):
    """Represents metadata for an asset snapshot."""

    snapshot_id: int = Field(..., description="Unique snapshot identifier")
    character_id: int = Field(..., description="Character who owns these assets")
    snapshot_time: datetime = Field(..., description="When the snapshot was taken")
    total_items: int = Field(..., ge=0, description="Total number of items")
    notes: str | None = Field(None, description="Optional notes about the snapshot")


class AssetChange(BaseModel):
    """Represents a change in an asset between snapshots."""

    change_id: int = Field(..., description="Unique change identifier")
    snapshot_id: int = Field(..., description="Snapshot this change belongs to")
    item_id: int = Field(..., description="Asset item ID")
    type_id: int = Field(..., description="EVE item type ID")
    change_type: str = Field(
        ..., description="Type of change: 'added', 'removed', or 'modified'"
    )
    old_quantity: int | None = Field(None, description="Previous quantity")
    new_quantity: int | None = Field(None, description="New quantity")
    old_location_id: int | None = Field(None, description="Previous location ID")
    new_location_id: int | None = Field(None, description="New location ID")
    old_location_flag: str | None = Field(None, description="Previous location flag")
    new_location_flag: str | None = Field(None, description="New location flag")
    change_time: datetime = Field(..., description="When the change occurred")
    snapshot_time: datetime = Field(
        ..., description="When the snapshot was taken (from join)"
    )


class PriceSnapshot(BaseModel):
    """Represents metadata for a price snapshot."""

    snapshot_id: int = Field(..., description="Unique snapshot identifier")
    snapshot_time: datetime = Field(..., description="When the snapshot was taken")
    source: str = Field(..., description="Data source (e.g., 'fuzzwork')")
    total_items: int = Field(..., ge=0, description="Total number of items")
    notes: str | None = Field(None, description="Optional notes about the snapshot")
    snapshot_group_id: int | None = Field(
        None, description="Optional snapshot group for grouped net worth history"
    )


class PriceHistory(BaseModel):
    """Represents historical price data for a specific item in a region."""

    price_id: int = Field(..., description="Unique price record identifier")
    type_id: int = Field(..., description="EVE item type ID")
    region_id: int = Field(..., description="EVE region ID")
    snapshot_id: int = Field(..., description="Snapshot identifier")

    # Buy order statistics
    buy_weighted_average: float | None = Field(
        None, description="Buy weighted average price"
    )
    buy_max_price: float | None = Field(None, description="Buy maximum price")
    buy_min_price: float | None = Field(None, description="Buy minimum price")
    buy_stddev: float | None = Field(None, description="Buy standard deviation")
    buy_median: float | None = Field(None, description="Buy median price")
    buy_volume: int | None = Field(None, description="Buy volume")
    buy_num_orders: int | None = Field(None, description="Number of buy orders")
    buy_five_percent: float | None = Field(None, description="Buy 5th percentile price")

    # Sell order statistics
    sell_weighted_average: float | None = Field(
        None, description="Sell weighted average price"
    )
    sell_max_price: float | None = Field(None, description="Sell maximum price")
    sell_min_price: float | None = Field(None, description="Sell minimum price")
    sell_stddev: float | None = Field(None, description="Sell standard deviation")
    sell_median: float | None = Field(None, description="Sell median price")
    sell_volume: int | None = Field(None, description="Sell volume")
    sell_num_orders: int | None = Field(None, description="Number of sell orders")
    sell_five_percent: float | None = Field(
        None, description="Sell 5th percentile price"
    )


class CustomPrice(BaseModel):
    """Represents a user-provided custom price override for a specific item.

    Stored per snapshot so the user can version their overrides.
    """

    type_id: int = Field(..., description="EVE item type ID")
    snapshot_id: int = Field(
        ..., description="Snapshot identifier this override belongs to"
    )
    custom_buy_price: float | None = Field(None, description="User override buy price")
    custom_sell_price: float | None = Field(
        None, description="User override sell price"
    )

"""Qt table models for displaying EVE Online data."""

from typing import Any, ClassVar

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt, QVariant

from models.eve import EveType
from utils import format_currency, format_mass, format_number, format_volume

# Optional import for market data manager
try:
    from data.managers import MarketDataManager
except ImportError:
    MarketDataManager = None  # type: ignore


class TypesTableModel(QAbstractTableModel):
    """Table model for displaying EVE types."""

    COLUMNS: ClassVar[list[tuple[str, str]]] = [
        ("ID", "id"),
        ("Name", "name"),
        ("Group ID", "group_id"),
        ("Volume", "volume"),
        ("Mass", "mass"),
        ("Base Price", "base_price"),
        ("Jita Sell", "market_sell"),
        ("Jita Buy", "market_buy"),
        ("Published", "published"),
    ]

    def __init__(
        self,
        types: list[EveType] | None = None,
        market_manager: Any | None = None,
        region_id: int = 10000002,
    ):
        """Initialize the model.

        Args:
            types: List of EveType objects to display
            market_manager: Optional MarketDataManager for price data
            region_id: Region ID for market prices (default: The Forge)

        """
        super().__init__()
        self._types = types or []
        self._market_manager = market_manager
        self._region_id = region_id

    def rowCount(self, parent: QModelIndex | None = None) -> int:  # noqa: N802
        """Return the number of rows."""
        if parent is None:
            parent = QModelIndex()
        if parent.isValid():
            return 0
        return len(self._types)

    def columnCount(self, parent: QModelIndex | None = None) -> int:  # noqa: N802
        """Return the number of columns."""
        if parent is None:
            parent = QModelIndex()
        if parent.isValid():
            return 0
        return len(self.COLUMNS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        """Return data for the given index and role."""
        if not index.isValid():
            return QVariant()

        if role != Qt.ItemDataRole.DisplayRole:
            return QVariant()

        row = index.row()
        col = index.column()

        if row < 0 or row >= len(self._types):
            return QVariant()

        eve_type = self._types[row]
        _, attr_name = self.COLUMNS[col]

        # Handle market price columns separately
        if attr_name == "market_sell":
            return self._get_market_price(eve_type.id, is_buy_order=False)
        if attr_name == "market_buy":
            return self._get_market_price(eve_type.id, is_buy_order=True)

        value = getattr(eve_type, attr_name, None)

        # Special formatting for specific columns
        if attr_name == "name" and value is not None and hasattr(value, "en"):
            return value.en
        if attr_name == "volume":
            return format_volume(value)
        if attr_name == "mass":
            return format_mass(value)
        if attr_name == "base_price":
            return format_currency(value)
        if attr_name == "published":
            return "Yes" if value else "No"
        if value is None:
            return "N/A"
        return str(value)

    def _get_market_price(self, type_id: int, is_buy_order: bool) -> str:
        """Get formatted market price for a type.

        Args:
            type_id: Type ID to look up
            is_buy_order: True for buy orders, False for sell orders

        Returns:
            Formatted price string or "N/A"

        """
        if self._market_manager is None:
            return "N/A"

        price = self._market_manager.get_price(type_id, self._region_id, is_buy_order)
        if price is None:
            return "N/A"

        # Use best price (lowest sell, highest buy)
        best = price.get_best_price()
        return format_currency(best, include_isk=False)

    def headerData(  # noqa: N802
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        """Return header data."""
        if role != Qt.ItemDataRole.DisplayRole:
            return QVariant()

        if orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(self.COLUMNS):
                return self.COLUMNS[section][0]

        return QVariant()

    def update_types(self, types: list[EveType]) -> None:
        """Update the types displayed in the model.

        Args:
            types: New list of EveType objects

        """
        self.beginResetModel()
        self._types = types
        self.endResetModel()

    def set_market_manager(self, market_manager: Any) -> None:
        """Set the market manager and refresh display.

        Args:
            market_manager: MarketDataManager instance

        """
        self._market_manager = market_manager
        # Refresh the market price columns
        if len(self._types) > 0:
            top_left = self.index(0, 6)  # market_sell column
            bottom_right = self.index(len(self._types) - 1, 7)  # market_buy
            self.dataChanged.emit(top_left, bottom_right)

    def set_region(self, region_id: int) -> None:
        """Set the region for market prices and refresh.

        Args:
            region_id: New region ID

        """
        self._region_id = region_id
        # Refresh the market price columns
        if len(self._types) > 0:
            top_left = self.index(0, 6)  # market_sell column
            bottom_right = self.index(len(self._types) - 1, 7)  # market_buy
            self.dataChanged.emit(top_left, bottom_right)

    def get_type_at_row(self, row: int) -> EveType | None:
        """Get the EveType object at a specific row.

        Args:
            row: Row index

        Returns:
            EveType object or None if row is invalid

        """
        if 0 <= row < len(self._types):
            return self._types[row]
        return None


class BlueprintTableModel(QAbstractTableModel):
    """Table model for displaying blueprint materials."""

    COLUMNS: ClassVar[list[tuple[str, str]]] = [
        ("Type ID", "type_id"),
        ("Quantity", "quantity"),
        ("Name", "name"),
    ]

    def __init__(
        self,
        materials: list[Any] | None = None,
        type_names: dict[int, str] | None = None,
    ):
        """Initialize the model.

        Args:
            materials: List of material objects (from blueprint activities)
            type_names: Dictionary mapping type IDs to names

        """
        super().__init__()
        self._materials = materials or []
        self._type_names = type_names or {}

    def rowCount(self, parent: QModelIndex | None = None) -> int:  # noqa: N802
        """Return the number of rows."""
        if parent is None:
            parent = QModelIndex()
        if parent.isValid():
            return 0
        return len(self._materials)

    def columnCount(self, parent: QModelIndex | None = None) -> int:  # noqa: N802
        """Return the number of columns."""
        if parent is None:
            parent = QModelIndex()
        if parent.isValid():
            return 0
        return len(self.COLUMNS)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        """Return data for the given index and role."""
        if not index.isValid():
            return QVariant()

        if role != Qt.ItemDataRole.DisplayRole:
            return QVariant()

        row = index.row()
        col = index.column()

        if row < 0 or row >= len(self._materials):
            return QVariant()

        material = self._materials[row]
        _, attr_name = self.COLUMNS[col]

        if attr_name == "name":
            type_id = getattr(material, "type_id", None)
            if type_id is not None:
                return self._type_names.get(type_id, "Unknown")
            return "Unknown"
        if attr_name == "quantity":
            value = getattr(material, attr_name, None)
            return format_number(value) if value is not None else "N/A"
        value = getattr(material, attr_name, None)
        return str(value) if value is not None else "N/A"

    def headerData(  # noqa: N802
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        """Return header data."""
        if role != Qt.ItemDataRole.DisplayRole:
            return QVariant()

        if orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(self.COLUMNS):
                return self.COLUMNS[section][0]

        return QVariant()

    def update_materials(
        self, materials: list[Any], type_names: dict[int, str] | None = None
    ) -> None:
        """Update the materials displayed in the model.

        Args:
            materials: New list of material objects
            type_names: Dictionary mapping type IDs to names

        """
        self.beginResetModel()
        self._materials = materials
        if type_names is not None:
            self._type_names = type_names
        self.endResetModel()

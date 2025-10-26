"""Qt table models for displaying EVE Online data."""

from typing import Any, ClassVar

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt, QVariant

from src.models.eve import EveType
from src.utils import format_currency, format_mass, format_number, format_volume


class TypesTableModel(QAbstractTableModel):
    """Table model for displaying EVE types."""

    COLUMNS: ClassVar[list[tuple[str, str]]] = [
        ("ID", "id"),
        ("Name", "name"),
        ("Group ID", "group_id"),
        ("Volume", "volume"),
        ("Mass", "mass"),
        ("Base Price", "base_price"),
        ("Published", "published"),
    ]

    def __init__(self, types: list[EveType] | None = None):
        """Initialize the model.

        Args:
            types: List of EveType objects to display

        """
        super().__init__()
        self._types = types or []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        """Return the number of rows."""
        if parent.isValid():
            return 0
        return len(self._types)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        """Return the number of columns."""
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

        value = getattr(eve_type, attr_name, None)

        # Special formatting for specific columns
        if attr_name == "name" and value is not None and hasattr(value, "en"):
            return value.en
        elif attr_name == "volume":
            return format_volume(value)
        elif attr_name == "mass":
            return format_mass(value)
        elif attr_name == "base_price":
            return format_currency(value)
        elif attr_name == "published":
            return "Yes" if value else "No"
        elif value is None:
            return "N/A"
        else:
            return str(value)

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

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        """Return the number of rows."""
        if parent.isValid():
            return 0
        return len(self._materials)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        """Return the number of columns."""
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
        elif attr_name == "quantity":
            value = getattr(material, attr_name, None)
            return format_number(value) if value is not None else "N/A"
        else:
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

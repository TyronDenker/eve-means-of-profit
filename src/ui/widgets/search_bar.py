"""Search bar widget for filtering data."""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QWidget


class SearchBar(QWidget):
    """Reusable search bar widget.

    Emits a signal when the search text changes.

    """

    # Signal emitted when search text changes
    search_changed = pyqtSignal(str)

    def __init__(self, placeholder: str = "Search...", parent=None):
        """Initialize the search bar.

        Args:
            placeholder: Placeholder text for the search input
            parent: Parent widget

        """
        super().__init__(parent)
        self._setup_ui(placeholder)

    def _setup_ui(self, placeholder: str) -> None:
        """Set up the UI components."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Search label
        label = QLabel("Search:")
        layout.addWidget(label)

        # Search input
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText(placeholder)
        self._search_input.textChanged.connect(self._on_search_changed)
        layout.addWidget(self._search_input)

        self.setLayout(layout)

    def _on_search_changed(self, text: str) -> None:
        """Handle search text changes."""
        self.search_changed.emit(text)

    def get_text(self) -> str:
        """Get the current search text.

        Returns:
            Current search text

        """
        return self._search_input.text()

    def clear(self) -> None:
        """Clear the search text."""
        self._search_input.clear()

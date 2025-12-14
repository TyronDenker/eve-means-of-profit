"""Unified styling system for EVE Means of Profit.

This module centralizes all widget and graph styling to ensure consistent
visual appearance across the application.

Usage:
    from ui.styles import AppStyles, GraphStyles, COLORS

    # Widget styling
    widget.setStyleSheet(AppStyles.BUTTON_PRIMARY)
    label.setStyleSheet(AppStyles.LABEL_INFO)

    # Graph styling
    color = GraphStyles.COLORS["Wallet"]
    symbol = GraphStyles.SYMBOLS["Wallet"]
    symbol_char = GraphStyles.SYMBOL_CHARS["Wallet"]

    # For delta labels with symbol+color
    html = GraphStyles.format_series_indicator("Wallet")
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True)
class ColorPalette:
    """Application color palette for consistent theming."""

    # Primary colors
    PRIMARY: str = "#0d7377"
    PRIMARY_HOVER: str = "#14a1a8"
    PRIMARY_PRESSED: str = "#0a5a5d"

    # Secondary colors
    SECONDARY: str = "#323232"
    SECONDARY_HOVER: str = "#454545"
    SECONDARY_PRESSED: str = "#252525"

    # Background colors
    BG_DARK: str = "#1a1a1a"
    BG_MEDIUM: str = "#1e1e1e"
    BG_LIGHT: str = "#2b2b2b"
    BG_LIGHTER: str = "#3d3d3d"

    # Text colors
    TEXT_PRIMARY: str = "#fff"
    TEXT_SECONDARY: str = "#ccc"
    TEXT_MUTED: str = "#888"
    TEXT_DISABLED: str = "#555"

    # Border colors
    BORDER_DARK: str = "#333"
    BORDER_MEDIUM: str = "#444"
    BORDER_LIGHT: str = "#555"
    BORDER_HIGHLIGHT: str = "#888"

    # Status colors
    SUCCESS: str = "#40a040"
    SUCCESS_HOVER: str = "#50c050"
    ERROR: str = "#c94040"
    ERROR_HOVER: str = "#e05050"
    WARNING: str = "#d97706"
    WARNING_HOVER: str = "#f59e0b"

    # Graph colors (EVE Online themed)
    WALLET: str = "#2ca02c"
    ASSETS: str = "#1f77b4"
    MARKET_ESCROW: str = "#ff7f0e"
    SELL_ORDERS: str = "#d62728"
    CONTRACT_COLLATERAL: str = "#9467bd"
    CONTRACTS: str = "#8c564b"
    INDUSTRY: str = "#17becf"
    PLEX: str = "#e377c2"
    TOTAL: str = "#000000"


# Singleton instance
COLORS = ColorPalette()


class AppStyles:
    """Centralized stylesheet definitions for the application."""

    # Button styles
    BUTTON_PRIMARY: ClassVar[str] = f"""
        QPushButton {{
            background-color: {COLORS.PRIMARY};
            color: white;
            border: none;
            border-radius: 4px;
            padding: 6px 12px;
            font-weight: bold;
        }}
        QPushButton:hover {{
            background-color: {COLORS.PRIMARY_HOVER};
        }}
        QPushButton:pressed {{
            background-color: {COLORS.PRIMARY_PRESSED};
        }}
        QPushButton:disabled {{
            background-color: {COLORS.SECONDARY};
            color: {COLORS.TEXT_DISABLED};
        }}
    """

    BUTTON_SECONDARY: ClassVar[str] = f"""
        QPushButton {{
            background-color: {COLORS.SECONDARY};
            color: white;
            border: 1px solid {COLORS.BORDER_LIGHT};
            border-radius: 4px;
            padding: 6px 12px;
            font-weight: bold;
        }}
        QPushButton:hover {{
            background-color: {COLORS.SECONDARY_HOVER};
            border: 1px solid {COLORS.BORDER_HIGHLIGHT};
        }}
        QPushButton:pressed {{
            background-color: {COLORS.SECONDARY_PRESSED};
        }}
    """

    BUTTON_WARNING: ClassVar[str] = f"""
        QPushButton {{
            background-color: {COLORS.WARNING};
            color: white;
            border: none;
            border-radius: 4px;
            padding: 6px 12px;
            font-weight: bold;
        }}
        QPushButton:hover {{
            background-color: {COLORS.WARNING_HOVER};
        }}
        QPushButton:pressed {{
            background-color: #b45309;
        }}
    """

    BUTTON_SMALL: ClassVar[str] = f"""
        QPushButton {{
            background-color: {COLORS.BG_LIGHTER};
            color: {COLORS.TEXT_SECONDARY};
            border: 1px solid {COLORS.BORDER_LIGHT};
            border-radius: 4px;
            padding: 4px 8px;
            font-size: 11px;
        }}
        QPushButton:hover {{
            background-color: {COLORS.SECONDARY_HOVER};
            border: 1px solid {COLORS.BORDER_HIGHLIGHT};
        }}
        QPushButton:pressed {{
            background-color: {COLORS.SECONDARY_PRESSED};
        }}
    """

    BUTTON_PLEX_PLUS: ClassVar[str] = f"""
        QPushButton {{
            background-color: {COLORS.BG_LIGHTER};
            color: {COLORS.TEXT_PRIMARY};
            border: 1px solid {COLORS.BORDER_LIGHT};
            border-radius: 4px;
            font-weight: bold;
            font-size: 14px;
        }}
        QPushButton:hover {{
            background-color: {COLORS.SUCCESS};
            border-color: {COLORS.SUCCESS_HOVER};
        }}
        QPushButton:pressed {{
            background-color: #308030;
        }}
    """

    BUTTON_PLEX_MINUS: ClassVar[str] = f"""
        QPushButton {{
            background-color: {COLORS.BG_LIGHTER};
            color: {COLORS.TEXT_PRIMARY};
            border: 1px solid {COLORS.BORDER_LIGHT};
            border-radius: 4px;
            font-weight: bold;
            font-size: 14px;
        }}
        QPushButton:hover {{
            background-color: {COLORS.ERROR};
            border-color: {COLORS.ERROR_HOVER};
        }}
        QPushButton:pressed {{
            background-color: #a03030;
        }}
    """

    # Panel and frame styles
    PANEL_DARK: ClassVar[str] = f"""
        QFrame {{
            background-color: {COLORS.BG_LIGHT};
            border: 1px solid {COLORS.BORDER_LIGHT};
            border-radius: 4px;
        }}
        QLabel {{
            color: {COLORS.TEXT_SECONDARY};
        }}
        QPushButton {{
            background-color: {COLORS.BG_LIGHTER};
            color: {COLORS.TEXT_SECONDARY};
            border: 1px solid {COLORS.BORDER_LIGHT};
            border-radius: 4px;
            padding: 4px 8px;
        }}
        QPushButton:hover {{
            background-color: {COLORS.SECONDARY_HOVER};
            border: 1px solid {COLORS.BORDER_HIGHLIGHT};
        }}
        QPushButton:pressed {{
            background-color: {COLORS.SECONDARY_PRESSED};
        }}
        QDateEdit {{
            background-color: {COLORS.BG_LIGHTER};
            color: {COLORS.TEXT_SECONDARY};
            border: 1px solid {COLORS.BORDER_LIGHT};
            border-radius: 4px;
            padding: 2px 4px;
        }}
    """

    ACCOUNT_GROUP: ClassVar[str] = f"""
        AccountGroupWidget {{
            background-color: {COLORS.BG_MEDIUM};
            border: 2px solid {COLORS.BORDER_MEDIUM};
            border-radius: 6px;
            padding: 2px;
        }}
    """

    CHARACTER_CARD: ClassVar[str] = f"""
        CharacterCard {{
            background-color: {COLORS.BG_LIGHT};
            border: 1px solid {COLORS.BORDER_LIGHT};
            border-radius: 4px;
        }}
        CharacterCard:hover {{
            border: 1px solid {COLORS.BORDER_HIGHLIGHT};
        }}
    """

    # Input styles
    SPINBOX: ClassVar[str] = f"""
        QSpinBox {{
            background-color: {COLORS.BG_LIGHT};
            color: {COLORS.TEXT_PRIMARY};
            border: 1px solid {COLORS.BORDER_LIGHT};
            border-radius: 4px;
            padding: 2px 4px;
            font-size: 12px;
        }}
        QSpinBox:hover {{
            border: 1px solid {COLORS.PRIMARY};
        }}
        QSpinBox:focus {{
            border: 1px solid {COLORS.PRIMARY_HOVER};
            background-color: {COLORS.BG_LIGHTER};
        }}
        QSpinBox::up-button, QSpinBox::down-button {{
            background-color: {COLORS.BG_LIGHTER};
            border: none;
            width: 14px;
        }}
        QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
            background-color: {COLORS.PRIMARY};
        }}
    """

    DOUBLE_SPINBOX: ClassVar[str] = f"""
        QDoubleSpinBox {{
            background-color: {COLORS.BG_LIGHT};
            color: {COLORS.TEXT_PRIMARY};
            border: 1px solid {COLORS.BORDER_LIGHT};
            border-radius: 4px;
            padding: 2px 4px;
        }}
        QDoubleSpinBox:hover {{
            border: 1px solid {COLORS.PRIMARY};
        }}
        QDoubleSpinBox:focus {{
            border: 1px solid {COLORS.PRIMARY_HOVER};
        }}
    """

    # Checkbox styles with gridicons checkmark SVG
    CHECKBOX: ClassVar[str] = f"""
        QCheckBox {{
            color: {COLORS.TEXT_SECONDARY};
            spacing: 6px;
            font-size: 11px;
        }}
        QCheckBox::indicator {{
            width: 16px;
            height: 16px;
            border: 2px solid {COLORS.BORDER_LIGHT};
            border-radius: 3px;
            background-color: {COLORS.BG_LIGHT};
        }}
        QCheckBox::indicator:checked {{
            background-color: {COLORS.PRIMARY};
            border-color: {COLORS.PRIMARY_HOVER};
            image: url(data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxZW0iIGhlaWdodD0iMWVtIiB2aWV3Qm94PSIwIDAgMjQgMjQiPjxwYXRoIGZpbGw9IndoaXRlIiBkPSJtOSAxOS40MTRsLTYuNzA3LTYuNzA3bDEuNDE0LTEuNDE0TDkgMTYuNTg2TDIwLjI5MyA1LjI5M2wxLjQxNCAxLjQxNHoiLz48L3N2Zz4=);
        }}
        QCheckBox::indicator:hover {{
            border-color: {COLORS.BORDER_HIGHLIGHT};
            background-color: {COLORS.BG_LIGHTER};
        }}
        QCheckBox::indicator:checked:hover {{
            background-color: {COLORS.PRIMARY_HOVER};
            border-color: #20c0c8;
            image: url(data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxZW0iIGhlaWdodD0iMWVtIiB2aWV3Qm94PSIwIDAgMjQgMjQiPjxwYXRoIGZpbGw9IndoaXRlIiBkPSJtOSAxOS40MTRsLTYuNzA3LTYuNzA3bDEuNDE0LTEuNDE0TDkgMTYuNTg2TDIwLjI5MyA1LjI5M2wxLjQxNCAxLjQxNHoiLz48L3N2Zz4=);
        }}
        QCheckBox::indicator:disabled {{
            background-color: {COLORS.BG_DARK};
            border-color: {COLORS.BORDER_DARK};
        }}
    """

    # Table styles
    TABLE: ClassVar[str] = f"""
        QTableView {{
            background-color: {COLORS.BG_LIGHT};
            color: {COLORS.TEXT_SECONDARY};
            border: 1px solid {COLORS.BORDER_MEDIUM};
            gridline-color: {COLORS.BORDER_DARK};
            selection-background-color: {COLORS.PRIMARY};
            selection-color: white;
        }}
        QTableView::item {{
            padding: 2px 4px;
        }}
        QHeaderView::section {{
            background-color: {COLORS.BG_MEDIUM};
            color: {COLORS.TEXT_SECONDARY};
            padding: 4px;
            border: 1px solid {COLORS.BORDER_DARK};
            font-weight: bold;
        }}
    """

    # Calendar popup styles
    CALENDAR: ClassVar[str] = f"""
        QCalendarWidget {{
            background-color: {COLORS.BG_LIGHT};
            color: {COLORS.TEXT_SECONDARY};
            min-width: 280px;
        }}
        QCalendarWidget QToolButton {{
            color: {COLORS.TEXT_SECONDARY};
            background-color: {COLORS.BG_LIGHTER};
            border: 1px solid {COLORS.BORDER_LIGHT};
            border-radius: 4px;
            padding: 4px 6px;
            margin: 2px;
            min-width: 24px;
        }}
        QCalendarWidget QToolButton:hover {{
            background-color: {COLORS.SECONDARY_HOVER};
        }}
        QCalendarWidget QToolButton:pressed {{
            background-color: {COLORS.SECONDARY_PRESSED};
        }}
        QCalendarWidget QToolButton#qt_calendar_prevmonth,
        QCalendarWidget QToolButton#qt_calendar_nextmonth {{
            min-width: 20px;
            max-width: 28px;
            padding: 4px;
        }}
        QCalendarWidget QToolButton#qt_calendar_monthbutton,
        QCalendarWidget QToolButton#qt_calendar_yearbutton {{
            min-width: 60px;
            padding: 4px 8px;
        }}
        QCalendarWidget QMenu {{
            background-color: {COLORS.BG_LIGHT};
            color: {COLORS.TEXT_SECONDARY};
        }}
        QCalendarWidget QSpinBox {{
            background-color: {COLORS.BG_LIGHTER};
            color: {COLORS.TEXT_SECONDARY};
            border: 1px solid {COLORS.BORDER_LIGHT};
            border-radius: 4px;
            min-width: 60px;
            padding: 2px 4px;
        }}
        QCalendarWidget QSpinBox::up-button,
        QCalendarWidget QSpinBox::down-button {{
            width: 16px;
            background-color: {COLORS.BG_LIGHTER};
            border: none;
        }}
        QCalendarWidget QSpinBox::up-button:hover,
        QCalendarWidget QSpinBox::down-button:hover {{
            background-color: {COLORS.PRIMARY};
        }}
        QCalendarWidget QAbstractItemView:enabled {{
            background-color: {COLORS.BG_LIGHT};
            color: {COLORS.TEXT_SECONDARY};
            selection-background-color: {COLORS.PRIMARY};
            selection-color: white;
        }}
        QCalendarWidget QAbstractItemView:disabled {{
            color: {COLORS.TEXT_DISABLED};
        }}
        QCalendarWidget QWidget#qt_calendar_navigationbar {{
            background-color: {COLORS.BG_MEDIUM};
            min-height: 32px;
        }}
    """

    # Label styles
    LABEL_HEADER: ClassVar[str] = f"""
        QLabel {{
            color: {COLORS.TEXT_PRIMARY};
            font-weight: bold;
            font-size: 12px;
            padding-top: 4px;
            border-bottom: 1px solid {COLORS.BORDER_LIGHT};
            padding-bottom: 2px;
        }}
    """

    LABEL_INFO: ClassVar[str] = f"""
        QLabel {{
            color: {COLORS.TEXT_MUTED};
            font-style: italic;
        }}
    """

    LABEL_VALUE: ClassVar[str] = f"""
        QLabel {{
            color: {COLORS.TEXT_SECONDARY};
            font-weight: bold;
        }}
    """

    # Scroll area styles
    SCROLL_AREA: ClassVar[str] = """
        QScrollArea {
            background-color: transparent;
            border: none;
        }
        QWidget {
            background-color: transparent;
        }
    """

    # Scrollbar styles (dark theme)
    SCROLLBAR: ClassVar[str] = f"""
        QScrollBar:vertical {{
            background-color: {COLORS.BG_DARK};
            width: 12px;
            margin: 0px;
            border: none;
            border-radius: 6px;
        }}
        QScrollBar::handle:vertical {{
            background-color: {COLORS.BG_LIGHTER};
            min-height: 30px;
            border-radius: 5px;
            margin: 2px;
        }}
        QScrollBar::handle:vertical:hover {{
            background-color: {COLORS.BORDER_LIGHT};
        }}
        QScrollBar::handle:vertical:pressed {{
            background-color: {COLORS.PRIMARY};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
            background: none;
        }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
            background: none;
        }}
        QScrollBar:horizontal {{
            background-color: {COLORS.BG_DARK};
            height: 12px;
            margin: 0px;
            border: none;
            border-radius: 6px;
        }}
        QScrollBar::handle:horizontal {{
            background-color: {COLORS.BG_LIGHTER};
            min-width: 30px;
            border-radius: 5px;
            margin: 2px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background-color: {COLORS.BORDER_LIGHT};
        }}
        QScrollBar::handle:horizontal:pressed {{
            background-color: {COLORS.PRIMARY};
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0px;
            background: none;
        }}
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
            background: none;
        }}
    """

    # Combobox styles
    COMBOBOX: ClassVar[str] = f"""
        QComboBox {{
            background-color: {COLORS.BG_LIGHT};
            color: {COLORS.TEXT_SECONDARY};
            border: 1px solid {COLORS.BORDER_LIGHT};
            border-radius: 4px;
            padding: 4px 8px;
            min-height: 20px;
        }}
        QComboBox:hover {{
            border: 1px solid {COLORS.PRIMARY};
        }}
        QComboBox:focus {{
            border: 1px solid {COLORS.PRIMARY_HOVER};
        }}
        QComboBox::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 20px;
            border-left: 1px solid {COLORS.BORDER_LIGHT};
            border-top-right-radius: 3px;
            border-bottom-right-radius: 3px;
            background-color: {COLORS.BG_LIGHTER};
        }}
        QComboBox::down-arrow {{
            width: 10px;
            height: 10px;
            image: url(data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTAiIGhlaWdodD0iMTAiIHZpZXdCb3g9IjAgMCAxMCAxMCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cGF0aCBkPSJNIDIgMyBMIDUgNyBMIDggMyIgc3Ryb2tlPSIjY2NjIiBzdHJva2Utd2lkdGg9IjEuNSIgZmlsbD0ibm9uZSIvPjwvc3ZnPg==);
        }}
        QComboBox QAbstractItemView {{
            background-color: {COLORS.BG_LIGHT};
            color: {COLORS.TEXT_SECONDARY};
            border: 1px solid {COLORS.BORDER_LIGHT};
            selection-background-color: {COLORS.PRIMARY};
            selection-color: white;
            outline: none;
        }}
    """

    # List widget styles
    LIST_WIDGET: ClassVar[str] = f"""
        QListWidget {{
            background-color: {COLORS.BG_MEDIUM};
            border: 1px solid {COLORS.BORDER_MEDIUM};
            border-radius: 4px;
        }}
        QListWidget::item {{
            padding: 6px;
            border-bottom: 1px solid {COLORS.BORDER_DARK};
        }}
        QListWidget::item:selected {{
            background-color: {COLORS.PRIMARY};
        }}
        QListWidget::item:hover {{
            background-color: {COLORS.BG_LIGHT};
        }}
    """

    # Progress bar styles
    PROGRESS_BAR: ClassVar[str] = f"""
        QProgressBar {{
            border: 1px solid {COLORS.BORDER_LIGHT};
            border-radius: 4px;
            text-align: center;
            background-color: {COLORS.BG_LIGHT};
            color: {COLORS.TEXT_SECONDARY};
        }}
        QProgressBar::chunk {{
            background-color: {COLORS.SUCCESS};
            border-radius: 2px;
        }}
    """

    # Line edit styles
    LINE_EDIT: ClassVar[str] = f"""
        QLineEdit {{
            background-color: {COLORS.BG_LIGHT};
            color: {COLORS.TEXT_PRIMARY};
            border: 1px solid {COLORS.BORDER_LIGHT};
            border-radius: 4px;
            padding: 4px 8px;
        }}
        QLineEdit:hover {{
            border: 1px solid {COLORS.PRIMARY};
        }}
        QLineEdit:focus {{
            border: 1px solid {COLORS.PRIMARY_HOVER};
            background-color: {COLORS.BG_LIGHTER};
        }}
        QLineEdit:disabled {{
            background-color: {COLORS.BG_DARK};
            color: {COLORS.TEXT_DISABLED};
        }}
    """

    # Dialog styles
    DIALOG: ClassVar[str] = f"""
        QDialog {{
            background-color: {COLORS.BG_MEDIUM};
        }}
        QLabel {{
            color: {COLORS.TEXT_SECONDARY};
        }}
    """

    # Group box styles
    GROUP_BOX: ClassVar[str] = f"""
        QGroupBox {{
            font-weight: bold;
            border: 1px solid {COLORS.BORDER_LIGHT};
            border-radius: 4px;
            margin-top: 8px;
            padding-top: 8px;
            background-color: {COLORS.BG_LIGHT};
            color: {COLORS.TEXT_PRIMARY};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 4px;
            background-color: {COLORS.BG_LIGHT};
            color: {COLORS.TEXT_PRIMARY};
        }}
    """

    # Date edit with calendar popup - enhanced with arrow buttons
    DATE_EDIT: ClassVar[str] = f"""
        QDateEdit {{
            background-color: {COLORS.BG_LIGHTER};
            color: {COLORS.TEXT_SECONDARY};
            border: 1px solid {COLORS.BORDER_LIGHT};
            border-radius: 4px;
            padding: 2px 4px;
        }}
        QDateEdit:hover {{
            border: 1px solid {COLORS.PRIMARY};
        }}
        QDateEdit::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: center right;
            width: 20px;
            border-left: 1px solid {COLORS.BORDER_LIGHT};
            background-color: {COLORS.BG_LIGHTER};
        }}
        QDateEdit::down-arrow {{
            width: 10px;
            height: 10px;
            image: url(data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTAiIGhlaWdodD0iMTAiIHZpZXdCb3g9IjAgMCAxMCAxMCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cGF0aCBkPSJNIDIgMyBMIDUgNyBMIDggMyIgc3Ryb2tlPSIjY2NjIiBzdHJva2Utd2lkdGg9IjEuNSIgZmlsbD0ibm9uZSIvPjwvc3ZnPg==);
        }}
    """

    # Enhanced calendar with visible year spinbox up/down arrows
    CALENDAR_ENHANCED: ClassVar[str] = f"""
        QCalendarWidget {{
            background-color: {COLORS.BG_LIGHT};
            color: {COLORS.TEXT_SECONDARY};
            min-width: 280px;
        }}
        QCalendarWidget QToolButton {{
            color: {COLORS.TEXT_SECONDARY};
            background-color: {COLORS.BG_LIGHTER};
            border: 1px solid {COLORS.BORDER_LIGHT};
            border-radius: 4px;
            padding: 4px 6px;
            margin: 2px;
            min-width: 24px;
        }}
        QCalendarWidget QToolButton:hover {{
            background-color: {COLORS.SECONDARY_HOVER};
        }}
        QCalendarWidget QToolButton:pressed {{
            background-color: {COLORS.SECONDARY_PRESSED};
        }}
        QCalendarWidget QToolButton#qt_calendar_prevmonth,
        QCalendarWidget QToolButton#qt_calendar_nextmonth {{
            min-width: 20px;
            max-width: 28px;
            padding: 4px;
        }}
        QCalendarWidget QToolButton#qt_calendar_monthbutton,
        QCalendarWidget QToolButton#qt_calendar_yearbutton {{
            min-width: 60px;
            padding: 4px 8px;
        }}
        QCalendarWidget QMenu {{
            background-color: {COLORS.BG_LIGHT};
            color: {COLORS.TEXT_SECONDARY};
        }}
        QCalendarWidget QSpinBox {{
            background-color: {COLORS.BG_LIGHTER};
            color: {COLORS.TEXT_SECONDARY};
            border: 1px solid {COLORS.BORDER_LIGHT};
            border-radius: 4px;
            min-width: 60px;
            padding: 2px 4px;
        }}
        QCalendarWidget QSpinBox::up-button {{
            subcontrol-origin: border;
            subcontrol-position: top right;
            width: 16px;
            height: 12px;
            background-color: {COLORS.BG_LIGHTER};
            border: 1px solid {COLORS.BORDER_LIGHT};
            border-top-right-radius: 3px;
        }}
        QCalendarWidget QSpinBox::up-button:hover {{
            background-color: {COLORS.PRIMARY};
        }}
        QCalendarWidget QSpinBox::up-arrow {{
            width: 8px;
            height: 8px;
            image: url(data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iOCIgaGVpZ2h0PSI4IiB2aWV3Qm94PSIwIDAgOCA4IiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciPjxwYXRoIGQ9Ik0gMSA1IEwgNCAyIEwgNyA1IiBzdHJva2U9IiNjY2MiIHN0cm9rZS13aWR0aD0iMS41IiBmaWxsPSJub25lIi8+PC9zdmc+);
        }}
        QCalendarWidget QSpinBox::down-button {{
            subcontrol-origin: border;
            subcontrol-position: bottom right;
            width: 16px;
            height: 12px;
            background-color: {COLORS.BG_LIGHTER};
            border: 1px solid {COLORS.BORDER_LIGHT};
            border-bottom-right-radius: 3px;
        }}
        QCalendarWidget QSpinBox::down-button:hover {{
            background-color: {COLORS.PRIMARY};
        }}
        QCalendarWidget QSpinBox::down-arrow {{
            width: 8px;
            height: 8px;
            image: url(data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iOCIgaGVpZ2h0PSI4IiB2aWV3Qm94PSIwIDAgOCA4IiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciPjxwYXRoIGQ9Ik0gMSAzIEwgNCA2IEwgNyAzIiBzdHJva2U9IiNjY2MiIHN0cm9rZS13aWR0aD0iMS41IiBmaWxsPSJub25lIi8+PC9zdmc+);
        }}
        QCalendarWidget QAbstractItemView:enabled {{
            background-color: {COLORS.BG_LIGHT};
            color: {COLORS.TEXT_SECONDARY};
            selection-background-color: {COLORS.PRIMARY};
            selection-color: white;
        }}
        QCalendarWidget QAbstractItemView:disabled {{
            color: {COLORS.TEXT_DISABLED};
        }}
        QCalendarWidget QWidget#qt_calendar_navigationbar {{
            background-color: {COLORS.BG_MEDIUM};
            min-height: 32px;
        }}
    """

    # Global application stylesheet (can be applied to QApplication)
    GLOBAL_STYLESHEET: ClassVar[str] = f"""
        QWidget {{
            background-color: {COLORS.BG_MEDIUM};
            color: {COLORS.TEXT_SECONDARY};
        }}
        QScrollBar:vertical {{
            background-color: {COLORS.BG_DARK};
            width: 12px;
            margin: 0px;
            border: none;
            border-radius: 6px;
        }}
        QScrollBar::handle:vertical {{
            background-color: {COLORS.BG_LIGHTER};
            min-height: 30px;
            border-radius: 5px;
            margin: 2px;
        }}
        QScrollBar::handle:vertical:hover {{
            background-color: {COLORS.BORDER_LIGHT};
        }}
        QScrollBar::handle:vertical:pressed {{
            background-color: {COLORS.PRIMARY};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
            background: none;
        }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
            background: none;
        }}
        QScrollBar:horizontal {{
            background-color: {COLORS.BG_DARK};
            height: 12px;
            margin: 0px;
            border: none;
            border-radius: 6px;
        }}
        QScrollBar::handle:horizontal {{
            background-color: {COLORS.BG_LIGHTER};
            min-width: 30px;
            border-radius: 5px;
            margin: 2px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background-color: {COLORS.BORDER_LIGHT};
        }}
        QScrollBar::handle:horizontal:pressed {{
            background-color: {COLORS.PRIMARY};
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0px;
            background: none;
        }}
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
            background: none;
        }}
        QToolTip {{
            background-color: {COLORS.BG_LIGHT};
            color: {COLORS.TEXT_PRIMARY};
            border: 1px solid {COLORS.BORDER_LIGHT};
            padding: 4px;
            border-radius: 4px;
        }}
    """


class GraphStyles:
    """Styling constants for pyqtgraph plots."""

    # Color map for graph series
    COLORS: ClassVar[dict[str, str]] = {
        "Wallet": COLORS.WALLET,
        "Assets": COLORS.ASSETS,
        "Market Escrow": COLORS.MARKET_ESCROW,
        "Sell Orders": COLORS.SELL_ORDERS,
        "Contract Collateral": COLORS.CONTRACT_COLLATERAL,
        "Contracts": COLORS.CONTRACTS,
        "Industry": COLORS.INDUSTRY,
        "PLEX": COLORS.PLEX,
        "Total": COLORS.TOTAL,
    }

    # Line styles (Qt.PenStyle names)
    LINE_STYLES: ClassVar[dict[str, str]] = {
        "Wallet": "solid",
        "Assets": "solid",
        "Market Escrow": "dash",
        "Sell Orders": "dot",
        "Contract Collateral": "dashdot",
        "Contracts": "solid",
        "Industry": "dash",
        "PLEX": "dot",
        "Total": "solid",
    }

    # Point symbols (pyqtgraph symbol codes)
    SYMBOLS: ClassVar[dict[str, str]] = {
        "Wallet": "o",  # circle
        "Assets": "s",  # square
        "Market Escrow": "t",  # triangle up
        "Sell Orders": "d",  # diamond
        "Contract Collateral": "+",  # plus
        "Contracts": "p",  # pentagon
        "Industry": "h",  # hexagon
        "PLEX": "star",  # star
        "Total": "s",  # square (larger for emphasis)
    }

    # Unicode characters representing the symbols for text display
    # These map to the same shapes as SYMBOLS but as displayable characters
    SYMBOL_CHARS: ClassVar[dict[str, str]] = {
        "Wallet": "●",  # filled circle (o)
        "Assets": "■",  # filled square (s)
        "Market Escrow": "▲",  # filled triangle up (t)
        "Sell Orders": "◆",  # filled diamond (d)
        "Contract Collateral": "+",  # plus (+)
        "Contracts": "⬠",  # pentagon (p)
        "Industry": "⬡",  # hexagon (h)
        "PLEX": "★",  # star (star)
        "Total": "■",  # filled square for total
    }

    # Line widths
    DEFAULT_LINE_WIDTH: ClassVar[float] = 1.5
    TOTAL_LINE_WIDTH: ClassVar[float] = 2.5

    # Symbol sizes
    DEFAULT_SYMBOL_SIZE: ClassVar[int] = 6
    TOTAL_SYMBOL_SIZE: ClassVar[int] = 8

    # Background color (white for graphs)
    BACKGROUND: ClassVar[str] = "w"

    # Grid alpha
    GRID_ALPHA: ClassVar[float] = 0.3

    @classmethod
    def format_series_indicator(cls, label: str) -> str:
        """Format a series indicator with colored symbol character for use in labels.

        Returns an HTML span with the symbol character in the series color.

        Args:
            label: The series label (e.g., "Wallet", "Assets")

        Returns:
            HTML string like '<span style="color:#2ca02c">●</span>'
        """
        color = cls.COLORS.get(label, "#888888")
        symbol_char = cls.SYMBOL_CHARS.get(label, "●")
        return f'<span style="color:{color}">{symbol_char}</span>'

    @classmethod
    def get_category_fields(cls) -> list[tuple[str, str]]:
        """Get the standard category fields for networth tracking.

        Returns:
            List of (field_name, display_label) tuples

        Note: PLEX is now tracked at account level via account_plex_snapshots,
              not in character snapshots.
        """
        return [
            ("wallet_balance", "Wallet"),
            ("total_asset_value", "Assets"),
            ("market_escrow", "Market Escrow"),
            ("market_sell_value", "Sell Orders"),
            ("contract_collateral", "Contract Collateral"),
            ("contract_value", "Contracts"),
            ("industry_job_value", "Industry"),
            # plex_vault removed - PLEX is now account-level data
        ]

"""Reusable widget that renders a character portrait and optional corp/alliance logos.

Public API:
- class CharacterItemWidget(QWidget)
  - set_portrait(img_data: bytes | bytearray | memoryview | None) -> None
  - set_corp_logo(img_data: bytes | bytearray | memoryview | None) -> None
  - set_alliance_logo(img_data: bytes | bytearray | memoryview | None) -> None

This module is self-contained and only depends on PyQt6. It guards against
invalid image data and preserves the styling and sizes from the original
inline implementation.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget


class CharacterItemWidget(QWidget):
    """Widget for a single character list item.

    Renders a 128x128 portrait and, if available on the ``character`` object,
    64x64 corporation and alliance logos with their respective names.

    The widget exposes setters to update the images from raw bytes and is
    resilient to invalid data (it will safely ignore bad images and keep
    placeholders).

    Parameters:
        character:
            An object with attributes like ``character_name``, ``character_id``,
            ``corporation_name``, ``alliance_name`` (missing ones are handled).
        parent:
            Optional parent widget.
    """

    def __init__(self, character: object, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.character = character

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # Portrait
        self.portrait_label = QLabel()
        self.portrait_label.setFixedSize(128, 128)
        self.portrait_label.setScaledContents(True)
        self.portrait_label.setStyleSheet("border: 2px solid #555; background: #222;")
        self._set_placeholder_portrait()
        layout.addWidget(self.portrait_label, alignment=Qt.AlignmentFlag.AlignCenter)

        # Character name
        name_value = getattr(
            character, "character_name", str(getattr(character, "character_id", ""))
        )
        name_label = QLabel(name_value)
        name_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(name_label)

        # Corporation section (optional)
        if getattr(character, "corporation_name", None):
            self.corp_logo_label = QLabel()
            self.corp_logo_label.setFixedSize(64, 64)
            self.corp_logo_label.setScaledContents(True)
            self.corp_logo_label.setStyleSheet("border: 1px solid #555;")
            self._set_placeholder_logo(self.corp_logo_label)

            corp_container = QWidget()
            corp_layout = QVBoxLayout(corp_container)
            corp_layout.setContentsMargins(0, 0, 0, 0)
            corp_layout.setSpacing(2)
            corp_layout.addWidget(
                self.corp_logo_label, alignment=Qt.AlignmentFlag.AlignCenter
            )
            corp_name = QLabel(getattr(character, "corporation_name"))
            corp_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            corp_name.setWordWrap(True)
            corp_layout.addWidget(corp_name)
            layout.addWidget(corp_container)
        else:
            self.corp_logo_label = None

        # Alliance section (optional)
        if getattr(character, "alliance_name", None):
            self.alliance_logo_label = QLabel()
            self.alliance_logo_label.setFixedSize(64, 64)
            self.alliance_logo_label.setScaledContents(True)
            self.alliance_logo_label.setStyleSheet("border: 1px solid #555;")
            self._set_placeholder_logo(self.alliance_logo_label)

            alliance_container = QWidget()
            alliance_layout = QVBoxLayout(alliance_container)
            alliance_layout.setContentsMargins(0, 0, 0, 0)
            alliance_layout.setSpacing(2)
            alliance_layout.addWidget(
                self.alliance_logo_label, alignment=Qt.AlignmentFlag.AlignCenter
            )
            alliance_name = QLabel(getattr(character, "alliance_name"))
            alliance_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            alliance_name.setWordWrap(True)
            alliance_layout.addWidget(alliance_name)
            layout.addWidget(alliance_container)
        else:
            self.alliance_logo_label = None

        layout.addStretch()

    # --- Placeholders -----------------------------------------------------
    def _set_placeholder_portrait(self) -> None:
        pixmap = QPixmap(128, 128)
        pixmap.fill(Qt.GlobalColor.darkGray)
        self.portrait_label.setPixmap(pixmap)

    def _set_placeholder_logo(self, label: QLabel) -> None:
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.darkGray)
        label.setPixmap(pixmap)

    # --- Public API: image setters ----------------------------------------
    def set_portrait(self, img_data: bytes | bytearray | memoryview | None) -> None:
        """Set the character portrait image from raw bytes.

        Silently ignores invalid data and keeps the current/placeholder image.
        """
        pixmap = self._pixmap_from_data(img_data)
        if pixmap is not None:
            self.portrait_label.setPixmap(pixmap)

    def set_corp_logo(self, img_data: bytes | bytearray | memoryview | None) -> None:
        """Set the corporation logo image from raw bytes, if applicable."""
        if self.corp_logo_label is None:
            return
        pixmap = self._pixmap_from_data(img_data)
        if pixmap is not None:
            self.corp_logo_label.setPixmap(pixmap)

    def set_alliance_logo(
        self, img_data: bytes | bytearray | memoryview | None
    ) -> None:
        """Set the alliance logo image from raw bytes, if applicable."""
        if self.alliance_logo_label is None:
            return
        pixmap = self._pixmap_from_data(img_data)
        if pixmap is not None:
            self.alliance_logo_label.setPixmap(pixmap)

    # --- Helpers -----------------------------------------------------------
    @staticmethod
    def _pixmap_from_data(
        img_data: bytes | bytearray | memoryview | None,
    ) -> QPixmap | None:
        """Create a QPixmap from raw bytes-like data.

        Returns None if ``img_data`` is None, is not bytes-like, or fails to
        decode into an image.
        """
        if img_data is None:
            return None
        try:
            if not isinstance(img_data, (bytes, bytearray, memoryview)):
                return None
            data = bytes(img_data)
            pixmap = QPixmap()
            if pixmap.loadFromData(data) and not pixmap.isNull():
                return pixmap
        except Exception:
            # Swallow errors to avoid UI crashes on corrupt data
            return None
        return None

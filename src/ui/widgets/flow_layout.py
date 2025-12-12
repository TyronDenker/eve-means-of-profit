# src/ui/widgets/flow_layout.py
from PyQt6.QtCore import QPoint, QRect, QSize, Qt
from PyQt6.QtWidgets import QLayout


class FlowLayout(QLayout):
    def __init__(self, parent=None):
        super().__init__(parent)
        if parent is not None:
            self.setContentsMargins(0, 0, 0, 0)
        self._item_list = []
        self._h_spacing = -1
        self._v_spacing = -1

    def __del__(self):
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)

    def addItem(self, item):
        self._item_list.append(item)

    def count(self):
        return len(self._item_list)

    def itemAt(self, index):
        if 0 <= index < len(self._item_list):
            return self._item_list[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._item_list):
            return self._item_list.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        height = self._do_layout(QRect(0, 0, width, 0), True)
        return height

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._item_list:
            size = size.expandedTo(item.minimumSize())
        margin, _, _, _ = self.getContentsMargins()
        size += QSize(2 * margin, 2 * margin)
        return size

    def setHorizontalSpacing(self, spacing):
        self._h_spacing = spacing

    def horizontalSpacing(self):
        if self._h_spacing >= 0:
            return self._h_spacing
        return self.spacing()

    def setVerticalSpacing(self, spacing):
        self._v_spacing = spacing

    def verticalSpacing(self):
        if self._v_spacing >= 0:
            return self._v_spacing
        return self.spacing()

    def _do_layout(self, rect, test_only):
        x = rect.x()
        y = rect.y()
        line_height = 0
        h_spacing = self.horizontalSpacing()
        v_spacing = self.verticalSpacing()

        for item in self._item_list:
            widget = item.widget()
            size_hint = item.sizeHint()
            next_x = x + size_hint.width() + h_spacing

            is_account_group = "AccountGroupWidget" in widget.metaObject().className()
            if is_account_group:
                if next_x - h_spacing > rect.right() and x > rect.x():
                    x = rect.x()
                    y = y + line_height + v_spacing
                    line_height = 0
            else:
                if next_x - h_spacing > rect.right() and line_height > 0:
                    x = rect.x()
                    y = y + line_height + v_spacing
                    line_height = 0

            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), size_hint))

            x = x + size_hint.width() + h_spacing
            line_height = max(line_height, size_hint.height())

        return y + line_height - rect.y()

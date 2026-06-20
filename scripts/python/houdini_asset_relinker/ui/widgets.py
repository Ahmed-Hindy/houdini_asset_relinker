"""Small reusable Qt widgets for the asset relinker UI."""

from __future__ import annotations

from houdini_asset_relinker.qt import QtCore, QtGui, QtWidgets
from houdini_asset_relinker.ui.qt_constants import BACKGROUND_ROLE


class StatWidget(QtWidgets.QFrame):
    """Compact summary stat display with a label and mutable value."""

    def __init__(self, label: str, value: str, parent: QtWidgets.QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("statFrame")

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)

        self.value_label = QtWidgets.QLabel(value, self)
        self.value_label.setObjectName("statValue")
        text_label = QtWidgets.QLabel(label, self)
        text_label.setObjectName("statLabel")

        layout.addWidget(self.value_label)
        layout.addWidget(text_label)

    def set_value(self, value: int) -> None:
        """Set the displayed stat value."""
        self.value_label.setText(str(value))


class StatusColorDelegate(QtWidgets.QStyledItemDelegate):
    """Custom item delegate that preserves model-defined backgrounds under stylesheets."""

    def paint(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> None:
        opt = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        # If the item is selected, let the default style paint the selection highlight
        if opt.state & QtWidgets.QStyle.State_Selected:
            super().paint(painter, option, index)
            return

        brush = index.data(BACKGROUND_ROLE)
        if brush is not None:
            painter.save()
            if not isinstance(brush, QtGui.QBrush):
                brush = QtGui.QBrush(brush)
            painter.fillRect(opt.rect, brush)
            painter.restore()

            # Clear background brush and remove widget association/style object
            # to bypass stylesheet overrides when painting text and decorations.
            opt.backgroundBrush = QtGui.QBrush(QtGui.QColor(0, 0, 0, 0))
            opt.widget = None
            if hasattr(opt, "styleObject"):
                opt.styleObject = None

        super().paint(painter, opt, index)

"""Small reusable Qt widgets for the asset relinker UI."""

from __future__ import annotations

from houdini_asset_relinker.qt import QtWidgets


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

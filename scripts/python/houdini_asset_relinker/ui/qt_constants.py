"""Qt constants shared by the asset relinker UI modules."""

from __future__ import annotations

from houdini_asset_relinker.qt import QtCore, QtGui, QtWidgets, qt_enum

DISPLAY_ROLE = qt_enum("ItemDataRole", "DisplayRole")
FOREGROUND_ROLE = qt_enum("ItemDataRole", "ForegroundRole")
TOOLTIP_ROLE = qt_enum("ItemDataRole", "ToolTipRole")
USER_ROLE = qt_enum("ItemDataRole", "UserRole")
HORIZONTAL = qt_enum("Orientation", "Horizontal")
CASE_INSENSITIVE = qt_enum("CaseSensitivity", "CaseInsensitive")
CUSTOM_CONTEXT_MENU = qt_enum("ContextMenuPolicy", "CustomContextMenu")
ASCENDING_ORDER = qt_enum("SortOrder", "AscendingOrder")
WAIT_CURSOR = qt_enum("CursorShape", "WaitCursor")
ARROW_CURSOR = qt_enum("CursorShape", "ArrowCursor")
TOOL_BUTTON_TEXT_ONLY = qt_enum("ToolButtonStyle", "ToolButtonTextOnly")
INVALID_INDEX = QtCore.QModelIndex()

try:
    ACTION_CLASS = QtGui.QAction
    SELECT_ROWS = QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
    SINGLE_SELECTION = QtWidgets.QAbstractItemView.SelectionMode.SingleSelection
    HEADER_INTERACTIVE = QtWidgets.QHeaderView.ResizeMode.Interactive
    MESSAGE_OK = QtWidgets.QMessageBox.StandardButton.Ok
    MESSAGE_CANCEL = QtWidgets.QMessageBox.StandardButton.Cancel
    MESSAGE_CRITICAL = QtWidgets.QMessageBox.Icon.Critical
except AttributeError:
    ACTION_CLASS = QtWidgets.QAction
    SELECT_ROWS = QtWidgets.QAbstractItemView.SelectRows
    SINGLE_SELECTION = QtWidgets.QAbstractItemView.SingleSelection
    HEADER_INTERACTIVE = QtWidgets.QHeaderView.Interactive
    MESSAGE_OK = QtWidgets.QMessageBox.Ok
    MESSAGE_CANCEL = QtWidgets.QMessageBox.Cancel
    MESSAGE_CRITICAL = QtWidgets.QMessageBox.Critical

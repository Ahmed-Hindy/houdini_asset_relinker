"""Stylesheet for the asset relinker Qt window."""

ASSET_RELINKER_STYLESHEET = """
QMainWindow, QWidget {
    background: #202326;
    color: #e8eaed;
    font-size: 10pt;
}
QToolBar {
    background: #292d31;
    border: 0;
    spacing: 6px;
    padding: 5px;
}
QToolBar QToolButton {
    min-width: 120px;
    padding: 7px 12px;
}
QLineEdit, QPlainTextEdit, QComboBox {
    background: #16181b;
    border: 1px solid #3c4248;
    border-radius: 4px;
    padding: 5px;
    selection-background-color: #4a7ebf;
}
QPushButton, QToolButton {
    background: #3b4652;
    border: 1px solid #56616d;
    border-radius: 4px;
    padding: 6px 10px;
}
QPushButton:hover, QToolButton:hover {
    background: #465665;
}
QPushButton:disabled {
    color: #80868b;
    background: #2b3035;
}
QTableView {
    background: #17191c;
    alternate-background-color: #1d2024;
    border: 1px solid #343a40;
    gridline-color: #30363c;
    selection-background-color: #365577;
    selection-color: #ffffff;
}
QHeaderView::section {
    background: #2d3339;
    border: 0;
    border-right: 1px solid #3d454d;
    padding: 5px;
}
QTabWidget::pane {
    border: 1px solid #343a40;
}
QTabBar::tab {
    background: #2a2f35;
    border: 1px solid #343a40;
    padding: 7px 14px;
}
QTabBar::tab:selected {
    background: #39434d;
}
QFrame#statFrame {
    background: #292f35;
    border: 1px solid #3b444d;
    border-radius: 5px;
    min-width: 96px;
}
QLabel#statValue {
    font-size: 18pt;
    font-weight: 700;
}
QLabel#statLabel {
    color: #aab0b6;
}
"""

"""Stylesheet for the asset relinker Qt window."""

ASSET_RELINKER_STYLESHEET = """
QMainWindow, QWidget {
    background: #202326;
    color: #e8eaed;
    font-size: 10pt;
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
QPushButton#primaryButton {
    background: #4a637d;
    border-color: #6f879f;
    font-weight: 600;
}
QPushButton#primaryButton:hover {
    background: #55718d;
}
QPushButton#applyButton {
    background: #4d5a64;
    border-color: #6b747d;
    font-weight: 600;
}
QPushButton#applyButton:hover {
    background: #5c6974;
}
QPushButton#secondaryButton {
    background: #303841;
    border-color: #48515a;
}
QPushButton#secondaryButton:hover {
    background: #3a4650;
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
QWidget#scanBar {
    background: #262b30;
    border: 1px solid #343c44;
    border-radius: 4px;
    padding: 6px;
}
QLabel#sectionLabel {
    color: #d7dde3;
    font-weight: 700;
    padding-right: 4px;
}
QLabel#summaryLabel {
    color: #aeb7c0;
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

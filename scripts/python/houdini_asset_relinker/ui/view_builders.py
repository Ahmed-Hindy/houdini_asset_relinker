"""Widget builders for the asset relinker window."""

from __future__ import annotations

from dataclasses import dataclass

from houdini_asset_relinker.qt import QtGui, QtWidgets
from houdini_asset_relinker.ui.qt_constants import (
    ASCENDING_ORDER,
    CUSTOM_CONTEXT_MENU,
    HEADER_INTERACTIVE,
    SCROLL_PER_PIXEL,
    SELECT_ROWS,
    SINGLE_SELECTION,
)
from houdini_asset_relinker.ui.relink_state import (
    SCOPE_ALL_ROWS,
    SCOPE_MISSING_UNDER_ROOT,
    SCOPE_PATH_FAMILY,
    SCOPE_SELECTED_ROW,
    SCOPE_VISIBLE_ROWS,
)
from houdini_asset_relinker.ui.style import (
    ASSET_RELINKER_STYLESHEET,
    REPORT_TABLE_ALT_BASE_COLOR,
    REPORT_TABLE_BASE_COLOR,
    STATUS_COLOR_MISSING,
    STATUS_COLOR_NOT_UPDATABLE,
    STATUS_COLOR_READY,
)
from houdini_asset_relinker.ui.widgets import StatusColorDelegate

REFERENCE_PATH_FAMILY_COLUMN = 5


@dataclass(frozen=True)
class ScanBarWidgets:
    """Widgets created for the scan toolbar."""

    panel: QtWidgets.QWidget
    project_variable_edit: QtWidgets.QLineEdit
    include_all_refs_check: QtWidgets.QCheckBox
    include_hda_check: QtWidgets.QCheckBox
    recurse_locked_check: QtWidgets.QCheckBox
    scan_button: QtWidgets.QPushButton


@dataclass(frozen=True)
class ReferencePanelWidgets:
    """Widgets created for the reference table panel."""

    panel: QtWidgets.QWidget
    search_edit: QtWidgets.QLineEdit
    missing_only_check: QtWidgets.QCheckBox
    writable_only_check: QtWidgets.QCheckBox
    kind_combo: QtWidgets.QComboBox
    reset_filters_button: QtWidgets.QPushButton
    summary_label: QtWidgets.QLabel
    export_button: QtWidgets.QPushButton
    reference_table: QtWidgets.QTableView


@dataclass(frozen=True)
class RelinkPanelWidgets:
    """Widgets created for the relink panel."""

    panel: QtWidgets.QWidget
    find_edit: QtWidgets.QLineEdit
    replace_edit: QtWidgets.QLineEdit
    scope_combo: QtWidgets.QComboBox
    find_match_label: QtWidgets.QLabel
    case_sensitive_check: QtWidgets.QCheckBox
    include_hda_replace_check: QtWidgets.QCheckBox
    uninstall_old_hda_check: QtWidgets.QCheckBox
    normalize_button: QtWidgets.QPushButton
    apply_button: QtWidgets.QPushButton
    copy_report_button: QtWidgets.QPushButton
    report_table: QtWidgets.QTableView


@dataclass(frozen=True)
class DetailsPanelWidgets:
    """Widgets created for the selected-reference details panel."""

    panel: QtWidgets.QWidget
    detail_text: QtWidgets.QPlainTextEdit


@dataclass(frozen=True)
class MainWindowWidgets:
    """Top-level widgets created for the main relinker window."""

    central_widget: QtWidgets.QWidget
    main_splitter: QtWidgets.QSplitter
    status_label: QtWidgets.QLabel
    scan_bar: ScanBarWidgets
    reference_panel: ReferencePanelWidgets
    relink_panel: RelinkPanelWidgets
    details_panel: DetailsPanelWidgets


def build_main_window(
    owner: QtWidgets.QMainWindow, proxy_model: object, report_model: object
) -> MainWindowWidgets:
    """Build the full main-window layout."""
    central_widget = QtWidgets.QWidget(owner)
    owner.setCentralWidget(central_widget)
    main_layout = QtWidgets.QVBoxLayout(central_widget)
    main_layout.setContentsMargins(12, 12, 12, 12)
    main_layout.setSpacing(10)

    scan_bar = build_scan_bar(owner)
    main_layout.addWidget(scan_bar.panel)

    reference_panel = build_reference_panel(owner, proxy_model)
    relink_panel = build_relink_panel(owner, report_model)
    details_panel = build_details_panel(owner)

    side_panel = QtWidgets.QTabWidget(owner)
    side_panel.addTab(relink_panel.panel, "Relink")
    side_panel.addTab(details_panel.panel, "Selected Reference")

    main_splitter = QtWidgets.QSplitter(owner)
    main_splitter.addWidget(reference_panel.panel)
    main_splitter.addWidget(side_panel)
    main_splitter.setSizes([860, 420])
    main_layout.addWidget(main_splitter, 1)

    status_label = QtWidgets.QLabel(owner)
    owner.statusBar().addPermanentWidget(status_label, 1)
    owner.setStyleSheet(ASSET_RELINKER_STYLESHEET)

    return MainWindowWidgets(
        central_widget=central_widget,
        main_splitter=main_splitter,
        status_label=status_label,
        scan_bar=scan_bar,
        reference_panel=reference_panel,
        relink_panel=relink_panel,
        details_panel=details_panel,
    )


def build_scan_bar(parent: QtWidgets.QWidget) -> ScanBarWidgets:
    """Build the scene-scan toolbar."""
    panel = QtWidgets.QWidget(parent)
    panel.setObjectName("scanBar")
    layout = QtWidgets.QHBoxLayout(panel)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)

    project_variable_edit = QtWidgets.QLineEdit("HIP", parent)
    project_variable_edit.setMaximumWidth(90)
    project_variable_edit.setToolTip(
        "Houdini project variable passed to hou.fileReferences, usually HIP."
    )
    include_all_refs_check = QtWidgets.QCheckBox("All file refs", parent)
    include_all_refs_check.setChecked(True)
    include_all_refs_check.setToolTip(
        "Include all Houdini file references instead of only selected references."
    )
    include_hda_check = QtWidgets.QCheckBox("Loaded HDA libraries", parent)
    include_hda_check.setChecked(False)
    include_hda_check.setToolTip("Include loaded HDA library files in the scan.")
    recurse_locked_check = QtWidgets.QCheckBox("Locked-node contents", parent)
    recurse_locked_check.setChecked(False)
    recurse_locked_check.setToolTip(
        "Inspect child nodes inside locked assets when scanning file references."
    )

    scan_button = QtWidgets.QPushButton("Scan Scene", parent)
    scan_button.setObjectName("primaryButton")
    scan_button.setDefault(True)
    scan_button.setMinimumWidth(92)
    scan_button.setShortcut("F5")
    scan_button.setToolTip("Scan the current Houdini scene for external asset references.")

    section_label = QtWidgets.QLabel("Scene scan", parent)
    section_label.setObjectName("sectionLabel")
    layout.addWidget(section_label)
    layout.addWidget(QtWidgets.QLabel("Project var", parent))
    layout.addWidget(project_variable_edit)
    layout.addWidget(include_all_refs_check)
    layout.addWidget(include_hda_check)
    layout.addWidget(recurse_locked_check)
    layout.addStretch(1)
    layout.addWidget(scan_button)

    return ScanBarWidgets(
        panel=panel,
        project_variable_edit=project_variable_edit,
        include_all_refs_check=include_all_refs_check,
        include_hda_check=include_hda_check,
        recurse_locked_check=recurse_locked_check,
        scan_button=scan_button,
    )


def build_reference_panel(parent: QtWidgets.QWidget, proxy_model: object) -> ReferencePanelWidgets:
    """Build the scanned-reference table panel."""
    panel = QtWidgets.QWidget(parent)
    layout = QtWidgets.QVBoxLayout(panel)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)

    search_edit = QtWidgets.QLineEdit(parent)
    search_edit.setMinimumWidth(260)
    search_edit.setPlaceholderText("Filter by node, parameter, path, or note")
    search_edit.setToolTip("Filter references by node, parameter, path, kind, or note.")
    missing_only_check = QtWidgets.QCheckBox("Broken targets", parent)
    missing_only_check.setToolTip(
        "Show only inbound relink targets that are missing or use undefined variables."
    )
    missing_only_check.setChecked(True)
    writable_only_check = QtWidgets.QCheckBox("Writable only", parent)
    writable_only_check.setToolTip("Show only references the relinker can update.")
    writable_only_check.setChecked(True)
    kind_combo = QtWidgets.QComboBox(parent)
    kind_combo.setMinimumWidth(112)
    kind_combo.setToolTip("Limit the table to a specific reference kind.")
    kind_combo.addItem("All kinds", "all")
    kind_combo.addItem("File parameters", "file")
    kind_combo.addItem("HDA libraries", "hda")
    reset_filters_button = QtWidgets.QPushButton("Reset", parent)
    reset_filters_button.setObjectName("secondaryButton")
    reset_filters_button.setToolTip("Clear table filters.")

    filter_row = QtWidgets.QHBoxLayout()
    filter_row.setContentsMargins(0, 0, 0, 0)
    filter_row.setSpacing(8)
    filter_label = QtWidgets.QLabel("References", parent)
    filter_label.setObjectName("sectionLabel")
    filter_row.addWidget(filter_label)
    filter_row.addWidget(search_edit, 1)
    filter_row.addWidget(missing_only_check)
    filter_row.addWidget(writable_only_check)
    filter_row.addWidget(kind_combo)
    filter_row.addWidget(reset_filters_button)
    layout.addLayout(filter_row)

    summary_label = QtWidgets.QLabel(
        "0 total | 0 broken targets | 0 generated outputs | 0 writable | 0 HDA | 0 visible",
        parent,
    )
    summary_label.setObjectName("summaryLabel")
    export_button = QtWidgets.QPushButton("Export CSV", parent)
    export_button.setObjectName("secondaryButton")
    export_button.setEnabled(False)
    export_button.setToolTip("Export the current reference table to a CSV report.")

    table_action_row = QtWidgets.QHBoxLayout()
    table_action_row.setContentsMargins(0, 0, 0, 0)
    table_action_row.setSpacing(8)
    table_action_row.addWidget(summary_label, 1)
    table_action_row.addWidget(export_button)
    layout.addLayout(table_action_row)

    reference_table = QtWidgets.QTableView(parent)
    reference_table.setModel(proxy_model)
    reference_table.setSortingEnabled(True)
    reference_table.sortByColumn(REFERENCE_PATH_FAMILY_COLUMN, ASCENDING_ORDER)
    reference_table.setSelectionBehavior(SELECT_ROWS)
    reference_table.setSelectionMode(SINGLE_SELECTION)
    reference_table.setAlternatingRowColors(True)
    reference_table.setContextMenuPolicy(CUSTOM_CONTEXT_MENU)
    reference_table.setItemDelegate(StatusColorDelegate(reference_table))
    configure_table_scrolling(reference_table)
    reference_table.verticalHeader().setVisible(False)
    reference_table.horizontalHeader().setStretchLastSection(True)
    reference_table.horizontalHeader().setSectionResizeMode(HEADER_INTERACTIVE)
    for column, width in (
        (0, 120),
        (1, 65),
        (2, 130),
        (3, 190),
        (4, 100),
        (5, 220),
        (6, 300),
        (7, 300),
        (9, 600),
    ):
        reference_table.setColumnWidth(column, width)
    reference_table.setToolTip(
        "Right-click a reference to copy its path, reveal it on disk, or select its node."
    )
    layout.addWidget(reference_table, 1)

    return ReferencePanelWidgets(
        panel=panel,
        search_edit=search_edit,
        missing_only_check=missing_only_check,
        writable_only_check=writable_only_check,
        kind_combo=kind_combo,
        reset_filters_button=reset_filters_button,
        summary_label=summary_label,
        export_button=export_button,
        reference_table=reference_table,
    )


def build_relink_panel(parent: QtWidgets.QWidget, report_model: object) -> RelinkPanelWidgets:
    """Build the preview/apply relink panel."""
    panel = QtWidgets.QWidget(parent)
    layout = QtWidgets.QVBoxLayout(panel)
    layout.setContentsMargins(10, 10, 10, 10)
    layout.setSpacing(8)

    form = QtWidgets.QFormLayout()
    find_edit = QtWidgets.QLineEdit(parent)
    find_edit.setPlaceholderText("P:/old_show or $JOB/assets")
    find_edit.setToolTip("Full words or partial text to find in reference paths.")
    replace_edit = QtWidgets.QLineEdit(parent)
    replace_edit.setPlaceholderText("P:/new_show or $HIP/assets")
    replace_edit.setToolTip("Replacement text to write into matching references.")
    scope_combo = QtWidgets.QComboBox(parent)
    scope_combo.setMinimumWidth(190)
    scope_combo.setToolTip("Apply to a safer subset of scanned rows.")
    scope_combo.addItem("Visible filtered rows", SCOPE_VISIBLE_ROWS)
    scope_combo.addItem("Selected row", SCOPE_SELECTED_ROW)
    scope_combo.addItem("Selected path family", SCOPE_PATH_FAMILY)
    scope_combo.addItem("Missing under Find root", SCOPE_MISSING_UNDER_ROOT)
    scope_combo.addItem("All scanned rows", SCOPE_ALL_ROWS)
    form.addRow("Find", find_edit)
    form.addRow("Replace with", replace_edit)
    form.addRow("Scope", scope_combo)
    layout.addLayout(form)

    find_match_label = QtWidgets.QLabel(parent)
    find_match_label.setObjectName("findMatchLabel")
    find_match_label.setWordWrap(True)
    find_match_label.hide()
    layout.addWidget(find_match_label)

    case_sensitive_check = QtWidgets.QCheckBox("Exact case only", parent)
    case_sensitive_check.setChecked(False)
    case_sensitive_check.setToolTip("Exact letter-case matching.")
    include_hda_replace_check = QtWidgets.QCheckBox("Relink HDA libraries too", parent)
    include_hda_replace_check.setChecked(False)
    include_hda_replace_check.setToolTip(
        "Apply the replacement to matching loaded HDA library paths too."
    )
    uninstall_old_hda_check = QtWidgets.QCheckBox(
        "Uninstall old HDA libraries after install", parent
    )
    uninstall_old_hda_check.setToolTip(
        "After installing replacement HDA libraries, unload the old matching libraries."
    )
    layout.addWidget(case_sensitive_check)
    layout.addWidget(include_hda_replace_check)
    layout.addWidget(uninstall_old_hda_check)

    normalize_button = QtWidgets.QPushButton("Normalize Paths", parent)
    normalize_button.setObjectName("secondaryButton")
    normalize_button.setToolTip(
        "Preview separator and drive-letter cleanup for file parameters in the selected scope."
    )
    apply_button = QtWidgets.QPushButton("Apply", parent)
    apply_button.setObjectName("applyButton")
    apply_button.setEnabled(False)
    apply_button.setToolTip("Apply the latest previewed path changes.")
    copy_report_button = QtWidgets.QPushButton("Copy Report", parent)
    copy_report_button.setEnabled(False)
    copy_report_button.setToolTip("Copy the latest preview or apply report.")
    button_row = QtWidgets.QHBoxLayout()
    button_row.addWidget(normalize_button)
    button_row.addWidget(apply_button)
    button_row.addWidget(copy_report_button)
    layout.addLayout(button_row)

    legend_row = QtWidgets.QHBoxLayout()
    legend_row.setContentsMargins(0, 0, 0, 0)
    legend_row.setSpacing(12)
    for label_text, color in (
        ("Change", STATUS_COLOR_READY),
        ("Skipped", STATUS_COLOR_NOT_UPDATABLE),
        ("Failed", STATUS_COLOR_MISSING),
    ):
        item = QtWidgets.QHBoxLayout()
        item.setSpacing(6)
        swatch = QtWidgets.QFrame(parent)
        swatch.setFixedSize(12, 12)
        swatch.setStyleSheet(f"background: {color}; border-radius: 2px;")
        label = QtWidgets.QLabel(label_text, parent)
        label.setObjectName("summaryLabel")
        item.addWidget(swatch)
        item.addWidget(label)
        legend_row.addLayout(item)
    legend_row.addStretch(1)
    layout.addLayout(legend_row)

    report_table = QtWidgets.QTableView(parent)
    report_table.setModel(report_model)
    report_table.setAlternatingRowColors(False)
    report_table.setItemDelegate(StatusColorDelegate(report_table))
    configure_table_scrolling(report_table)
    report_table.verticalHeader().setVisible(False)
    report_table.horizontalHeader().setStretchLastSection(True)
    report_table.horizontalHeader().setSectionResizeMode(HEADER_INTERACTIVE)
    for column, width in ((0, 200), (1, 280), (2, 280)):
        report_table.setColumnWidth(column, width)
    report_table.setToolTip("Preview and apply relinking.")
    layout.addWidget(report_table, 1)

    return RelinkPanelWidgets(
        panel=panel,
        find_edit=find_edit,
        replace_edit=replace_edit,
        scope_combo=scope_combo,
        find_match_label=find_match_label,
        case_sensitive_check=case_sensitive_check,
        include_hda_replace_check=include_hda_replace_check,
        uninstall_old_hda_check=uninstall_old_hda_check,
        normalize_button=normalize_button,
        apply_button=apply_button,
        copy_report_button=copy_report_button,
        report_table=report_table,
    )


def build_details_panel(parent: QtWidgets.QWidget) -> DetailsPanelWidgets:
    """Build the selected-reference details panel."""
    panel = QtWidgets.QWidget(parent)
    layout = QtWidgets.QVBoxLayout(panel)
    layout.setContentsMargins(10, 10, 10, 10)
    detail_text = QtWidgets.QPlainTextEdit(parent)
    detail_text.setReadOnly(True)
    detail_text.setToolTip("Full details for the selected reference.")
    layout.addWidget(detail_text, 1)
    return DetailsPanelWidgets(panel=panel, detail_text=detail_text)


def configure_table_scrolling(table: QtWidgets.QTableView) -> None:
    """Use pixel-based scrolling for wide relinker tables."""
    table.setVerticalScrollMode(SCROLL_PER_PIXEL)
    table.setHorizontalScrollMode(SCROLL_PER_PIXEL)
    table.verticalScrollBar().setSingleStep(24)
    table.horizontalScrollBar().setSingleStep(32)

    palette = table.palette()
    palette.setColor(QtGui.QPalette.Base, QtGui.QColor(REPORT_TABLE_BASE_COLOR))
    palette.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor(REPORT_TABLE_ALT_BASE_COLOR))
    table.setPalette(palette)

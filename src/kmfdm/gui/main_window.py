from __future__ import annotations

import copy
import ctypes
import json
import os
import re
import sys
from dataclasses import dataclass, field, replace
from importlib import resources
from pathlib import Path

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QPoint,
    QRect,
    QSortFilterProxyModel,
    Qt,
    QThread,
    QTimer,
    Signal,
)
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QComboBox,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionButton,
    QTabWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from kmfdm.config import (
    DEFAULT_CONFIG_FILENAME,
    LibrarySelection,
    PolicyProfile,
    PolicyRule,
    WorkspaceConfig,
    candidate_symbol_libraries_for_footprint,
    create_symbol_library_for_footprint,
    default_workspace_config_path,
    default_symbol_library_for_footprint,
    load_bundled_layout_profiles,
    load_bundled_policy_profiles,
    load_policy_profile,
    load_workspace_config,
    save_policy_profile,
    save_workspace_config,
    workspace_setup_issue,
)
from kmfdm.models import CellState, ChangeKind, ChangeSource, Issue, IssueSeverity
from kmfdm.services.history import (
    HistoryEvent,
    append_history_events,
    history_path_for_workspace,
    load_history_events,
)
from kmfdm.services.kicad_scan import KiCadLibraryItem, ScanProgressCallback, scan_workspace_libraries
from kmfdm.services.kicad_write import KiCadMetadataChange, KiCadWriteError, save_metadata_changes
from kmfdm.services.policy_audit import AuditContext, AuditItem, PolicyFinding, audit_items_against_policies


WINDOWS_APP_ID = "Phoenixjack.KMFDM"
WORKSPACE_POLICY_DIRNAME = ".kmfdm-policies"


@dataclass
class MockItem:
    library: str
    name: str
    cells: dict[str, CellState]
    auditable: bool = True
    library_alias: str = ""
    metadata_fields: dict[str, str] = field(default_factory=dict)
    source_path: Path | None = None

    @property
    def display_library(self) -> str:
        return self.library_alias or self.library


@dataclass
class LibraryTabState:
    model: ComponentTableModel
    proxy_model: ComponentFilterProxyModel
    table: QTableView
    inspector: ReadOnlyInfoPanel
    library_filter: MultiSelectFilterButton
    column_filter: MultiSelectFilterButton
    unsaved_filter: StatusFilterButton
    warning_filter: StatusFilterButton
    error_filter: StatusFilterButton


@dataclass
class AuditPolicySettings:
    profile: PolicyProfile
    enabled: bool
    apply_to_new_libraries: bool
    target: str
    severity: str
    enabled_libraries: set[str] = field(default_factory=set)
    known_libraries: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class PendingChange:
    scope: str
    library: str
    item: str
    field: str
    original: str
    current: str
    included: bool
    source: str = ""
    detail: str = ""
    source_path: Path | None = None
    item_ref: MockItem | None = None


class LibraryLoadWorker(QObject):
    progress = Signal(int, int, str)
    finished = Signal(object, object)
    failed = Signal(str)

    def __init__(self, workspace_config: WorkspaceConfig) -> None:
        super().__init__()
        self.workspace_config = workspace_config

    def run(self) -> None:
        try:
            self.progress.emit(0, 1, "Preparing KiCad library scan...")
            symbol_items, footprint_items = configured_table_items_from_workspace(
                self.workspace_config,
                progress_callback=self._report_progress,
            )
        except Exception as error:  # pragma: no cover - exercised through GUI error path.
            self.failed.emit(str(error))
            return

        self.finished.emit(symbol_items, footprint_items)

    def _report_progress(self, completed_steps: int, total_steps: int, message: str) -> None:
        self.progress.emit(completed_steps, total_steps, message)


class ComponentTableModel(QAbstractTableModel):
    columns = ["Apply", "Library", "Name", "Value", "Manufacturer", "MPN", "Datasheet"]

    def __init__(self, items: list[MockItem]) -> None:
        super().__init__()
        self.items = items

    def set_items(self, items: list[MockItem]) -> None:
        self.beginResetModel()
        self.items = items
        self.endResetModel()

    def refresh_all(self) -> None:
        if not self.items:
            return
        self.dataChanged.emit(
            self.index(0, 0),
            self.index(len(self.items) - 1, len(self.columns) - 1),
            [Qt.DisplayRole, Qt.BackgroundRole, Qt.FontRole, Qt.ToolTipRole],
        )

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.items)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.columns)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.columns[section]
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.NoItemFlags

        flags = Qt.ItemIsSelectable | Qt.ItemIsEnabled
        column_name = self.columns[index.column()]

        if column_name == "Apply":
            return flags | Qt.ItemIsUserCheckable

        cell = self._cell_for(index)
        if cell and cell.editable:
            flags |= Qt.ItemIsEditable

        return flags

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None

        item = self.items[index.row()]
        column_name = self.columns[index.column()]

        if column_name == "Apply":
            if role == Qt.DisplayRole:
                return None
            if role == Qt.CheckStateRole:
                return Qt.CheckState.Checked if self._row_included(item) else Qt.CheckState.Unchecked
            if role == Qt.TextAlignmentRole:
                return Qt.AlignCenter
            if role == Qt.ToolTipRole:
                return "Include this item's pending changes in the next save."
            return None

        if column_name == "Library":
            if role == Qt.DisplayRole:
                return item.display_library
            if role == Qt.EditRole:
                return item.library
            if role == Qt.ToolTipRole and item.display_library != item.library:
                return item.library
            return None

        if column_name == "Name":
            return item.name if role in (Qt.DisplayRole, Qt.EditRole) else None

        cell = self._cell_for(index)
        if cell is None:
            return None

        if role in (Qt.DisplayRole, Qt.EditRole):
            if cell.change_kind == ChangeKind.FIELD_DELETED:
                return "FIELD DELETED"
            if cell.change_kind == ChangeKind.VALUE_CLEARED:
                return "CONTENTS DELETED"
            return cell.working_value

        if role == Qt.BackgroundRole:
            if cell.change_kind == ChangeKind.FIELD_DELETED:
                return QColor("#f3d1d1")
            if cell.change_source == ChangeSource.MANUAL:
                return QColor("#d9ead3")
            if cell.change_source == ChangeSource.RULE_GENERATED:
                return QColor("#fff2cc")
            if cell.issues:
                return QColor("#fce5cd")

        if role == Qt.FontRole:
            font = QFont()
            font.setBold(cell.is_changed)
            font.setItalic(cell.inherited)
            font.setStrikeOut(cell.change_kind == ChangeKind.FIELD_DELETED)
            return font

        if role == Qt.ToolTipRole:
            return cell.tooltip_text()

        return None

    def setData(self, index: QModelIndex, value, role: int = Qt.EditRole) -> bool:
        if not index.isValid():
            return False

        item = self.items[index.row()]
        column_name = self.columns[index.column()]

        if column_name == "Apply" and role == Qt.CheckStateRole:
            included = value == Qt.CheckState.Checked or value == Qt.CheckState.Checked.value
            for cell in item.cells.values():
                if cell.is_changed:
                    cell.included_in_save = included
            self.dataChanged.emit(index, index, [Qt.CheckStateRole])
            return True

        cell = self._cell_for(index)
        if cell is None or role != Qt.EditRole:
            return False

        new_value = str(value)
        if new_value == cell.working_value:
            return True

        cell.working_value = new_value
        if new_value == cell.original_value:
            cell.change_source = None
            cell.change_kind = None
        else:
            cell.change_source = ChangeSource.MANUAL
            cell.change_kind = ChangeKind.VALUE_CHANGED
        top_left = self.index(index.row(), 0)
        self.dataChanged.emit(top_left, index, [Qt.DisplayRole, Qt.BackgroundRole, Qt.FontRole, Qt.ToolTipRole, Qt.CheckStateRole])
        return True

    def _cell_for(self, index: QModelIndex) -> CellState | None:
        column_name = self.columns[index.column()]
        return self.items[index.row()].cells.get(column_name)

    def _row_included(self, item: MockItem) -> bool:
        changed_cells = [cell for cell in item.cells.values() if cell.is_changed]
        return bool(changed_cells) and all(cell.included_in_save for cell in changed_cells)

    def _row_has_changes(self, item: MockItem) -> bool:
        return any(cell.is_changed for cell in item.cells.values())


class ComponentFilterProxyModel(QSortFilterProxyModel):
    def __init__(self) -> None:
        super().__init__()
        self._enabled_libraries: set[str] = set()
        self._show_unsaved_only = False
        self._show_warnings_only = False
        self._show_errors_only = False

    def set_enabled_libraries(self, libraries: set[str]) -> None:
        self.beginFilterChange()
        self._enabled_libraries = set(libraries)
        self.endFilterChange()

    def set_status_filters(
        self,
        *,
        unsaved: bool,
        warnings: bool,
        errors: bool,
    ) -> None:
        self.beginFilterChange()
        self._show_unsaved_only = unsaved
        self._show_warnings_only = warnings
        self._show_errors_only = errors
        self.endFilterChange()

    def refresh_status_filters(self) -> None:
        self.beginFilterChange()
        self.endFilterChange()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        source_model = self.sourceModel()
        if source_model is None:
            return False

        library_column = source_model.columns.index("Library")
        library_index = source_model.index(source_row, library_column, source_parent)
        if source_model.data(library_index, Qt.DisplayRole) not in self._enabled_libraries:
            return False

        if not self._status_filters_active():
            return True

        item = source_model.items[source_row]
        return (
            (self._show_unsaved_only and _item_has_changes(item))
            or (self._show_warnings_only and _item_has_issue_severity(item, IssueSeverity.WARNING))
            or (self._show_errors_only and _item_has_issue_severity(item, IssueSeverity.ERROR))
        )

    def _status_filters_active(self) -> bool:
        return self._show_unsaved_only or self._show_warnings_only or self._show_errors_only


class MultiSelectFilterButton(QPushButton):
    selectionChanged = Signal(object)

    def __init__(self, title: str, options: list[str], selected_options: set[str] | None = None) -> None:
        super().__init__()
        self.title = title
        self.options = list(options)
        self._updating = False
        self._actions_by_option: dict[str, QAction] = {}
        self.set_options(options, selected_options)

    def set_options(self, options: list[str], selected_options: set[str] | None = None) -> None:
        self.options = list(options)
        self._actions_by_option = {}
        menu = QMenu(self)
        self.setMenu(menu)

        select_all_action = QAction("Select All", self)
        select_all_action.triggered.connect(self.select_all)
        menu.addAction(select_all_action)

        select_none_action = QAction("Select None", self)
        select_none_action.triggered.connect(self.select_none)
        menu.addAction(select_none_action)
        menu.addSeparator()

        selected_options = set(options) if selected_options is None else set(selected_options)
        for option in self.options:
            action = QAction(option, self)
            action.setCheckable(True)
            action.setChecked(option in selected_options)
            action.toggled.connect(lambda _checked, checked_option=option: self._option_toggled(checked_option))
            menu.addAction(action)
            self._actions_by_option[option] = action

        self._update_text()

    def selected_options(self) -> set[str]:
        return {
            option
            for option, action in self._actions_by_option.items()
            if action.isChecked()
        }

    def select_all(self) -> None:
        self._set_selected_options(set(self.options))

    def select_none(self) -> None:
        self._set_selected_options(set())

    def _set_selected_options(self, selected_options: set[str]) -> None:
        self._updating = True
        for option, action in self._actions_by_option.items():
            action.setChecked(option in selected_options)
        self._updating = False
        self._emit_selection_changed()

    def _option_toggled(self, _option: str) -> None:
        if self._updating:
            return
        self._emit_selection_changed()

    def _emit_selection_changed(self) -> None:
        self._update_text()
        self.selectionChanged.emit(self.selected_options())

    def _update_text(self) -> None:
        selected_count = len(self.selected_options())
        total_count = len(self.options)
        if total_count == 0:
            summary = "None"
        elif selected_count == total_count:
            summary = "All"
        elif selected_count == 0:
            summary = "None"
        else:
            summary = f"{selected_count}/{total_count}"
        self.setText(f"{self.title}: {summary}")


class StatusFilterButton(QPushButton):
    def __init__(self, title: str, active_color: str) -> None:
        super().__init__()
        self.title = title
        self.active_color = active_color
        self.count = 0
        self.setCheckable(True)
        self.setMinimumHeight(24)
        self.setToolTip(f"Filter rows with {title.casefold()}.")
        self.set_count(0)

    def set_count(self, count: int) -> None:
        self.count = count
        self.setText(f"{self.title}: {count}")
        self._apply_style(count)

    def _apply_style(self, count: int) -> None:
        background = "#d9ead3" if count == 0 else self.active_color
        border = "#5f8f5f" if count == 0 else "#7f7f7f"
        if self.isChecked():
            border = "#222222"
        self.setStyleSheet(
            "QPushButton {"
            f"background-color: {background};"
            f"border: 1px solid {border};"
            "border-radius: 11px;"
            "padding: 3px 10px;"
            "}"
            "QPushButton:checked {"
            "border: 2px solid #222222;"
            "padding: 2px 9px;"
            "}"
        )

    def nextCheckState(self) -> None:
        super().nextCheckState()
        self._apply_style(self.count)


class CenteredCheckBoxDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index) -> None:
        check_state = index.data(Qt.CheckStateRole)
        if check_state is None:
            super().paint(painter, option, index)
            return

        style = option.widget.style() if option.widget else QApplication.style()
        checkbox_option = QStyleOptionButton()
        checkbox_option.state |= QStyle.StateFlag.State_Enabled
        checkbox_option.state |= (
            QStyle.StateFlag.State_On
            if check_state == Qt.CheckState.Checked
            else QStyle.StateFlag.State_Off
        )

        indicator_rect = style.subElementRect(
            QStyle.SubElement.SE_CheckBoxIndicator,
            checkbox_option,
            option.widget,
        )
        checkbox_option.rect = QRect(
            option.rect.x() + (option.rect.width() - indicator_rect.width()) // 2,
            option.rect.y() + (option.rect.height() - indicator_rect.height()) // 2,
            indicator_rect.width(),
            indicator_rect.height(),
        )

        style.drawControl(QStyle.ControlElement.CE_CheckBox, checkbox_option, painter, option.widget)


class ReadOnlyInfoPanel(QFrame):
    def __init__(self, text: str = "") -> None:
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setObjectName("readOnlyInfoPanel")
        self.setStyleSheet(
            "#readOnlyInfoPanel {"
            "background-color: #efefef;"
            "border: 1px solid #a0a0a0;"
            "}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        self.label = QLabel()
        self.label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.label.setTextFormat(Qt.TextFormat.PlainText)
        self.label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.label.setWordWrap(True)
        layout.addWidget(self.label)
        self.setPlainText(text)

    def setPlainText(self, text: str) -> None:
        self.label.setText(text)


class RuleEditorDialog(QDialog):
    def __init__(
        self,
        fields: list[str],
        rule: PolicyRule | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.rule = rule
        self.setWindowTitle("New Rule" if rule is None else "Edit Rule")
        self.resize(560, 460)

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        self.name_input = QLineEdit()
        self.field_combo = QComboBox()
        self.field_combo.setEditable(True)
        self.field_combo.addItems(fields)
        self.required_checkbox = QCheckBox("Field must be populated")
        self.regex_enabled_checkbox = QCheckBox("Validate with regex pattern")
        self.regex_input = QLineEdit()
        self.regex_input.setPlaceholderText(r"Example: ^[A-Za-z0-9_.-]+$")
        self.test_input = QLineEdit()
        self.test_input.setPlaceholderText("Type a sample value to test the regex")
        self.regex_result = QLabel("Regex preview is inactive.")
        self.unsupported_rule = rule is not None and rule.rule_type not in {
            "required_field",
            "regex_check",
        }

        form_layout.addRow("Rule name", self.name_input)
        form_layout.addRow("Field", self.field_combo)
        form_layout.addRow("", self.required_checkbox)
        form_layout.addRow("", self.regex_enabled_checkbox)
        form_layout.addRow("Regex pattern", self.regex_input)
        form_layout.addRow("Test value", self.test_input)
        form_layout.addRow("Preview", self.regex_result)
        layout.addLayout(form_layout)

        help_text = QLabel(
            "\n".join(
                [
                    "Regex quick help",
                    "^ starts the value, $ ends the value.",
                    "[A-Z] allows uppercase letters. [a-z] allows lowercase letters. [0-9] allows digits.",
                    "+ means one or more. * means zero or more. ? means optional.",
                    r"\d means any digit. \. means a literal dot.",
                    "(jpg|png|gif) allows one of several choices.",
                ]
            )
        )
        help_text.setWordWrap(True)
        layout.addWidget(help_text)

        note = QLabel(
            "This editor currently saves required-field and regex rules."
            if not self.unsupported_rule
            else "This rule type is visible but is not editable in the first rule-editor slice."
        )
        note.setWordWrap(True)
        layout.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok_button.setEnabled(not self.unsupported_rule)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.regex_enabled_checkbox.toggled.connect(self._update_regex_preview)
        self.regex_input.textChanged.connect(self._update_regex_preview)
        self.test_input.textChanged.connect(self._update_regex_preview)
        self._populate_from_rule()
        for control in [
            self.name_input,
            self.field_combo,
            self.required_checkbox,
            self.regex_enabled_checkbox,
            self.regex_input,
            self.test_input,
        ]:
            control.setEnabled(not self.unsupported_rule)
        self._update_regex_preview()

    def accept(self) -> None:
        try:
            self.to_rule(existing_rule_ids=[])
        except ValueError as error:
            QMessageBox.warning(self, "Rule Incomplete", str(error))
            return
        super().accept()

    def to_rule(self, *, existing_rule_ids: list[str]) -> PolicyRule:
        if self.unsupported_rule:
            raise ValueError("This rule type is not editable yet.")

        name = self.name_input.text().strip()
        field = self.field_combo.currentText().strip()
        regex_enabled = self.regex_enabled_checkbox.isChecked()
        required = self.required_checkbox.isChecked()
        if not name:
            raise ValueError("Enter a rule name.")
        if not field:
            raise ValueError("Choose or enter a field name.")
        if not required and not regex_enabled:
            raise ValueError("Select Required, Regex Pattern, or both.")

        rule_id = self.rule.rule_id if self.rule is not None else _unique_rule_id(name, existing_rule_ids)
        target = self.rule.target if self.rule is not None else "both"
        severity = self.rule.severity if self.rule is not None else "warning"
        save_behavior = self.rule.save_behavior if self.rule is not None else "advisory"
        if regex_enabled:
            pattern = self.regex_input.text().strip()
            if not pattern:
                raise ValueError("Enter a regex pattern.")
            try:
                re.compile(pattern)
            except re.error as error:
                raise ValueError(f"Invalid regex pattern: {error}") from error
            return PolicyRule(
                rule_id=rule_id,
                name=name,
                rule_type="regex_check",
                target=target,
                severity=severity,
                save_behavior=save_behavior,
                parameters={
                    "field": field,
                    "pattern": pattern,
                    "mode": "contains_match",
                    "ignore_blank": not required,
                },
            )

        return PolicyRule(
            rule_id=rule_id,
            name=name,
            rule_type="required_field",
            target=target,
            severity=severity,
            save_behavior=save_behavior,
            parameters={"field": field},
        )

    def _populate_from_rule(self) -> None:
        if self.rule is None:
            return

        self.name_input.setText(self.rule.name)
        field = str(
            self.rule.parameters.get("field")
            or self.rule.parameters.get("canonical")
            or ""
        )
        if field:
            field_index = self.field_combo.findText(field)
            if field_index >= 0:
                self.field_combo.setCurrentIndex(field_index)
            else:
                self.field_combo.setEditText(field)
        self.regex_enabled_checkbox.setChecked(self.rule.rule_type == "regex_check")
        self.required_checkbox.setChecked(
            self.rule.rule_type == "required_field"
            or (
                self.rule.rule_type == "regex_check"
                and not bool(self.rule.parameters.get("ignore_blank", False))
            )
        )
        self.regex_input.setText(str(self.rule.parameters.get("pattern", "")))

    def _update_regex_preview(self) -> None:
        if not self.regex_enabled_checkbox.isChecked():
            self.regex_result.setText("Regex preview is inactive.")
            self.regex_result.setStyleSheet("")
            return

        pattern = self.regex_input.text()
        sample = self.test_input.text()
        if not pattern:
            self.regex_result.setText("Enter a regex pattern.")
            self.regex_result.setStyleSheet("color: #7a4a00;")
            return
        try:
            compiled = re.compile(pattern)
        except re.error as error:
            self.regex_result.setText(f"Invalid regex: {error}")
            self.regex_result.setStyleSheet("color: #b00020;")
            return
        if not sample:
            self.regex_result.setText("Enter a test value.")
            self.regex_result.setStyleSheet("color: #7a4a00;")
            return
        if compiled.search(sample):
            self.regex_result.setText("Pass: sample matches.")
            self.regex_result.setStyleSheet("color: #146c2e;")
        else:
            self.regex_result.setText("Fail: sample does not match.")
            self.regex_result.setStyleSheet("color: #b00020;")


class MainWindow(QMainWindow):
    def __init__(self, workspace_config_path: Path | None = None) -> None:
        super().__init__()
        self.setWindowTitle("KMFDM")
        self.setWindowIcon(kmfdm_icon())
        self.resize(1200, 760)
        self.workspace_config_path = workspace_config_path or default_workspace_config_path()
        self.history_path = history_path_for_workspace(self.workspace_config_path)
        self.workspace_config = WorkspaceConfig()
        self.workspace_setup_message = ""
        self._load_workspace_config_for_launch()
        self.policy_profiles = load_policy_profiles_for_workspace(
            self.workspace_config,
            self.workspace_config_path,
        )
        self.symbol_items: list[MockItem] = []
        self.footprint_items: list[MockItem] = []
        self.audit_policy_settings = audit_policy_settings_from_profiles(
            self.policy_profiles,
            self.symbol_items,
            self.footprint_items,
            _audit_policy_settings_overrides_from_config(self.workspace_config),
        )
        self._saved_policy_profiles_by_id = {
            profile.profile_id: copy.deepcopy(profile)
            for profile in self.policy_profiles
        }
        self._saved_audit_policy_settings = {
            profile_id: _audit_policy_settings_to_dict(settings)
            for profile_id, settings in self.audit_policy_settings.items()
        }
        self.policy_findings: list[PolicyFinding] = []
        self._refresh_policy_findings()
        self._library_load_thread: QThread | None = None
        self._library_load_worker: LibraryLoadWorker | None = None
        self._library_load_progress_dialog: QProgressDialog | None = None
        self._library_load_has_completed = False

        tabs = QTabWidget()
        self.tabs = tabs
        symbol_tab, self.symbol_tab_state = self._library_tab(self.symbol_items)
        footprint_tab, self.footprint_tab_state = self._library_tab(self.footprint_items)
        tabs.addTab(symbol_tab, _ui_icon("symbol"), "Symbols")
        tabs.addTab(footprint_tab, _ui_icon("footprint"), "Footprints")
        tabs.addTab(self._audit_rules_tab(), _ui_icon("audit"), "Audit")
        self.changes_tab_index = tabs.addTab(self._changes_tab(), _ui_icon("changes"), "Changes")
        tabs.addTab(self._history_tab(), _ui_icon("history"), "History")
        tabs.currentChanged.connect(lambda _index: self._update_action_buttons())

        edit_menu = self.menuBar().addMenu("&Edit")
        configuration_action = QAction("Configuration...", self)
        configuration_action.triggered.connect(lambda: self._show_configuration_dialog())
        preferences_action = QAction("Preferences...", self)
        preferences_action.triggered.connect(self._show_preferences_dialog)
        edit_menu.addAction(configuration_action)
        edit_menu.addAction(preferences_action)

        help_menu = self.menuBar().addMenu("&Help")
        legend_action = QAction("Cell Color Legend", self)
        legend_action.triggered.connect(self._show_color_legend)
        policy_guidance_action = QAction("Policy Guidance...", self)
        policy_guidance_action.triggered.connect(self._show_policy_guidance)
        help_menu.addAction(legend_action)
        help_menu.addAction(policy_guidance_action)

        central_widget = QWidget()
        central_layout = QVBoxLayout(central_widget)
        central_layout.setContentsMargins(6, 6, 6, 6)
        central_layout.addWidget(tabs)
        central_layout.addLayout(self._action_bar())
        self.setCentralWidget(central_widget)
        self._set_library_loading_message("Library data has not loaded yet.")
        self._update_action_buttons()
        QTimer.singleShot(0, self._start_launch_work)

    def _load_workspace_config_for_launch(self) -> None:
        load_path = self._workspace_config_load_path()
        config_exists = load_path.exists()
        try:
            self.workspace_config = load_workspace_config(load_path)
            self.workspace_setup_message = workspace_setup_issue(
                self.workspace_config,
                config_exists=config_exists,
            )
        except (OSError, ValueError, json.JSONDecodeError) as error:
            self.workspace_config = WorkspaceConfig()
            self.workspace_setup_message = (
                "Workspace configuration could not be loaded and needs repair."
                f"\n\n{error}"
            )

    def _workspace_config_load_path(self) -> Path:
        if self.workspace_config_path.exists():
            return self.workspace_config_path

        legacy_path = Path(sys.executable).parent / DEFAULT_CONFIG_FILENAME
        if legacy_path != self.workspace_config_path and legacy_path.exists():
            return legacy_path

        return self.workspace_config_path

    def _start_launch_work(self) -> None:
        if self._show_required_configuration_if_needed():
            self._begin_deferred_library_load()

    def _show_required_configuration_if_needed(self) -> bool:
        if not self.workspace_setup_message:
            return True

        QMessageBox.warning(
            self,
            "Workspace Setup Required",
            "\n".join(
                [
                    self.workspace_setup_message,
                    "",
                    "Select a library layout before continuing.",
                ]
            ),
        )
        if not self._show_configuration_dialog(require_layout_profile=True):
            self.close()
            return False
        return False

    def _action_bar(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        self.inline_status_label = QLabel("")
        self.inline_status_label.setMinimumWidth(260)
        self.inline_status_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.inline_status_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.inline_status_label.setStyleSheet("color: #555555;")
        layout.addWidget(self.inline_status_label, 1)

        self.revert_selected_button = QPushButton("Revert Selected")
        self.revert_selected_button.clicked.connect(self._revert_selected)
        layout.addWidget(self.revert_selected_button)

        self.revert_all_button = QPushButton("Revert All")
        self.revert_all_button.clicked.connect(self._revert_all)
        layout.addWidget(self.revert_all_button)

        self.save_selected_button = QPushButton("Save Selected")
        self.save_selected_button.clicked.connect(self._save_selected)
        layout.addWidget(self.save_selected_button)

        exit_button = QPushButton("Exit")
        exit_button.clicked.connect(self.close)
        layout.addWidget(exit_button)

        return layout

    def _show_inline_status(self, message: str, timeout_ms: int = 0) -> None:
        if not hasattr(self, "inline_status_label"):
            return
        self.inline_status_label.setText(message)
        if timeout_ms > 0:
            QTimer.singleShot(timeout_ms, lambda expected=message: self._clear_inline_status(expected))

    def _clear_inline_status(self, expected_message: str) -> None:
        if self.inline_status_label.text() == expected_message:
            self.inline_status_label.clear()

    def _library_tab(self, items: list[MockItem]) -> tuple[QWidget, LibraryTabState]:
        widget = QWidget()
        layout = QHBoxLayout(widget)

        left_side = QWidget()
        left_layout = QVBoxLayout(left_side)
        left_layout.setContentsMargins(0, 0, 0, 0)

        filter_bar = QHBoxLayout()
        filter_bar.setContentsMargins(0, 0, 0, 0)

        libraries = _available_libraries(items)
        library_filter = MultiSelectFilterButton("Source library", libraries)
        column_filter = MultiSelectFilterButton("Columns", ComponentTableModel.columns)
        unsaved_filter = StatusFilterButton("Unsaved", "#cfe2f3")
        warning_filter = StatusFilterButton("Warnings", "#fff2cc")
        error_filter = StatusFilterButton("Errors", "#f4cccc")
        filter_bar.addWidget(library_filter)
        filter_bar.addWidget(column_filter)
        filter_bar.addWidget(unsaved_filter)
        filter_bar.addWidget(warning_filter)
        filter_bar.addWidget(error_filter)
        filter_bar.addStretch()

        table = QTableView()
        model = ComponentTableModel(items)
        model.dataChanged.connect(lambda *_args: self._update_action_buttons())
        model.modelReset.connect(self._update_action_buttons)
        proxy_model = ComponentFilterProxyModel()
        proxy_model.setSourceModel(model)
        proxy_model.set_enabled_libraries(set(libraries))
        table.setModel(proxy_model)
        table.setItemDelegateForColumn(0, CenteredCheckBoxDelegate(table))
        table.resizeColumnsToContents()
        table.setColumnWidth(0, 72)
        inspector = ReadOnlyInfoPanel("Select a cell to inspect it.")
        inspector.setMinimumWidth(320)

        library_filter.selectionChanged.connect(proxy_model.set_enabled_libraries)
        model.dataChanged.connect(lambda *_args, proxy=proxy_model: proxy.refresh_status_filters())
        for button in [unsaved_filter, warning_filter, error_filter]:
            button.toggled.connect(
                lambda _checked, proxy=proxy_model, unsaved_button=unsaved_filter,
                warning_button=warning_filter, error_button=error_filter: proxy.set_status_filters(
                    unsaved=unsaved_button.isChecked(),
                    warnings=warning_button.isChecked(),
                    errors=error_button.isChecked(),
                )
            )
        model.dataChanged.connect(
            lambda *_args, source_model=model, unsaved_button=unsaved_filter,
            warning_button=warning_filter, error_button=error_filter: _update_status_filter_counts(
                source_model.items,
                unsaved_button,
                warning_button,
                error_button,
            )
        )
        model.modelReset.connect(
            lambda source_model=model, unsaved_button=unsaved_filter,
            warning_button=warning_filter, error_button=error_filter: _update_status_filter_counts(
                source_model.items,
                unsaved_button,
                warning_button,
                error_button,
            )
        )
        column_filter.selectionChanged.connect(lambda columns: self._apply_column_filter(table, model, columns))
        table.selectionModel().currentChanged.connect(
            lambda index: self._show_cell(proxy_model.mapToSource(index), model, inspector)
        )
        model.dataChanged.connect(lambda *_args: self._refresh_changes_tab())
        model.modelReset.connect(self._refresh_changes_tab)
        _update_status_filter_counts(items, unsaved_filter, warning_filter, error_filter)

        left_layout.addLayout(filter_bar)
        left_layout.addWidget(table)

        layout.addWidget(left_side, 4)
        layout.addWidget(inspector, 1)
        return widget, LibraryTabState(
            model=model,
            proxy_model=proxy_model,
            table=table,
            inspector=inspector,
            library_filter=library_filter,
            column_filter=column_filter,
            unsaved_filter=unsaved_filter,
            warning_filter=warning_filter,
            error_filter=error_filter,
        )

    def _changes_tab(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)

        self.changes_table = QTableWidget(0, 8)
        self.changes_table.setHorizontalHeaderLabels(
            ["Apply", "Scope", "Library", "Item", "Field", "Original", "Current", "Source"]
        )
        self.changes_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.changes_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.changes_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.changes_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.changes_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.changes_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.changes_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        self.changes_table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        self.changes_table.verticalHeader().setVisible(False)
        self.changes_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.changes_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.changes_table.currentCellChanged.connect(
            lambda row, _column, _previous_row, _previous_column: self._show_pending_change(row)
        )
        self.changes_table.itemChanged.connect(self._changes_apply_item_changed)

        self.changes_inspector = ReadOnlyInfoPanel("No pending changes.")
        self.changes_inspector.setMinimumWidth(340)
        layout.addWidget(self.changes_table, 3)
        layout.addWidget(self.changes_inspector, 1)
        self._pending_changes: list[PendingChange] = []
        self._refresh_changes_tab()
        return widget

    def _history_tab(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)

        history_side = QWidget()
        history_layout = QVBoxLayout(history_side)
        history_layout.setContentsMargins(0, 0, 0, 0)
        refresh_row = QHBoxLayout()
        self.history_summary_label = QLabel("")
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self._refresh_history_tab)
        refresh_row.addWidget(self.history_summary_label)
        refresh_row.addStretch()
        refresh_row.addWidget(refresh_button)

        self.history_table = QTableWidget(0, 7)
        self.history_table.setHorizontalHeaderLabels(
            ["Time", "Action", "Scope", "Library / Policy", "Item", "Field", "Status"]
        )
        self.history_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.history_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.history_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.history_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history_table.currentCellChanged.connect(
            lambda row, _column, _previous_row, _previous_column: self._show_history_event(row)
        )

        history_layout.addLayout(refresh_row)
        history_layout.addWidget(self.history_table)
        self.history_inspector = ReadOnlyInfoPanel("No saved history events.")
        self.history_inspector.setMinimumWidth(340)
        layout.addWidget(history_side, 3)
        layout.addWidget(self.history_inspector, 1)
        self._history_events: list[HistoryEvent] = []
        self._refresh_history_tab()
        return widget

    def _apply_column_filter(
        self,
        table: QTableView,
        model: ComponentTableModel,
        selected_columns: set[str],
    ) -> None:
        for column_index, column_name in enumerate(model.columns):
            table.setColumnHidden(column_index, column_name not in selected_columns)

    def _refresh_policy_findings(self) -> None:
        _clear_policy_issues(self.symbol_items, self.footprint_items)
        audit_items = mock_audit_items(self.symbol_items, self.footprint_items)
        context = AuditContext.from_items(audit_items)
        self.policy_findings = []
        for settings in self.audit_policy_settings.values():
            if not settings.enabled or settings.severity == "ignore":
                continue

            policy_items = [
                item
                for item in audit_items
                if item.library in settings.enabled_libraries
                and _policy_target_applies_to_item(settings.target, item)
            ]
            if not policy_items:
                continue

            self.policy_findings.extend(
                audit_items_against_policies(
                    policy_items,
                    [_policy_with_severity(settings.profile, settings.severity)],
                    context,
                )
            )
        attach_policy_findings_to_mock_items(
            self.symbol_items,
            self.footprint_items,
            self.policy_findings,
        )
        if hasattr(self, "symbol_tab_state"):
            self.symbol_tab_state.model.refresh_all()
            self.footprint_tab_state.model.refresh_all()
            self._refresh_status_filter_counts(self.symbol_tab_state)
            self._refresh_status_filter_counts(self.footprint_tab_state)
        if hasattr(self, "audit_library_table"):
            self._refresh_audit_violation_display()
        self._refresh_changes_tab()

    def _refresh_configured_library_tables(self) -> None:
        self.symbol_items, self.footprint_items = configured_table_items_from_workspace(
            self.workspace_config
        )
        self._sync_audit_policy_libraries()
        self._refresh_policy_findings()
        self._refresh_library_tab(self.symbol_tab_state, self.symbol_items)
        self._refresh_library_tab(self.footprint_tab_state, self.footprint_items)
        if hasattr(self, "audit_policy_list"):
            self._show_policy_configuration(self.audit_policy_list.currentItem())

    def _begin_deferred_library_load(self) -> None:
        if self._library_load_thread is not None:
            return
        if not _workspace_has_enabled_libraries(self.workspace_config):
            self._apply_loaded_library_items([], [])
            self._set_library_loading_message("No enabled KiCad libraries are configured.")
            return

        self._set_library_loading_message("Loading KiCad libraries...")
        progress_dialog = QProgressDialog("Loading KiCad libraries...", None, 0, 100, self)
        progress_dialog.setWindowTitle("Loading Libraries")
        progress_dialog.setCancelButton(None)
        progress_dialog.setAutoClose(False)
        progress_dialog.setAutoReset(False)
        progress_dialog.setMinimumDuration(0)
        progress_dialog.setValue(0)
        progress_dialog.show()
        self._library_load_progress_dialog = progress_dialog

        thread = QThread(self)
        worker = LibraryLoadWorker(copy.deepcopy(self.workspace_config))
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._library_load_progress_changed)
        worker.finished.connect(self._library_load_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(self._library_load_failed)
        worker.failed.connect(thread.quit)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._library_load_thread_finished)
        self._library_load_thread = thread
        self._library_load_worker = worker
        thread.start()

    def _library_load_progress_changed(
        self,
        completed_steps: int,
        total_steps: int,
        message: str,
    ) -> None:
        percentage = _progress_percentage(completed_steps, total_steps)
        if self._library_load_progress_dialog is not None:
            self._library_load_progress_dialog.setLabelText(f"{message}\n\n{percentage}% complete")
            self._library_load_progress_dialog.setValue(percentage)
        self._set_library_loading_message(f"Loading KiCad libraries\n\n{percentage}% complete\n{message}")
        self._show_inline_status(f"Loading KiCad libraries: {percentage}%")

    def _library_load_finished(
        self,
        symbol_items: list[MockItem],
        footprint_items: list[MockItem],
    ) -> None:
        self._close_library_load_progress_dialog()
        self._apply_loaded_library_items(symbol_items, footprint_items)
        self._show_inline_status(
            f"Loaded {len(symbol_items)} symbols and {len(footprint_items)} footprints.",
            5000,
        )

    def _library_load_failed(self, message: str) -> None:
        self._close_library_load_progress_dialog()
        self._set_library_loading_message("Library loading failed. Check Configuration and try again.")
        QMessageBox.warning(self, "Library Load Failed", message)

    def _library_load_thread_finished(self) -> None:
        self._library_load_thread = None
        self._library_load_worker = None

    def _close_library_load_progress_dialog(self) -> None:
        if self._library_load_progress_dialog is not None:
            self._library_load_progress_dialog.close()
            self._library_load_progress_dialog.deleteLater()
            self._library_load_progress_dialog = None

    def _apply_loaded_library_items(
        self,
        symbol_items: list[MockItem],
        footprint_items: list[MockItem],
    ) -> None:
        self.symbol_items = symbol_items
        self.footprint_items = footprint_items
        if not self._library_load_has_completed:
            self.audit_policy_settings = audit_policy_settings_from_profiles(
                self.policy_profiles,
                self.symbol_items,
                self.footprint_items,
                _audit_policy_settings_overrides_from_config(self.workspace_config),
            )
            self._saved_audit_policy_settings = {
                profile_id: _audit_policy_settings_to_dict(settings)
                for profile_id, settings in self.audit_policy_settings.items()
            }
            self._library_load_has_completed = True
        else:
            self._sync_audit_policy_libraries()
        self._refresh_policy_findings()
        self._refresh_library_tab(self.symbol_tab_state, self.symbol_items)
        self._refresh_library_tab(self.footprint_tab_state, self.footprint_items)
        if hasattr(self, "audit_policy_list"):
            self._show_policy_configuration(self.audit_policy_list.currentItem())
        self._update_action_buttons()
        self._refresh_changes_tab()

    def _set_library_loading_message(self, message: str) -> None:
        if hasattr(self, "symbol_tab_state"):
            self.symbol_tab_state.inspector.setPlainText(message)
        if hasattr(self, "footprint_tab_state"):
            self.footprint_tab_state.inspector.setPlainText(message)

    def _refresh_library_tab(self, tab_state: LibraryTabState, items: list[MockItem]) -> None:
        tab_state.model.set_items(items)
        libraries = _available_libraries(items)
        tab_state.library_filter.set_options(libraries)
        tab_state.proxy_model.set_enabled_libraries(set(libraries))
        self._refresh_status_filter_counts(tab_state)
        tab_state.inspector.setPlainText("Select a cell to inspect it.")
        tab_state.table.resizeColumnsToContents()
        tab_state.table.setColumnWidth(0, 72)

    def _refresh_status_filter_counts(self, tab_state: LibraryTabState) -> None:
        _update_status_filter_counts(
            tab_state.model.items,
            tab_state.unsaved_filter,
            tab_state.warning_filter,
            tab_state.error_filter,
        )
        tab_state.proxy_model.refresh_status_filters()

    def _refresh_changes_tab(self) -> None:
        if not hasattr(self, "changes_table"):
            return
        if getattr(self, "_suppress_changes_refresh", False):
            return

        changes = _pending_metadata_changes("Symbol", self.symbol_items)
        changes.extend(_pending_metadata_changes("Footprint", self.footprint_items))
        self._pending_changes = changes
        self._update_changes_tab_label(len(changes))
        self.changes_table.blockSignals(True)
        self.changes_table.setRowCount(len(changes))
        for row, change in enumerate(changes):
            apply_item = _read_only_table_item("")
            apply_item.setFlags(apply_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            apply_item.setCheckState(Qt.CheckState.Checked if change.included else Qt.CheckState.Unchecked)
            apply_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.changes_table.setItem(row, 0, apply_item)
            values = [
                change.scope,
                change.library,
                change.item,
                change.field,
                _table_value(change.original),
                _table_value(change.current),
                change.source,
            ]
            for column, value in enumerate(values, start=1):
                self.changes_table.setItem(row, column, _read_only_table_item(value))
        self.changes_table.blockSignals(False)

        if not changes:
            self.changes_inspector.setPlainText("No pending metadata changes.")
            return
        self.changes_table.selectRow(0)
        self._show_pending_change(0)

    def _update_changes_tab_label(self, change_count: int) -> None:
        if not hasattr(self, "tabs") or not hasattr(self, "changes_tab_index"):
            return
        label = "Changes" if change_count == 0 else f"Changes ({change_count})"
        if self.tabs.tabText(self.changes_tab_index) != label:
            self.tabs.setTabText(self.changes_tab_index, label)

    def _changes_apply_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() != 0 or item.row() >= len(self._pending_changes):
            return

        change = self._pending_changes[item.row()]
        if change.item_ref is None:
            return
        cell = change.item_ref.cells.get(change.field)
        if cell is None:
            return

        cell.included_in_save = item.checkState() == Qt.CheckState.Checked
        self._pending_changes[item.row()] = replace(change, included=cell.included_in_save)
        if self.changes_table.currentRow() == item.row():
            self._show_pending_change(item.row())
        self._suppress_changes_refresh = True
        try:
            self._refresh_library_views_after_apply_change(change.item_ref)
        finally:
            self._suppress_changes_refresh = False
        self._update_action_buttons()

    def _refresh_library_views_after_apply_change(self, item: MockItem) -> None:
        tab_state = self.symbol_tab_state if item in self.symbol_items else self.footprint_tab_state
        tab_state.model.refresh_all()
        self._refresh_status_filter_counts(tab_state)

    def _checked_changes_have_metadata(self) -> bool:
        return any(change.included for change in getattr(self, "_pending_changes", []))

    def _show_pending_change(self, row: int) -> None:
        if not hasattr(self, "_pending_changes") or row < 0 or row >= len(self._pending_changes):
            if hasattr(self, "changes_inspector"):
                self.changes_inspector.setPlainText("No pending change selected.")
            return

        change = self._pending_changes[row]
        lines = [
            f"Scope: {change.scope}",
            f"Library: {change.library}",
            f"Item: {change.item}",
            f"Field: {change.field}",
            "",
            "Original",
            change.original,
            "",
            "Current",
            change.current,
            "",
            "Included in save" if change.included else "Excluded from save",
        ]
        if change.source:
            lines.extend(["", "Source", change.source])
        if change.source_path is not None:
            lines.extend(["", "Source path", str(change.source_path)])
        if change.detail:
            lines.extend(["", "Detail", change.detail])
        self.changes_inspector.setPlainText("\n".join(lines))

    def _refresh_history_tab(self) -> None:
        if not hasattr(self, "history_table"):
            return

        try:
            events = list(reversed(load_history_events(self.history_path)))
        except (OSError, json.JSONDecodeError) as error:
            self._history_events = []
            self.history_table.setRowCount(0)
            self.history_summary_label.setText("History could not be loaded.")
            self.history_inspector.setPlainText(str(error))
            return

        self._history_events = events
        self.history_summary_label.setText(f"History events: {len(events)}")
        self.history_table.blockSignals(True)
        self.history_table.setRowCount(len(events))
        for row, event in enumerate(events):
            values = [
                event.timestamp,
                event.action,
                event.scope,
                event.library,
                event.item,
                event.field,
                event.status,
            ]
            for column, value in enumerate(values):
                self.history_table.setItem(row, column, _read_only_table_item(value))
        self.history_table.blockSignals(False)

        if not events:
            self.history_inspector.setPlainText("No saved history events.")
            return
        self.history_table.selectRow(0)
        self._show_history_event(0)

    def _show_history_event(self, row: int) -> None:
        if not hasattr(self, "_history_events") or row < 0 or row >= len(self._history_events):
            if hasattr(self, "history_inspector"):
                self.history_inspector.setPlainText("No history event selected.")
            return

        event = self._history_events[row]
        lines = [
            f"Time: {event.timestamp}",
            f"Action: {event.action}",
            f"Scope: {event.scope}",
            f"Library / Policy: {event.library}",
            f"Item: {event.item}",
            f"Field: {event.field}",
            f"Status: {event.status}",
        ]
        if event.source_path:
            lines.extend(["", "Source path", event.source_path])
        if event.detail:
            lines.extend(["", "Detail", event.detail])
        lines.extend(
            [
                "",
                "Original",
                _history_value_text(event.original),
                "",
                "Current",
                _history_value_text(event.current),
            ]
        )
        if event.metadata:
            lines.extend(["", "Metadata", _history_value_text(event.metadata)])
        self.history_inspector.setPlainText("\n".join(lines))

    def _append_history_events(self, events: list[HistoryEvent]) -> None:
        if not events:
            return
        try:
            append_history_events(self.history_path, events)
        except OSError as error:
            QMessageBox.warning(self, "History Save Failed", str(error))
            return
        self._refresh_history_tab()

    def _audit_rules_tab(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(12)

        self.audit_policy_list = QListWidget()
        self.audit_policy_list.setMinimumWidth(340)
        self.audit_policy_details = ReadOnlyInfoPanel("Select a policy to inspect it.")
        self.audit_enabled_checkbox = QCheckBox("Enabled")
        self.audit_apply_new_checkbox = QCheckBox("Apply to new libraries when added")
        self.audit_apply_new_checkbox.setToolTip(
            "When new libraries are added later, include them in this policy by default."
        )
        self.audit_target_symbols = QRadioButton("Symbols")
        self.audit_target_footprints = QRadioButton("Footprints")
        self.audit_target_both = QRadioButton("Symbols and Footprints")
        self.audit_target_group = QButtonGroup(self)
        self.audit_target_group.addButton(self.audit_target_symbols)
        self.audit_target_group.addButton(self.audit_target_footprints)
        self.audit_target_group.addButton(self.audit_target_both)
        self.audit_severity_error = QRadioButton("Error")
        self.audit_severity_warning = QRadioButton("Warning")
        self.audit_severity_ignore = QRadioButton("Ignore")
        self.audit_severity_group = QButtonGroup(self)
        self.audit_severity_group.addButton(self.audit_severity_error)
        self.audit_severity_group.addButton(self.audit_severity_warning)
        self.audit_severity_group.addButton(self.audit_severity_ignore)
        self.audit_library_table = QTableWidget(0, 2)
        self.audit_library_table.setHorizontalHeaderLabels(["Installed Libraries", "Violations"])
        self.audit_library_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.audit_library_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.audit_library_table.verticalHeader().setVisible(False)
        self.audit_library_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.audit_library_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.audit_library_table.setMinimumWidth(260)

        self.audit_rule_list = QListWidget()
        self.audit_rule_list.setMinimumHeight(130)
        new_rule_button = QPushButton("New...")
        edit_rule_button = QPushButton("Edit...")
        delete_rule_button = QPushButton("Delete")
        new_rule_button.clicked.connect(lambda: self._show_rule_editor(new_rule=True))
        edit_rule_button.clicked.connect(lambda: self._show_rule_editor(new_rule=False))
        delete_rule_button.clicked.connect(self._delete_current_rule)

        for policy in self.policy_profiles:
            item = QListWidgetItem(self._audit_policy_item_text(policy))
            item.setIcon(_ui_icon("audit"))
            item.setData(Qt.ItemDataRole.UserRole, policy)
            self.audit_policy_list.addItem(item)

        self.audit_policy_list.currentItemChanged.connect(
            lambda current, _previous: self._show_policy_configuration(current)
        )
        for control in [
            self.audit_enabled_checkbox,
            self.audit_apply_new_checkbox,
            self.audit_target_symbols,
            self.audit_target_footprints,
            self.audit_target_both,
            self.audit_severity_error,
            self.audit_severity_warning,
            self.audit_severity_ignore,
        ]:
            control.toggled.connect(self._audit_policy_controls_changed)
        self.audit_library_table.itemChanged.connect(self._audit_library_item_changed)

        policy_side = QWidget()
        policy_layout = QVBoxLayout(policy_side)
        policy_layout.setContentsMargins(0, 0, 0, 0)
        policy_layout.addWidget(QLabel("Policies"))
        policy_layout.addWidget(self.audit_policy_list)

        center_side = QWidget()
        center_layout = QVBoxLayout(center_side)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(10)
        checkbox_row = QHBoxLayout()
        checkbox_row.addWidget(self.audit_enabled_checkbox)
        checkbox_row.addWidget(self.audit_apply_new_checkbox)
        checkbox_row.addStretch()
        center_layout.addLayout(checkbox_row)
        center_layout.addLayout(_labeled_radio_row("Applies to", [
            self.audit_target_symbols,
            self.audit_target_footprints,
            self.audit_target_both,
        ]))
        center_layout.addLayout(_labeled_radio_row("Severity", [
            self.audit_severity_error,
            self.audit_severity_warning,
            self.audit_severity_ignore,
        ]))
        center_layout.addWidget(self.audit_policy_details, 2)
        center_layout.addWidget(QLabel("Rules"))
        rule_row = QHBoxLayout()
        rule_row.addWidget(self.audit_rule_list, 1)
        rule_button_column = QVBoxLayout()
        rule_button_column.addWidget(new_rule_button)
        rule_button_column.addWidget(edit_rule_button)
        rule_button_column.addWidget(delete_rule_button)
        rule_button_column.addStretch()
        rule_row.addLayout(rule_button_column)
        center_layout.addLayout(rule_row)

        library_side = QWidget()
        library_layout = QVBoxLayout(library_side)
        library_layout.setContentsMargins(0, 0, 0, 0)
        library_layout.addWidget(QLabel("Installed Libraries"))
        library_layout.addWidget(self.audit_library_table)

        self._refresh_audit_violation_display()
        if self.audit_policy_list.count():
            self.audit_policy_list.setCurrentRow(0)

        layout.addWidget(policy_side, 2)
        layout.addWidget(center_side, 3)
        layout.addWidget(library_side, 2)
        return widget

    def _show_policy_configuration(self, item: QListWidgetItem | None) -> None:
        if item is None:
            self.audit_policy_details.setPlainText("Select a policy to inspect it.")
            self._update_action_buttons()
            return

        policy: PolicyProfile = item.data(Qt.ItemDataRole.UserRole)
        settings = self.audit_policy_settings[policy.profile_id]
        self._updating_audit_controls = True
        self.audit_enabled_checkbox.setChecked(settings.enabled)
        self.audit_apply_new_checkbox.setChecked(settings.apply_to_new_libraries)
        self.audit_target_symbols.setChecked(settings.target == "symbol")
        self.audit_target_footprints.setChecked(settings.target == "footprint")
        self.audit_target_both.setChecked(settings.target == "both")
        self.audit_severity_error.setChecked(settings.severity == "error")
        self.audit_severity_warning.setChecked(settings.severity == "warning")
        self.audit_severity_ignore.setChecked(settings.severity == "ignore")
        self._populate_audit_library_table(settings)
        self._populate_audit_rule_list(policy)
        self._updating_audit_controls = False

        lines = [
            policy.name,
            policy.description,
            "",
            f"ID: {policy.profile_id}",
            f"Enabled: {'yes' if settings.enabled else 'no'}",
            f"Severity: {settings.severity.title()}",
            f"Applies to: {_policy_target_label(settings.target)}",
            f"Rules: {len(policy.rules)}",
            f"Unsaved changes: {'yes' if self._audit_policy_has_unsaved_changes(policy.profile_id) else 'no'}",
        ]
        if policy.profile_id == "library-validation-policy":
            lines.extend(
                [
                    "",
                    "Default applicability",
                    "GRAPHICS libraries start unchecked for this policy because symbolic schematic artwork and silkscreen-only footprints often do not need datasheets, associated footprints, or 3D models.",
                ]
            )
        if policy.rules:
            lines.extend(["", "Checks"])
            lines.extend(f"- {rule.name} [{rule.rule_type}]" for rule in policy.rules)
        overlap_lines = _policy_field_overlap_lines(policy, self.policy_profiles)
        if overlap_lines:
            lines.extend(["", "Related field coverage"])
            lines.extend(overlap_lines)
        lines.extend(
            [
                "",
                "Use New or Edit to maintain required-field and regex rules.",
                "Symbols and Footprints remain the primary places to inspect individual findings.",
            ]
        )
        self.audit_policy_details.setPlainText("\n".join(lines))
        self._update_action_buttons()

    def _audit_policy_controls_changed(self) -> None:
        if getattr(self, "_updating_audit_controls", False):
            return

        settings = self._current_audit_policy_settings()
        if settings is None:
            return

        old_target = settings.target
        settings.enabled = self.audit_enabled_checkbox.isChecked()
        settings.apply_to_new_libraries = self.audit_apply_new_checkbox.isChecked()
        settings.target = self._selected_audit_target()
        settings.severity = self._selected_audit_severity()
        if settings.target != old_target:
            available_libraries = self._audit_libraries_for_target(settings.target)
            settings.enabled_libraries &= available_libraries
            if settings.apply_to_new_libraries:
                settings.enabled_libraries |= available_libraries
            settings.known_libraries = set(available_libraries)
        settings.known_libraries |= self._audit_libraries_for_target(settings.target)
        self._refresh_policy_findings()
        self._refresh_current_audit_policy_item()
        self._show_policy_configuration(self.audit_policy_list.currentItem())
        self._update_action_buttons()

    def _audit_library_item_changed(self, item: QTableWidgetItem) -> None:
        if getattr(self, "_updating_audit_controls", False):
            return
        if item.column() != 0:
            return

        settings = self._current_audit_policy_settings()
        if settings is None:
            return

        library = item.data(Qt.ItemDataRole.UserRole)
        if item.checkState() == Qt.CheckState.Checked:
            settings.enabled_libraries.add(library)
        else:
            settings.enabled_libraries.discard(library)
        settings.known_libraries.add(library)
        self._refresh_policy_findings()
        self._refresh_current_audit_policy_item()
        self._show_policy_configuration(self.audit_policy_list.currentItem())
        self._update_action_buttons()

    def _current_audit_policy_settings(self) -> AuditPolicySettings | None:
        item = self.audit_policy_list.currentItem()
        if item is None:
            return None
        policy: PolicyProfile = item.data(Qt.ItemDataRole.UserRole)
        return self.audit_policy_settings[policy.profile_id]

    def _populate_audit_library_table(self, settings: AuditPolicySettings) -> None:
        self._updating_audit_controls = True
        libraries = sorted(
            self._audit_libraries_for_target(settings.target),
            key=lambda library: (_library_display_alias(library, self.symbol_items, self.footprint_items), library),
        )
        self.audit_library_table.setRowCount(len(libraries))
        for row, library in enumerate(libraries):
            library_item = QTableWidgetItem(_library_display_alias(library, self.symbol_items, self.footprint_items))
            library_item.setIcon(_ui_icon(_audit_library_kind(library, self.symbol_items, self.footprint_items)))
            library_item.setData(Qt.ItemDataRole.UserRole, library)
            library_item.setFlags(library_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            library_item.setCheckState(
                Qt.CheckState.Checked
                if library in settings.enabled_libraries
                else Qt.CheckState.Unchecked
            )
            self.audit_library_table.setItem(row, 0, library_item)
            violation_item = QTableWidgetItem(_audit_library_violation_text(library, settings, self.policy_findings))
            violation_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.audit_library_table.setItem(row, 1, violation_item)
        self._updating_audit_controls = False

    def _populate_audit_rule_list(self, policy: PolicyProfile) -> None:
        self.audit_rule_list.clear()
        for rule in policy.rules:
            item = QListWidgetItem(f"{rule.name} [{rule.rule_type}]")
            item.setData(Qt.ItemDataRole.UserRole, rule)
            self.audit_rule_list.addItem(item)
        if self.audit_rule_list.count():
            self.audit_rule_list.setCurrentRow(0)

    def _show_rule_editor(self, *, new_rule: bool) -> None:
        rule = None if new_rule else self._current_audit_rule()
        dialog = RuleEditorDialog(
            fields=_discovered_field_names(self.symbol_items, self.footprint_items),
            rule=rule,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        profile = self._current_audit_policy()
        if profile is None:
            return

        existing_rule_ids = [
            candidate.rule_id
            for candidate in profile.rules
            if rule is None or candidate.rule_id != rule.rule_id
        ]
        try:
            updated_rule = dialog.to_rule(existing_rule_ids=existing_rule_ids)
        except ValueError as error:
            QMessageBox.warning(self, "Rule Incomplete", str(error))
            return

        rules = list(profile.rules)
        if rule is None:
            rules.append(updated_rule)
        else:
            rules = [
                updated_rule if candidate.rule_id == rule.rule_id else candidate
                for candidate in rules
            ]
        self._replace_current_policy(replace(profile, rules=rules))

    def _delete_current_rule(self) -> None:
        rule = self._current_audit_rule()
        profile = self._current_audit_policy()
        if rule is None or profile is None:
            return

        response = QMessageBox.question(
            self,
            "Delete Rule",
            f"Delete rule '{rule.name}' from {profile.name}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if response != QMessageBox.StandardButton.Yes:
            return

        self._replace_current_policy(
            replace(
                profile,
                rules=[candidate for candidate in profile.rules if candidate.rule_id != rule.rule_id],
            )
        )

    def _current_audit_policy(self) -> PolicyProfile | None:
        item = self.audit_policy_list.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _current_audit_rule(self) -> PolicyRule | None:
        item = self.audit_rule_list.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _replace_current_policy(self, profile: PolicyProfile) -> None:
        current_item = self.audit_policy_list.currentItem()
        if current_item is None:
            return

        self.policy_profiles = [
            profile if candidate.profile_id == profile.profile_id else candidate
            for candidate in self.policy_profiles
        ]
        settings = self.audit_policy_settings[profile.profile_id]
        settings.profile = profile
        current_item.setData(Qt.ItemDataRole.UserRole, profile)
        current_item.setText(self._audit_policy_item_text(profile))
        self._refresh_policy_findings()
        self._show_policy_configuration(current_item)
        self._update_action_buttons()

    def _save_policy_override(self, profile: PolicyProfile) -> None:
        policy_path = _workspace_policy_file_path(self.workspace_config_path, profile)
        save_policy_profile(profile, policy_path)
        if not _workspace_config_has_policy_file(self.workspace_config, policy_path):
            self.workspace_config.policy_files.append(LibrarySelection(str(policy_path)))
        save_workspace_config(self.workspace_config, self.workspace_config_path)

    def _audit_libraries_for_target(self, target: str) -> set[str]:
        libraries: set[str] = set()
        if target in {"symbol", "both"}:
            libraries.update(item.library for item in self.symbol_items if item.auditable)
        if target in {"footprint", "both"}:
            libraries.update(item.library for item in self.footprint_items if item.auditable)
        return libraries

    def _sync_audit_policy_libraries(self) -> None:
        for settings in self.audit_policy_settings.values():
            available_libraries = self._audit_libraries_for_target(settings.target)
            new_libraries = available_libraries - settings.known_libraries
            if settings.apply_to_new_libraries:
                settings.enabled_libraries |= new_libraries
            settings.enabled_libraries &= available_libraries
            settings.known_libraries = available_libraries

    def _selected_audit_target(self) -> str:
        if self.audit_target_symbols.isChecked():
            return "symbol"
        if self.audit_target_footprints.isChecked():
            return "footprint"
        return "both"

    def _selected_audit_severity(self) -> str:
        if self.audit_severity_error.isChecked():
            return "error"
        if self.audit_severity_ignore.isChecked():
            return "ignore"
        return "warning"

    def _refresh_audit_violation_display(self) -> None:
        if hasattr(self, "audit_library_table"):
            settings = self._current_audit_policy_settings()
            if settings is not None:
                self._populate_audit_library_table(settings)

    def _show_cell(self, index: QModelIndex, model: ComponentTableModel, inspector: ReadOnlyInfoPanel) -> None:
        if not index.isValid():
            return

        item = model.items[index.row()]
        column_name = model.columns[index.column()]
        cell = model._cell_for(index)

        lines = [
            f"Item: {item.name}",
            f"Library: {item.display_library}",
            f"Field: {column_name}",
            "",
        ]
        if item.display_library != item.library:
            lines.extend(["Source library", item.library, ""])

        if cell:
            lines.extend(
                [
                    "Original",
                    cell.original_value,
                    "",
                    "Current",
                    cell.working_value,
                    "",
                    "Status",
                    "Changed" if cell.is_changed else "Unchanged",
                    "Included in save" if cell.included_in_save else "Excluded from save",
                ]
            )
            if cell.issues:
                lines.extend(["", "Issues"])
                for issue in cell.issues:
                    lines.append(f"{issue.severity.value.upper()}: {issue.title}")
                    if issue.policy_name:
                        lines.append(f"Policy: {issue.policy_name}")
                    if issue.rule_name:
                        lines.append(f"Rule: {issue.rule_name}")
                    if issue.detail:
                        lines.append(issue.detail)
        else:
            lines.append("Fixed item metadata column.")

        inspector.setPlainText("\n".join(lines))

    def _show_configuration_dialog(self, require_layout_profile: bool = False) -> bool:
        dialog = ConfigurationDialog(self.workspace_config, self, require_layout_profile=require_layout_profile)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.workspace_config = dialog.to_config()
            save_workspace_config(self.workspace_config, self.workspace_config_path)
            self.workspace_setup_message = ""
            self._begin_deferred_library_load()
            QMessageBox.information(self, "Configuration", "Workspace configuration saved.")
            return True
        return False

    def _show_preferences_dialog(self) -> None:
        QMessageBox.information(
            self,
            "Preferences",
            "Preferences will be added as application-wide options emerge.",
        )

    def _save_selected(self) -> None:
        if self._changes_tab_is_current():
            self._save_applied_changes_tab_metadata()
            return
        if not self._audit_tab_is_current():
            self._save_current_library_tab_changes()
            return

        profile = self._current_audit_policy()
        settings = self._current_audit_policy_settings()
        if profile is None or settings is None:
            return

        policy_path = _workspace_policy_file_path(self.workspace_config_path, profile)
        history_events = _history_events_for_policy_save(
            profile,
            settings,
            self._saved_policy_profiles_by_id.get(profile.profile_id),
            self._saved_audit_policy_settings.get(profile.profile_id, {}),
            policy_path,
        )
        self._save_policy_override(profile)
        self._save_audit_policy_settings(settings)
        self._append_history_events(history_events)
        self._saved_policy_profiles_by_id[profile.profile_id] = copy.deepcopy(profile)
        self._saved_audit_policy_settings[profile.profile_id] = _audit_policy_settings_to_dict(settings)
        self._refresh_current_audit_policy_item()
        self._show_policy_configuration(self.audit_policy_list.currentItem())
        self._refresh_changes_tab()
        self._update_action_buttons()
        self._show_inline_status(f"Saved audit policy: {profile.name}", 5000)

    def _save_applied_changes_tab_metadata(self) -> None:
        items = [*self.symbol_items, *self.footprint_items]
        changes = _kicad_metadata_changes_for_items(items)
        if not changes:
            self._show_inline_status("No applied metadata changes to save.", 5000)
            self._update_action_buttons()
            return

        try:
            save_metadata_changes(changes)
        except KiCadWriteError as error:
            QMessageBox.warning(self, "Save Failed", str(error))
            return

        self._append_history_events(_history_events_for_metadata_save(items))
        _mark_saved_metadata_changes(items)
        self.symbol_tab_state.model.refresh_all()
        self.footprint_tab_state.model.refresh_all()
        self._refresh_policy_findings()
        self._refresh_changes_tab()
        self._update_action_buttons()
        self._show_inline_status(f"Saved {len(changes)} applied metadata changes.", 5000)

    def _save_current_library_tab_changes(self) -> None:
        tab_state = self._current_library_tab_state()
        items = self._current_library_tab_items()
        if tab_state is None or items is None:
            self._show_mock_action("Save Selected")
            return

        changes = _kicad_metadata_changes_for_items(items)
        if not changes:
            self._show_inline_status("No included KiCad metadata changes to save.", 5000)
            self._update_action_buttons()
            return

        try:
            save_metadata_changes(changes)
        except KiCadWriteError as error:
            QMessageBox.warning(self, "Save Failed", str(error))
            return

        self._append_history_events(_history_events_for_metadata_save(items))
        _mark_saved_metadata_changes(items)
        tab_state.model.refresh_all()
        self._refresh_policy_findings()
        self._refresh_changes_tab()
        self._update_action_buttons()
        self._show_inline_status(f"Saved {len(changes)} KiCad metadata changes.", 5000)

    def _revert_selected(self) -> None:
        if self._changes_tab_is_current():
            self._revert_applied_changes_tab_metadata()
            return
        if not self._audit_tab_is_current():
            self._revert_current_library_tab_changes()
            return

        profile = self._current_audit_policy()
        if profile is None:
            return

        saved_profile = self._saved_policy_profiles_by_id.get(profile.profile_id)
        if saved_profile is None:
            return

        replacement = copy.deepcopy(saved_profile)
        self._replace_policy_in_memory(replacement)
        self.audit_policy_settings[replacement.profile_id] = audit_policy_settings_from_profiles(
            [replacement],
            self.symbol_items,
            self.footprint_items,
            {replacement.profile_id: self._saved_audit_policy_settings.get(replacement.profile_id, {})},
        )[replacement.profile_id]

        current_item = self.audit_policy_list.currentItem()
        if current_item is not None:
            current_item.setData(Qt.ItemDataRole.UserRole, replacement)
            current_item.setText(self._audit_policy_item_text(replacement))
        self._refresh_policy_findings()
        self._show_policy_configuration(current_item)
        self._refresh_changes_tab()
        self._update_action_buttons()
        self._show_inline_status(f"Reverted audit policy: {replacement.name}", 5000)

    def _revert_all(self) -> None:
        if self._changes_tab_is_current():
            self._revert_all_changes_tab_metadata()
            return
        if not self._audit_tab_is_current():
            self._revert_current_library_tab_changes()
            return

        selected_profile_id = None
        current_policy = self._current_audit_policy()
        if current_policy is not None:
            selected_profile_id = current_policy.profile_id

        self.policy_profiles = [
            copy.deepcopy(self._saved_policy_profiles_by_id.get(profile.profile_id, profile))
            for profile in self.policy_profiles
        ]
        self.audit_policy_settings = audit_policy_settings_from_profiles(
            self.policy_profiles,
            self.symbol_items,
            self.footprint_items,
            self._saved_audit_policy_settings,
        )
        for row, profile in enumerate(self.policy_profiles):
            item = self.audit_policy_list.item(row)
            item.setData(Qt.ItemDataRole.UserRole, profile)
            item.setText(self._audit_policy_item_text(profile))

        if selected_profile_id is not None:
            _select_audit_policy_row(self.audit_policy_list, selected_profile_id)
        self._refresh_policy_findings()
        self._show_policy_configuration(self.audit_policy_list.currentItem())
        self._refresh_changes_tab()
        self._update_action_buttons()
        self._show_inline_status("Reverted all audit policy changes.", 5000)

    def _revert_applied_changes_tab_metadata(self) -> None:
        reverted_count = _revert_metadata_changes([*self.symbol_items, *self.footprint_items], included_only=True)
        self.symbol_tab_state.model.refresh_all()
        self.footprint_tab_state.model.refresh_all()
        self._refresh_policy_findings()
        self._refresh_changes_tab()
        self._update_action_buttons()
        self._show_inline_status(f"Reverted {reverted_count} applied metadata changes.", 5000)

    def _revert_all_changes_tab_metadata(self) -> None:
        reverted_count = _revert_metadata_changes([*self.symbol_items, *self.footprint_items])
        self.symbol_tab_state.model.refresh_all()
        self.footprint_tab_state.model.refresh_all()
        self._refresh_policy_findings()
        self._refresh_changes_tab()
        self._update_action_buttons()
        self._show_inline_status(f"Reverted {reverted_count} metadata changes.", 5000)

    def _revert_current_library_tab_changes(self) -> None:
        tab_state = self._current_library_tab_state()
        items = self._current_library_tab_items()
        if tab_state is None or items is None:
            self._show_mock_action("Revert Selected")
            return

        reverted_count = _revert_metadata_changes(items)
        tab_state.model.refresh_all()
        self._refresh_policy_findings()
        self._refresh_changes_tab()
        self._update_action_buttons()
        self._show_inline_status(f"Reverted {reverted_count} metadata changes.", 5000)

    def _current_library_tab_state(self) -> LibraryTabState | None:
        tab_name = self.tabs.tabText(self.tabs.currentIndex())
        if tab_name == "Symbols":
            return self.symbol_tab_state
        if tab_name == "Footprints":
            return self.footprint_tab_state
        return None

    def _current_library_tab_items(self) -> list[MockItem] | None:
        tab_name = self.tabs.tabText(self.tabs.currentIndex())
        if tab_name == "Symbols":
            return self.symbol_items
        if tab_name == "Footprints":
            return self.footprint_items
        return None

    def _audit_tab_is_current(self) -> bool:
        return hasattr(self, "tabs") and self.tabs.tabText(self.tabs.currentIndex()) == "Audit"

    def _changes_tab_is_current(self) -> bool:
        return hasattr(self, "tabs") and self.tabs.currentIndex() == getattr(self, "changes_tab_index", -1)

    def _update_action_buttons(self) -> None:
        if not all(
            hasattr(self, attribute)
            for attribute in [
                "save_selected_button",
                "revert_selected_button",
                "revert_all_button",
            ]
        ):
            return

        selected_dirty = self._current_tab_selected_dirty()
        any_dirty = self._current_tab_any_dirty()
        if self._changes_tab_is_current():
            self.save_selected_button.setText("Save Applied")
            self.revert_selected_button.setText("Revert Applied")
        else:
            self.save_selected_button.setText("Save Selected")
            self.revert_selected_button.setText("Revert Selected")
        self.save_selected_button.setEnabled(selected_dirty)
        self.revert_selected_button.setEnabled(selected_dirty)
        self.revert_all_button.setEnabled(any_dirty)

    def _current_tab_selected_dirty(self) -> bool:
        tab_name = self.tabs.tabText(self.tabs.currentIndex())
        if tab_name == "Audit":
            policy = self._current_audit_policy()
            return policy is not None and self._audit_policy_has_unsaved_changes(policy.profile_id)
        if tab_name == "Symbols":
            return _items_have_changes(self.symbol_items)
        if tab_name == "Footprints":
            return _items_have_changes(self.footprint_items)
        if self._changes_tab_is_current():
            return self._checked_changes_have_metadata()
        return False

    def _current_tab_any_dirty(self) -> bool:
        tab_name = self.tabs.tabText(self.tabs.currentIndex())
        if tab_name == "Audit":
            return any(
                self._audit_policy_has_unsaved_changes(profile.profile_id)
                for profile in self.policy_profiles
            )
        if tab_name == "Symbols":
            return _items_have_changes(self.symbol_items)
        if tab_name == "Footprints":
            return _items_have_changes(self.footprint_items)
        if self._changes_tab_is_current():
            return _items_have_changes([*self.symbol_items, *self.footprint_items])
        return False

    def _save_audit_policy_settings(self, settings: AuditPolicySettings) -> None:
        self.workspace_config.kia_interop = dict(self.workspace_config.kia_interop)
        policy_settings = _audit_policy_settings_overrides_from_config(self.workspace_config)
        policy_settings[settings.profile.profile_id] = _audit_policy_settings_to_dict(settings)
        self.workspace_config.kia_interop["audit_policy_settings"] = policy_settings
        save_workspace_config(self.workspace_config, self.workspace_config_path)

    def _replace_policy_in_memory(self, profile: PolicyProfile) -> None:
        self.policy_profiles = [
            profile if candidate.profile_id == profile.profile_id else candidate
            for candidate in self.policy_profiles
        ]

    def _audit_policy_item_text(self, policy: PolicyProfile) -> str:
        suffix = " *" if self._audit_policy_has_unsaved_changes(policy.profile_id) else ""
        return f"{policy.name} ({len(policy.rules)} rules){suffix}"

    def _audit_policy_has_unsaved_changes(self, profile_id: str) -> bool:
        current_profile = _policy_by_id(self.policy_profiles, profile_id)
        saved_profile = self._saved_policy_profiles_by_id.get(profile_id)
        if current_profile is not None and saved_profile is not None and current_profile != saved_profile:
            return True

        settings = self.audit_policy_settings.get(profile_id)
        if settings is None:
            return False
        return _audit_policy_settings_to_dict(settings) != self._saved_audit_policy_settings.get(profile_id, {})

    def _refresh_current_audit_policy_item(self) -> None:
        item = self.audit_policy_list.currentItem()
        if item is None:
            return
        policy = self._current_audit_policy()
        if policy is not None:
            item.setText(self._audit_policy_item_text(policy))

    def _show_mock_action(self, action_name: str) -> None:
        QMessageBox.information(self, action_name, f"{action_name} will operate on pending changes in a later slice.")

    def _show_color_legend(self) -> None:
        QMessageBox.information(
            self,
            "Cell Color Legend",
            "\n".join(
                [
                    "Green: manual pending change",
                    "Yellow: rule-generated pending change",
                    "Orange: suspicious or policy issue",
                    "Red: pending field deletion",
                    "",
                    "Bold text means the current value differs from the baseline.",
                    "Italic text will mark inherited values in a later slice.",
                    "Strike-through marks pending deletion when the text remains visible.",
                ]
            ),
        )

    def _show_policy_guidance(self) -> None:
        QMessageBox.information(
            self,
            "Policy Guidance",
            "\n".join(
                [
                    "Audit policies run read-only checks against loaded symbol and footprint metadata.",
                    "",
                    "Use the Audit tab to enable a policy, choose its severity, select whether it applies to Symbols, Footprints, or both, and opt installed libraries in or out.",
                    "",
                    "Individual violations appear in the Symbols and Footprints tables.",
                    "",
                    "Starter examples live in examples/policies:",
                    "minimal-library-policy.json",
                    "procurement-fields-policy.json",
                    "fab-readability-policy.json",
                    "datasheet-link-policy.json",
                    "library-validation-policy.json",
                    "manufacturer-part-policy.json",
                ]
            ),
        )


class ConfigurationDialog(QDialog):
    def __init__(
        self,
        config: WorkspaceConfig,
        parent: QWidget | None = None,
        *,
        require_layout_profile: bool = False,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.require_layout_profile = require_layout_profile
        self.setWindowTitle("Configuration")
        self.resize(720, 560)

        layout = QVBoxLayout(self)
        form_layout = QFormLayout()

        root_row = QWidget()
        root_layout = QHBoxLayout(root_row)
        root_layout.setContentsMargins(0, 0, 0, 0)
        self.library_root_input = QLineEdit()
        self.library_root_input.setText(config.library_root)
        self.library_root_input.setPlaceholderText("Choose a local KiCad library root")
        browse_button = QPushButton("Browse...")
        browse_button.clicked.connect(self._choose_library_root)
        root_layout.addWidget(self.library_root_input)
        root_layout.addWidget(browse_button)
        form_layout.addRow("Library root", root_row)

        self.path_variable_input = QLineEdit()
        self.path_variable_input.setText(config.path_variable)
        self.path_variable_input.setPlaceholderText("KiCad path variable, such as KICAD_USER_LIB")
        form_layout.addRow("Path variable", self.path_variable_input)

        self.layout_profiles = _load_configuration_layout_profiles()
        self.layout_profile_combo = QComboBox()
        self.layout_profile_combo.addItem("No layout selected", "")
        placeholder_item = self.layout_profile_combo.model().item(0)
        if placeholder_item is not None:
            placeholder_item.setEnabled(False)
        for profile in self.layout_profiles:
            self.layout_profile_combo.addItem(f"{profile.name} ({profile.profile_id})", profile.profile_id)

        selected_profile_index = self.layout_profile_combo.findData(config.layout_profile_id)
        if selected_profile_index >= 0:
            self.layout_profile_combo.setCurrentIndex(selected_profile_index)
        self.layout_profile_combo.setToolTip("Select how this workspace organizes symbols, footprints, and models.")
        self.layout_profile_combo.currentIndexChanged.connect(self._update_layout_profile_details)
        form_layout.addRow("Library layout", self.layout_profile_combo)

        self.layout_profile_details = ReadOnlyInfoPanel()
        self.layout_profile_details.setMaximumHeight(150)
        form_layout.addRow("Layout details", self.layout_profile_details)
        self._update_layout_profile_details()

        self.footprint_libraries = QListWidget()
        self._populate_list(self.footprint_libraries, config.footprint_libraries)
        form_layout.addRow("Footprint libraries", self._library_list_editor(self.footprint_libraries, self._add_footprint_library))

        self.symbol_libraries = QListWidget()
        self._populate_list(self.symbol_libraries, config.symbol_libraries)
        form_layout.addRow("Symbol libraries", self._library_list_editor(self.symbol_libraries, self._add_symbol_library))

        layout.addLayout(form_layout)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self) -> None:
        if self.require_layout_profile and not self.layout_profile_combo.currentData():
            QMessageBox.warning(
                self,
                "Library Layout Required",
                "Select a library layout before saving the workspace configuration.",
            )
            return
        super().accept()

    def _choose_library_root(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Choose Library Root", self.library_root_input.text())
        if directory:
            self.library_root_input.setText(directory)

    def _library_list_editor(self, list_widget: QListWidget, add_callback) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(list_widget)

        button_row = QHBoxLayout()
        add_button = QPushButton("Add...")
        add_button.clicked.connect(add_callback)
        remove_button = QPushButton("Remove Selected")
        remove_button.clicked.connect(lambda: self._remove_selected_items(list_widget))
        button_row.addWidget(add_button)
        button_row.addWidget(remove_button)
        button_row.addStretch()
        layout.addLayout(button_row)

        return widget

    def _add_symbol_library(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Add Symbol Libraries",
            self.library_root_input.text(),
            "KiCad symbol libraries (*.kicad_sym);;All files (*.*)",
        )
        for file_path in files:
            self._add_checked_item(self.symbol_libraries, file_path)

    def _add_footprint_library(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self,
            "Add Footprint Library",
            self.library_root_input.text(),
        )
        if directory:
            self._add_checked_item(self.footprint_libraries, directory)
            self._add_matching_symbol_library(directory)

    def _remove_selected_items(self, list_widget: QListWidget) -> None:
        for item in list_widget.selectedItems():
            list_widget.takeItem(list_widget.row(item))

    def _populate_list(self, list_widget: QListWidget, selections: list[LibrarySelection]) -> None:
        for selection in selections:
            self._add_checked_item(list_widget, selection.path, selection.enabled)

    def _add_checked_item(self, list_widget: QListWidget, text: str, checked: bool = True) -> None:
        if self._list_contains_text(list_widget, text):
            return
        item = QListWidgetItem(text)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        list_widget.addItem(item)

    def _add_matching_symbol_library(self, footprint_library: str) -> None:
        symbol_library = self._symbol_library_for_footprint(footprint_library)
        if symbol_library is not None:
            self._add_checked_item(self.symbol_libraries, str(symbol_library))

    def _symbol_library_for_footprint(self, footprint_library: str) -> Path | None:
        candidates = candidate_symbol_libraries_for_footprint(footprint_library)
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            return self._choose_symbol_library_for_footprint(footprint_library)
        return self._create_symbol_library_for_footprint(footprint_library)

    def _choose_symbol_library_for_footprint(self, footprint_library: str) -> Path | None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose Symbol Library",
            footprint_library,
            "KiCad symbol libraries (*.kicad_sym);;All files (*.*)",
        )
        return Path(file_path) if file_path else None

    def _create_symbol_library_for_footprint(self, footprint_library: str) -> Path | None:
        symbol_library = default_symbol_library_for_footprint(footprint_library)
        if symbol_library is None:
            return None
        response = QMessageBox.question(
            self,
            "Create Symbol Library",
            "\n".join(
                [
                    "No KiCad symbol library was found for this footprint library.",
                    "",
                    "Create an empty symbol library?",
                    str(symbol_library),
                ]
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if response != QMessageBox.StandardButton.Yes:
            return None

        try:
            return create_symbol_library_for_footprint(footprint_library)
        except (OSError, ValueError) as error:
            QMessageBox.warning(
                self,
                "Symbol Library Not Created",
                f"KMFDM could not create a matching symbol library.\n\n{error}",
            )
            return None

    def _list_contains_text(self, list_widget: QListWidget, text: str) -> bool:
        return any(list_widget.item(row).text() == text for row in range(list_widget.count()))

    def _update_layout_profile_details(self) -> None:
        profile = self._selected_layout_profile()
        if profile is None:
            self.layout_profile_details.setPlainText(
                "\n".join(
                    [
                        "Select the layout that best describes where your custom KiCad libraries live.",
                        "",
                        "This choice does not scan, copy, or modify files yet. It only tells KMFDM how to interpret the workspace later.",
                    ]
                )
            )
            return

        self.layout_profile_details.setPlainText(
            "\n".join(
                [
                    profile.description,
                    "",
                    f"Footprints: {profile.paths.footprint_library}",
                    f"Symbols: {profile.paths.symbol_library}",
                    f"Models: {profile.paths.model_directory}",
                ]
            )
        )

    def _selected_layout_profile(self):
        profile_id = self.layout_profile_combo.currentData()
        return next((profile for profile in self.layout_profiles if profile.profile_id == profile_id), None)

    def to_config(self) -> WorkspaceConfig:
        return WorkspaceConfig(
            library_root=self.library_root_input.text().strip(),
            path_variable=self.path_variable_input.text().strip(),
            layout_profile_id=str(self.layout_profile_combo.currentData() or ""),
            symbol_libraries=self._list_to_selections(self.symbol_libraries),
            footprint_libraries=self._list_to_selections(self.footprint_libraries),
            policy_files=list(self.config.policy_files),
            kia_interop=dict(self.config.kia_interop),
        )

    def _list_to_selections(self, list_widget: QListWidget) -> list[LibrarySelection]:
        selections: list[LibrarySelection] = []
        for row in range(list_widget.count()):
            item = list_widget.item(row)
            selections.append(
                LibrarySelection(
                    path=item.text(),
                    enabled=item.checkState() == Qt.CheckState.Checked,
                )
            )
        return selections


def _load_configuration_layout_profiles():
    return load_bundled_layout_profiles()


def load_policy_profiles_for_workspace(
    config: WorkspaceConfig,
    workspace_config_path: Path,
) -> list[PolicyProfile]:
    bundled_profiles = load_bundled_policy_profiles()
    profiles_by_id = {profile.profile_id: profile for profile in bundled_profiles}
    profile_order = [profile.profile_id for profile in bundled_profiles]
    for selection in config.policy_files:
        if not selection.enabled:
            continue
        policy_path = _resolved_policy_file_path(selection.path, workspace_config_path)
        if not policy_path.is_file():
            continue
        try:
            profile = load_policy_profile(policy_path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if profile.profile_id not in profiles_by_id:
            profile_order.append(profile.profile_id)
        profiles_by_id[profile.profile_id] = profile
    return [profiles_by_id[profile_id] for profile_id in profile_order]


def _resolved_policy_file_path(path_text: str, workspace_config_path: Path) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    return workspace_config_path.parent / path


def _workspace_policy_file_path(workspace_config_path: Path, profile: PolicyProfile) -> Path:
    return workspace_config_path.parent / WORKSPACE_POLICY_DIRNAME / f"{profile.profile_id}.json"


def _workspace_config_has_policy_file(config: WorkspaceConfig, policy_path: Path) -> bool:
    policy_path = policy_path.resolve()
    return any(
        Path(selection.path).resolve() == policy_path
        for selection in config.policy_files
    )


def audit_policy_settings_from_profiles(
    profiles: list[PolicyProfile],
    symbol_items: list[MockItem],
    footprint_items: list[MockItem],
    overrides: dict[str, dict[str, object]] | None = None,
) -> dict[str, AuditPolicySettings]:
    settings: dict[str, AuditPolicySettings] = {}
    overrides = overrides or {}
    for profile in profiles:
        override = overrides.get(profile.profile_id, {})
        target = _audit_setting_target_from_value(
            override.get("target"),
            default=_policy_default_target(profile),
        )
        available_libraries = _audit_libraries_for_items(target, symbol_items, footprint_items)
        enabled_libraries = _default_enabled_audit_libraries(
            profile.profile_id,
            target,
            symbol_items,
            footprint_items,
        )
        known_libraries = set(available_libraries)
        apply_to_new_libraries = _bool_from_value(
            override.get("apply_to_new_libraries"),
            default=True,
        )
        if "enabled_libraries" in override:
            enabled_libraries = _string_set_from_value(override.get("enabled_libraries")) & available_libraries
        if "known_libraries" in override:
            saved_known_libraries = _string_set_from_value(override.get("known_libraries")) & available_libraries
            if apply_to_new_libraries:
                enabled_libraries |= available_libraries - saved_known_libraries
            known_libraries = set(available_libraries)
        settings[profile.profile_id] = AuditPolicySettings(
            profile=profile,
            enabled=_bool_from_value(override.get("enabled"), default=True),
            apply_to_new_libraries=apply_to_new_libraries,
            target=target,
            severity=_audit_setting_severity_from_value(
                override.get("severity"),
                default=_policy_default_severity(profile),
            ),
            enabled_libraries=enabled_libraries,
            known_libraries=known_libraries,
        )
    return settings


def _default_enabled_audit_libraries(
    profile_id: str,
    target: str,
    symbol_items: list[MockItem],
    footprint_items: list[MockItem],
) -> set[str]:
    libraries = _audit_libraries_for_items(target, symbol_items, footprint_items)
    if profile_id != "library-validation-policy":
        return libraries
    return {
        library
        for library in libraries
        if "GRAPHICS" not in _library_display_alias(library, symbol_items, footprint_items).upper()
        and "GRAPHICS" not in library.upper()
    }


def _audit_policy_settings_overrides_from_config(config: WorkspaceConfig) -> dict[str, dict[str, object]]:
    policy_settings = config.kia_interop.get("audit_policy_settings")
    if not isinstance(policy_settings, dict):
        return {}
    return {
        str(profile_id): dict(settings)
        for profile_id, settings in policy_settings.items()
        if isinstance(settings, dict)
    }


def _audit_policy_settings_to_dict(settings: AuditPolicySettings) -> dict[str, object]:
    return {
        "enabled": settings.enabled,
        "apply_to_new_libraries": settings.apply_to_new_libraries,
        "target": settings.target,
        "severity": settings.severity,
        "enabled_libraries": sorted(settings.enabled_libraries),
        "known_libraries": sorted(settings.known_libraries),
    }


def _bool_from_value(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default


def _audit_setting_target_from_value(value: object, *, default: str) -> str:
    return value if isinstance(value, str) and value in {"symbol", "footprint", "both"} else default


def _audit_setting_severity_from_value(value: object, *, default: str) -> str:
    return value if isinstance(value, str) and value in {"error", "warning", "ignore"} else default


def _string_set_from_value(value: object) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {item for item in value if isinstance(item, str)}


def _policy_default_target(profile: PolicyProfile) -> str:
    targets = {rule.target for rule in profile.rules}
    if targets == {"symbol"}:
        return "symbol"
    if targets == {"footprint"}:
        return "footprint"
    return "both"


def _policy_by_id(profiles: list[PolicyProfile], profile_id: str) -> PolicyProfile | None:
    for profile in profiles:
        if profile.profile_id == profile_id:
            return profile
    return None


def _select_audit_policy_row(policy_list: QListWidget, profile_id: str) -> None:
    for row in range(policy_list.count()):
        policy = policy_list.item(row).data(Qt.ItemDataRole.UserRole)
        if policy.profile_id == profile_id:
            policy_list.setCurrentRow(row)
            return


def _policy_default_severity(profile: PolicyProfile) -> str:
    for severity in ["error", "warning"]:
        if any(rule.severity == severity for rule in profile.rules):
            return severity
    return "warning"


def _policy_with_severity(profile: PolicyProfile, severity: str) -> PolicyProfile:
    return replace(
        profile,
        rules=[
            replace(rule, severity=severity if severity in {"error", "warning"} else rule.severity)
            for rule in profile.rules
        ],
    )


def _policy_target_applies_to_item(target: str, item: AuditItem) -> bool:
    return target == "both" or target == item.item_type


def _policy_target_label(target: str) -> str:
    if target == "symbol":
        return "Symbols"
    if target == "footprint":
        return "Footprints"
    return "Symbols and Footprints"


def _policy_field_overlap_lines(
    policy: PolicyProfile,
    profiles: list[PolicyProfile],
) -> list[str]:
    fields = _policy_rule_fields(policy)
    if not fields:
        return []

    overlap_by_field: dict[str, list[str]] = {}
    for other_policy in profiles:
        if other_policy.profile_id == policy.profile_id:
            continue
        other_fields = _policy_rule_fields(other_policy)
        for field_name in fields & other_fields:
            overlap_by_field.setdefault(field_name, []).append(other_policy.name)

    return [
        f"- {field}: also checked by {', '.join(sorted(policy_names))}"
        for field, policy_names in sorted(overlap_by_field.items())
    ]


def _policy_rule_fields(policy: PolicyProfile) -> set[str]:
    fields: set[str] = set()
    for rule in policy.rules:
        fields.update(_rule_fields(rule))
    return fields


def _rule_fields(rule: PolicyRule) -> set[str]:
    fields = set()
    for key in ["field", "canonical"]:
        value = rule.parameters.get(key)
        if isinstance(value, str) and value:
            fields.add(value)
    aliases = rule.parameters.get("aliases")
    if isinstance(aliases, list):
        fields.update(alias for alias in aliases if isinstance(alias, str) and alias)
    return fields


def _audit_libraries_for_items(
    target: str,
    symbol_items: list[MockItem],
    footprint_items: list[MockItem],
) -> set[str]:
    libraries: set[str] = set()
    if target in {"symbol", "both"}:
        libraries.update(item.library for item in symbol_items if item.auditable)
    if target in {"footprint", "both"}:
        libraries.update(item.library for item in footprint_items if item.auditable)
    return libraries


def _library_display_alias(
    library: str,
    symbol_items: list[MockItem],
    footprint_items: list[MockItem],
) -> str:
    for item in [*symbol_items, *footprint_items]:
        if item.library == library:
            return item.display_library
    return _base_library_alias(library)


def _clear_policy_issues(symbol_items: list[MockItem], footprint_items: list[MockItem]) -> None:
    for item in [*symbol_items, *footprint_items]:
        for cell in item.cells.values():
            cell.issues = [issue for issue in cell.issues if not issue.policy_name]


def _items_have_changes(items: list[MockItem]) -> bool:
    return any(cell.is_changed for item in items for cell in item.cells.values())


def _item_has_changes(item: MockItem) -> bool:
    return any(cell.is_changed for cell in item.cells.values())


def _item_has_issue_severity(item: MockItem, severity: IssueSeverity) -> bool:
    return any(
        issue.severity == severity
        for cell in item.cells.values()
        for issue in cell.issues
    )


def _issue_count_for_items(items: list[MockItem], severity: IssueSeverity) -> int:
    return sum(
        1
        for item in items
        for cell in item.cells.values()
        for issue in cell.issues
        if issue.severity == severity
    )


def _update_status_filter_counts(
    items: list[MockItem],
    unsaved_filter: StatusFilterButton,
    warning_filter: StatusFilterButton,
    error_filter: StatusFilterButton,
) -> None:
    unsaved_filter.set_count(sum(1 for item in items if _item_has_changes(item)))
    warning_filter.set_count(_issue_count_for_items(items, IssueSeverity.WARNING))
    error_filter.set_count(_issue_count_for_items(items, IssueSeverity.ERROR))


def _kicad_metadata_changes_for_items(items: list[MockItem]) -> list[KiCadMetadataChange]:
    changes: list[KiCadMetadataChange] = []
    for item in items:
        item_type = _kicad_item_type(item)
        if item_type is None or item.source_path is None:
            continue
        for field_name, cell in item.cells.items():
            if cell.is_changed and cell.included_in_save:
                changes.append(
                    KiCadMetadataChange(
                        item_type=item_type,
                        source_path=item.source_path,
                        item_name=item.name,
                        field_name=field_name,
                        value=cell.working_value,
                    )
                )
    return changes


def _mark_saved_metadata_changes(items: list[MockItem]) -> None:
    for item in items:
        if item.source_path is None:
            continue
        for field_name, cell in item.cells.items():
            if not cell.is_changed or not cell.included_in_save:
                continue
            cell.original_value = cell.working_value
            cell.change_source = None
            cell.change_kind = None
            cell.included_in_save = True
            item.metadata_fields[field_name] = cell.working_value


def _revert_metadata_changes(items: list[MockItem], *, included_only: bool = False) -> int:
    reverted_count = 0
    for item in items:
        for field_name, cell in item.cells.items():
            if not cell.is_changed:
                continue
            if included_only and not cell.included_in_save:
                continue
            cell.working_value = cell.original_value
            cell.change_source = None
            cell.change_kind = None
            cell.included_in_save = True
            item.metadata_fields[field_name] = cell.original_value
            reverted_count += 1
    return reverted_count


def _pending_metadata_changes(scope: str, items: list[MockItem]) -> list[PendingChange]:
    changes: list[PendingChange] = []
    for item in items:
        for field_name, cell in item.cells.items():
            if not cell.is_changed:
                continue
            source_parts = []
            if cell.change_source is not None:
                source_parts.append(cell.change_source.value)
            if cell.change_kind is not None:
                source_parts.append(cell.change_kind.value)
            changes.append(
                PendingChange(
                    scope=scope,
                    library=item.display_library,
                    item=item.name,
                    field=field_name,
                    original=cell.original_value,
                    current=cell.working_value,
                    included=cell.included_in_save,
                    source=", ".join(source_parts),
                    detail=f"Full source library: {item.library}",
                    source_path=item.source_path,
                    item_ref=item,
                )
            )
    return changes


def _history_events_for_metadata_save(items: list[MockItem]) -> list[HistoryEvent]:
    events: list[HistoryEvent] = []
    for item in items:
        item_type = _kicad_item_type(item)
        if item_type is None or item.source_path is None:
            continue
        for field_name, cell in item.cells.items():
            if not cell.is_changed or not cell.included_in_save:
                continue
            events.append(
                HistoryEvent.create(
                    action="metadata_saved",
                    scope=item_type,
                    library=item.display_library,
                    item=item.name,
                    field=field_name,
                    original=cell.original_value,
                    current=cell.working_value,
                    source_path=item.source_path,
                    detail=f"Full source library: {item.library}",
                    metadata={
                        "change_source": cell.change_source.value if cell.change_source else "",
                        "change_kind": cell.change_kind.value if cell.change_kind else "",
                    },
                )
            )
    return events


def _history_events_for_policy_save(
    profile: PolicyProfile,
    settings: AuditPolicySettings,
    saved_profile: PolicyProfile | None,
    saved_settings: dict[str, object],
    policy_path: Path,
) -> list[HistoryEvent]:
    return [
        HistoryEvent.create(
            action="policy_saved",
            scope="policy",
            library=profile.name,
            item=profile.profile_id,
            field="Policy settings and rules",
            original=_policy_history_state(saved_profile, saved_settings),
            current=_policy_history_state(profile, _audit_policy_settings_to_dict(settings)),
            source_path=policy_path,
            detail="Saved audit policy override.",
        )
    ]


def _policy_history_state(
    profile: PolicyProfile | None,
    settings: dict[str, object],
) -> dict[str, object]:
    return {
        "profile": profile.to_dict() if profile is not None else {},
        "settings": dict(settings),
    }


def _read_only_table_item(value: str) -> QTableWidgetItem:
    item = QTableWidgetItem(value)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item


def _table_value(value: object) -> str:
    text = _history_value_text(value).replace("\r", " ").replace("\n", " ")
    return text if len(text) <= 160 else text[:157] + "..."


def _history_value_text(value: object) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, indent=2, sort_keys=True)


def _kicad_item_type(item: MockItem) -> str | None:
    if item.source_path is None:
        return None
    if item.source_path.suffix == ".kicad_sym":
        return "symbol"
    if item.source_path.suffix == ".kicad_mod":
        return "footprint"
    return None


def _radio_row(buttons: list[QRadioButton]) -> QHBoxLayout:
    layout = QHBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    for button in buttons:
        layout.addWidget(button)
    layout.addStretch()
    return layout


def _labeled_radio_row(label: str, buttons: list[QRadioButton]) -> QHBoxLayout:
    layout = QHBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(QLabel(f"{label}:"))
    for button in buttons:
        layout.addWidget(button)
    layout.addStretch()
    return layout


def _audit_library_violation_text(
    library: str,
    settings: AuditPolicySettings,
    findings: list[PolicyFinding],
) -> str:
    if not settings.enabled or settings.severity == "ignore" or library not in settings.enabled_libraries:
        return "-"
    count = sum(
        1
        for finding in findings
        if finding.policy_id == settings.profile.profile_id and finding.library == library
    )
    return str(count)


def _audit_library_kind(
    library: str,
    symbol_items: list[MockItem],
    footprint_items: list[MockItem],
) -> str:
    if any(item.library == library for item in symbol_items):
        return "symbol"
    if any(item.library == library for item in footprint_items):
        return "footprint"
    return "library"


def _discovered_field_names(symbol_items: list[MockItem], footprint_items: list[MockItem]) -> list[str]:
    fields = set(ComponentTableModel.columns[3:])
    for item in [*symbol_items, *footprint_items]:
        fields.update(item.cells)
        fields.update(item.metadata_fields)
    fields.discard("Apply")
    fields.discard("Library")
    fields.discard("Name")
    return sorted(fields, key=str.casefold)


def _unique_rule_id(name: str, existing_rule_ids: list[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-") or "rule"
    existing = set(existing_rule_ids)
    if base not in existing:
        return base
    index = 2
    while f"{base}-{index}" in existing:
        index += 1
    return f"{base}-{index}"


def _ui_icon(kind: str) -> QIcon:
    icon = _bundled_ui_icon(kind)
    if not icon.isNull():
        return icon

    pixmap = QPixmap(16, 16)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor("#1f5f8b"), 1)
    painter.setPen(pen)

    if kind == "footprint":
        painter.setBrush(QColor("#8ecae6"))
        painter.drawRect(4, 3, 8, 10)
        painter.setPen(QPen(QColor("#1f5f8b"), 1))
        for x, inner_x in [(2, 4), (14, 12)]:
            for y in [4, 7, 10, 13]:
                painter.drawLine(x, y, inner_x, y)
        painter.drawLine(6, 5, 10, 5)
        painter.drawLine(6, 8, 10, 8)
        painter.drawLine(6, 11, 10, 11)
    elif kind == "audit":
        painter.setBrush(QColor("#f7f7f7"))
        painter.drawRect(3, 2, 9, 12)
        painter.drawLine(5, 5, 10, 5)
        painter.drawLine(5, 8, 10, 8)
        painter.drawLine(5, 11, 8, 11)
        painter.setPen(QPen(QColor("#146c2e"), 2))
        painter.drawLine(9, 12, 11, 14)
        painter.drawLine(11, 14, 15, 8)
    elif kind == "changes":
        painter.setBrush(QColor("#d8ecff"))
        painter.drawRect(4, 2, 8, 12)
        painter.drawLine(6, 6, 10, 6)
        painter.drawLine(6, 9, 10, 9)
        painter.setPen(QPen(QColor("#1f5f8b"), 2))
        painter.drawLine(2, 4, 5, 4)
        painter.drawLine(2, 12, 5, 12)
    elif kind == "history":
        painter.setPen(QPen(QColor("#111111"), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(4, 4, 9, 9)
        painter.drawLine(8, 6, 8, 9)
        painter.drawLine(8, 9, 10, 10)
        painter.setPen(QPen(QColor("#111111"), 2))
        painter.drawArc(2, 2, 12, 12, 130 * 16, 210 * 16)
        painter.drawLine(2, 5, 2, 2)
        painter.drawLine(2, 5, 5, 5)
    else:
        painter.setBrush(QColor("#e6f2ff"))
        painter.drawPolygon([QPoint(3, 3), QPoint(13, 8), QPoint(3, 13)])
        painter.drawLine(1, 8, 3, 8)
        painter.drawLine(13, 8, 15, 8)
        painter.drawLine(5, 6, 7, 6)
        painter.drawLine(5, 10, 7, 10)

    painter.end()
    return QIcon(pixmap)


def _bundled_ui_icon(kind: str) -> QIcon:
    if kind not in {"symbol", "footprint", "history"}:
        return QIcon()

    icon_path = resources.files("kmfdm").joinpath("resources", "ui-icons", f"{kind}.svg")
    return QIcon(str(icon_path))


def _available_libraries(items: list[MockItem]) -> list[str]:
    return sorted({item.display_library for item in items})


def configured_table_items_from_workspace(
    config: WorkspaceConfig,
    progress_callback: ScanProgressCallback | None = None,
) -> tuple[list[MockItem], list[MockItem]]:
    symbol_items, footprint_items = scan_workspace_libraries(
        config,
        progress_callback=progress_callback,
    )
    table_symbol_items = _scanned_or_placeholder_symbol_items(symbol_items, config.symbol_libraries)
    table_footprint_items = _scanned_or_placeholder_footprint_items(
        footprint_items,
        config.footprint_libraries,
    )
    _apply_library_aliases(table_symbol_items)
    _apply_library_aliases(table_footprint_items)
    return table_symbol_items, table_footprint_items


def _workspace_has_enabled_libraries(config: WorkspaceConfig) -> bool:
    return any(selection.enabled for selection in [*config.symbol_libraries, *config.footprint_libraries])


def _progress_percentage(completed_steps: int, total_steps: int) -> int:
    if total_steps <= 0:
        return 100
    bounded_completed = max(0, min(completed_steps, total_steps))
    return int(bounded_completed * 100 / total_steps)


def configured_symbol_items(selections: list[LibrarySelection]) -> list[MockItem]:
    return [
        _configured_library_placeholder(selection.path, "Configured symbol library")
        for selection in selections
        if selection.enabled
    ]


def configured_footprint_items(selections: list[LibrarySelection]) -> list[MockItem]:
    return [
        _configured_library_placeholder(selection.path, "Configured footprint library")
        for selection in selections
        if selection.enabled
    ]


def _scanned_or_placeholder_symbol_items(
    scanned_items: list[KiCadLibraryItem],
    selections: list[LibrarySelection],
) -> list[MockItem]:
    if scanned_items:
        return [_mock_item_from_kicad_item(item) for item in scanned_items]
    return configured_symbol_items(selections)


def _scanned_or_placeholder_footprint_items(
    scanned_items: list[KiCadLibraryItem],
    selections: list[LibrarySelection],
) -> list[MockItem]:
    if scanned_items:
        return [_mock_item_from_kicad_item(item) for item in scanned_items]
    return configured_footprint_items(selections)


def _mock_item_from_kicad_item(item: KiCadLibraryItem) -> MockItem:
    return MockItem(
        library=item.library,
        name=item.name,
        metadata_fields=dict(item.fields),
        source_path=item.source_path,
        cells={
            "Value": _cell_from_fields(item.fields, ["Value"]),
            "Manufacturer": _cell_from_fields(
                item.fields,
                ["Manufacturer", "MANUFACTURER", "MFR", "MFG"],
            ),
            "MPN": _cell_from_fields(
                item.fields,
                [
                    "MPN",
                    "Manufacturer Part Number",
                    "Manufacturer_Part_Number",
                    "MANUFACTURER_PART_NUMBER",
                    "PARTNUMBER",
                    "PART_NUMBER",
                ],
            ),
            "Datasheet": _cell_from_fields(
                item.fields,
                ["Datasheet", "DATASHEET", "Data Sheet", "DATA_SHEET"],
            ),
        },
    )


def _cell_from_fields(fields: dict[str, str], names: list[str]) -> CellState:
    value = _field_value(fields, names)
    return CellState(value, value)


def _field_value(fields: dict[str, str], names: list[str]) -> str:
    normalized_fields = {key.casefold(): value for key, value in fields.items()}
    for name in names:
        value = normalized_fields.get(name.casefold())
        if value is not None:
            return value
    return ""


def _configured_library_placeholder(path_text: str, item_name: str) -> MockItem:
    return MockItem(
        library=_source_library_label(path_text),
        name=item_name,
        cells=_empty_metadata_cells(),
        auditable=False,
    )


def _source_library_label(path_text: str) -> str:
    path = Path(path_text)
    if path.name:
        if path.parent.suffix == ".pretty":
            return f"{path.parent.name}/{path.name}"
        return path.name
    return path_text


def _apply_library_aliases(items: list[MockItem]) -> None:
    aliases_by_library = _library_aliases([item.library for item in items])
    for item in items:
        item.library_alias = aliases_by_library[item.library]


def _library_aliases(libraries: list[str]) -> dict[str, str]:
    unique_libraries = sorted(set(libraries))
    base_aliases = {library: _base_library_alias(library) for library in unique_libraries}
    alias_counts: dict[str, int] = {}
    for alias in base_aliases.values():
        alias_counts[alias] = alias_counts.get(alias, 0) + 1

    duplicate_indexes: dict[str, int] = {}
    aliases: dict[str, str] = {}
    for library in unique_libraries:
        base_alias = base_aliases[library]
        if alias_counts[base_alias] == 1:
            aliases[library] = base_alias
            continue

        duplicate_indexes[base_alias] = duplicate_indexes.get(base_alias, 0) + 1
        aliases[library] = f"{base_alias} ({duplicate_indexes[base_alias]})"

    return aliases


def _base_library_alias(library: str) -> str:
    path = Path(library)
    if path.parent.suffix == ".pretty":
        return path.parent.stem
    if path.suffix in {".pretty", ".kicad_sym"}:
        return path.stem
    return path.name or library


def _empty_metadata_cells() -> dict[str, CellState]:
    return {
        "Value": CellState(editable=False),
        "Manufacturer": CellState(editable=False),
        "MPN": CellState(editable=False),
        "Datasheet": CellState(editable=False),
    }


def mock_symbol_items() -> list[MockItem]:
    return [
        MockItem(
            "Analog",
            "TPS54560",
            {
                "Value": CellState("TPS54560BDDAR_SWITCHING_REGULATOR", "TPS54560", ChangeSource.MANUAL, ChangeKind.VALUE_CHANGED),
                "Manufacturer": CellState("Texas instruments", "Texas Instruments", ChangeSource.RULE_GENERATED, ChangeKind.AUTOMATIC_NORMALIZATION),
                "MPN": CellState("TPS54560BDDAR", "TPS54560BDDAR"),
                "Datasheet": CellState("http://example.com/tps54560.pdf", "http://example.com/tps54560.pdf"),
            },
        ),
        MockItem(
            "Connectors",
            "USB_C_Receptacle",
            {
                "Value": CellState("USB-C-16P", "USB-C-16P"),
                "Manufacturer": CellState("Amphenol", "Amphenol"),
                "MPN": CellState("12401610E4#2A", "12401610E4#2A"),
                "Datasheet": CellState(
                    "",
                    "",
                    issues=[Issue(IssueSeverity.WARNING, "Missing datasheet", "Datasheet field is empty.")],
                ),
            },
        ),
    ]


def mock_footprint_items() -> list[MockItem]:
    return [
        MockItem(
            "Connectors.pretty",
            "USB_C_Receptacle_SMD",
            {
                "Value": CellState("USB_C_Receptacle_SMD_16P_MidMount_LongName", "USB-C-16P", ChangeSource.MANUAL, ChangeKind.VALUE_CHANGED),
                "Manufacturer": CellState("", ""),
                "MPN": CellState("", ""),
                "Datasheet": CellState("", ""),
            },
        ),
        MockItem(
            "Mechanical.pretty",
            "MountingHole_3.2mm",
            {
                "Value": CellState("MountingHole_3.2mm", "MountingHole_3.2mm"),
                "Manufacturer": CellState("Example Supplier", "Example Supplier", ChangeSource.MANUAL, ChangeKind.FIELD_DELETED),
                "MPN": CellState("", ""),
                "Datasheet": CellState("", ""),
            },
        ),
    ]


def mock_audit_items(
    symbol_items: list[MockItem] | None = None,
    footprint_items: list[MockItem] | None = None,
) -> list[AuditItem]:
    symbol_items = symbol_items if symbol_items is not None else mock_symbol_items()
    footprint_items = footprint_items if footprint_items is not None else mock_footprint_items()
    return [
        *_mock_items_to_audit_items("symbol", symbol_items),
        *_mock_items_to_audit_items("footprint", footprint_items),
    ]


def _mock_items_to_audit_items(item_type: str, items: list[MockItem]) -> list[AuditItem]:
    return [
        AuditItem(
            item_type=item_type,
            library=item.library,
            name=item.name,
            fields=_audit_fields_for_mock_item(item),
        )
        for item in items
        if item.auditable
    ]


def _audit_fields_for_mock_item(item: MockItem) -> dict[str, str]:
    fields = dict(item.metadata_fields)
    for field_name, cell in item.cells.items():
        fields[field_name] = cell.working_value
    return fields


def attach_policy_findings_to_mock_items(
    symbol_items: list[MockItem],
    footprint_items: list[MockItem],
    findings: list[PolicyFinding],
) -> None:
    items_by_key = {
        **_mock_item_index("symbol", symbol_items),
        **_mock_item_index("footprint", footprint_items),
    }
    for finding in findings:
        item = items_by_key.get((finding.item_type, finding.library, finding.item_name))
        if item is None:
            continue

        cell = _issue_cell_for_finding(item, finding.field)
        if cell is None:
            continue

        issue = Issue(
            severity=IssueSeverity(finding.severity),
            title=finding.message,
            detail="",
            rule_name=finding.rule_name,
            policy_name=finding.policy_name,
        )
        if issue not in cell.issues:
            cell.issues.append(issue)


def _mock_item_index(item_type: str, items: list[MockItem]) -> dict[tuple[str, str, str], MockItem]:
    return {
        (item_type, item.library, item.name): item
        for item in items
    }


def _issue_cell_for_finding(item: MockItem, field: str) -> CellState | None:
    if field in item.cells:
        return item.cells[field]
    if "Value" in item.cells:
        return item.cells["Value"]
    return next(iter(item.cells.values()), None)


def run() -> int:
    configure_windows_app_id()
    app = QApplication(sys.argv)
    app.setWindowIcon(kmfdm_icon())
    window = MainWindow()
    window.show()
    return app.exec()


def kmfdm_icon() -> QIcon:
    icon_path = resources.files("kmfdm").joinpath("resources", "kmfdm.ico")
    return QIcon(str(icon_path))


def configure_windows_app_id() -> None:
    if os.name != "nt":
        return

    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(WINDOWS_APP_ID)
    except Exception:
        pass

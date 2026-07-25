from __future__ import annotations

import ctypes
import json
import os
import sys
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QRect, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
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
    QMessageBox,
    QPushButton,
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
    WorkspaceConfig,
    load_bundled_layout_profiles,
    load_workspace_config,
    matching_symbol_library_for_footprint,
    save_workspace_config,
    workspace_setup_issue,
)
from kmfdm.models import CellState, ChangeKind, ChangeSource, Issue, IssueSeverity


WINDOWS_APP_ID = "Phoenixjack.KMFDM"


@dataclass
class MockItem:
    library: str
    name: str
    cells: dict[str, CellState]


class ComponentTableModel(QAbstractTableModel):
    columns = ["Apply", "Library", "Name", "Value", "Manufacturer", "MPN", "Datasheet"]

    def __init__(self, items: list[MockItem]) -> None:
        super().__init__()
        self.items = items

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
            return item.library if role in (Qt.DisplayRole, Qt.EditRole) else None

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


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("KMFDM")
        self.setWindowIcon(kmfdm_icon())
        self.resize(1200, 760)
        self.workspace_config_path = Path.cwd() / DEFAULT_CONFIG_FILENAME
        self.workspace_config = WorkspaceConfig()
        self.workspace_setup_message = ""
        self._load_workspace_config_for_launch()

        tabs = QTabWidget()
        tabs.addTab(self._library_tab(mock_symbol_items()), "Symbols")
        tabs.addTab(self._library_tab(mock_footprint_items()), "Footprints")
        tabs.addTab(QLabel("Audit and Rules prototype placeholder"), "Audit and Rules")
        tabs.addTab(QLabel("Changes prototype placeholder"), "Changes")
        tabs.addTab(QLabel("History prototype placeholder"), "History")

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
        QTimer.singleShot(0, self._show_required_configuration_if_needed)

    def _load_workspace_config_for_launch(self) -> None:
        config_exists = self.workspace_config_path.exists()
        try:
            self.workspace_config = load_workspace_config(self.workspace_config_path)
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

    def _show_required_configuration_if_needed(self) -> None:
        if not self.workspace_setup_message:
            return

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

    def _action_bar(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.addStretch()

        revert_selected_button = QPushButton("Revert Selected")
        revert_selected_button.clicked.connect(lambda: self._show_mock_action("Revert Selected"))
        layout.addWidget(revert_selected_button)

        revert_all_button = QPushButton("Revert All")
        revert_all_button.clicked.connect(lambda: self._show_mock_action("Revert All"))
        layout.addWidget(revert_all_button)

        save_button = QPushButton("Save Selected")
        save_button.clicked.connect(lambda: self._show_mock_action("Save Selected"))
        layout.addWidget(save_button)

        exit_button = QPushButton("Exit")
        exit_button.clicked.connect(self.close)
        layout.addWidget(exit_button)

        return layout

    def _library_tab(self, items: list[MockItem]) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)

        table = QTableView()
        model = ComponentTableModel(items)
        table.setModel(model)
        table.setItemDelegateForColumn(0, CenteredCheckBoxDelegate(table))
        table.resizeColumnsToContents()
        table.setColumnWidth(0, 72)
        inspector = ReadOnlyInfoPanel("Select a cell to inspect it.")
        inspector.setMinimumWidth(320)

        table.selectionModel().currentChanged.connect(lambda index: self._show_cell(index, model, inspector))

        layout.addWidget(table, 4)
        layout.addWidget(inspector, 1)
        return widget

    def _show_cell(self, index: QModelIndex, model: ComponentTableModel, inspector: ReadOnlyInfoPanel) -> None:
        if not index.isValid():
            return

        item = model.items[index.row()]
        column_name = model.columns[index.column()]
        cell = model._cell_for(index)

        lines = [
            f"Item: {item.name}",
            f"Library: {item.library}",
            f"Field: {column_name}",
            "",
        ]

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
                lines.extend(f"{issue.severity.value.upper()}: {issue.title}" for issue in cell.issues)
        else:
            lines.append("Fixed item metadata column.")

        inspector.setPlainText("\n".join(lines))

    def _show_configuration_dialog(self, require_layout_profile: bool = False) -> bool:
        dialog = ConfigurationDialog(self.workspace_config, self, require_layout_profile=require_layout_profile)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.workspace_config = dialog.to_config()
            save_workspace_config(self.workspace_config)
            self.workspace_setup_message = ""
            QMessageBox.information(self, "Configuration", "Workspace configuration saved.")
            return True
        return False

    def _show_preferences_dialog(self) -> None:
        QMessageBox.information(
            self,
            "Preferences",
            "Preferences will be added as application-wide options emerge.",
        )

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
                    "Policy guidance will be added as the policy system is implemented.",
                    "",
                    "Starter examples live in examples/policies:",
                    "minimal-library-policy.json",
                    "procurement-fields-policy.json",
                    "fab-readability-policy.json",
                    "datasheet-link-policy.json",
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
        symbol_library = matching_symbol_library_for_footprint(footprint_library)
        if symbol_library is not None:
            self._add_checked_item(self.symbol_libraries, str(symbol_library))

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

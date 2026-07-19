from __future__ import annotations

import sys
from dataclasses import dataclass

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QTabWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from kmfdm.models import CellState, ChangeKind, ChangeSource, Issue, IssueSeverity


@dataclass
class MockItem:
    library: str
    name: str
    cells: dict[str, CellState]


class ComponentTableModel(QAbstractTableModel):
    columns = ["Save", "Library", "Name", "Value", "Manufacturer", "MPN", "Datasheet"]

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

        if column_name == "Save":
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

        if column_name == "Save":
            if role == Qt.CheckStateRole:
                return Qt.Checked if self._row_included(item) else Qt.Unchecked
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

        if column_name == "Save" and role == Qt.CheckStateRole:
            included = value == Qt.Checked
            for cell in item.cells.values():
                if cell.is_changed:
                    cell.included_in_save = included
            self.dataChanged.emit(index, index, [Qt.CheckStateRole])
            return True

        cell = self._cell_for(index)
        if cell is None or role != Qt.EditRole:
            return False

        cell.working_value = str(value)
        cell.change_source = ChangeSource.MANUAL
        cell.change_kind = ChangeKind.VALUE_CHANGED
        self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.BackgroundRole, Qt.FontRole, Qt.ToolTipRole])
        return True

    def _cell_for(self, index: QModelIndex) -> CellState | None:
        column_name = self.columns[index.column()]
        return self.items[index.row()].cells.get(column_name)

    def _row_included(self, item: MockItem) -> bool:
        changed_cells = [cell for cell in item.cells.values() if cell.is_changed]
        return bool(changed_cells) and all(cell.included_in_save for cell in changed_cells)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("KMFDM")
        self.resize(1200, 760)

        tabs = QTabWidget()
        tabs.addTab(self._library_tab(mock_symbol_items()), "Symbols")
        tabs.addTab(self._library_tab(mock_footprint_items()), "Footprints")
        tabs.addTab(QLabel("Audit and Rules prototype placeholder"), "Audit and Rules")
        tabs.addTab(QLabel("Changes prototype placeholder"), "Changes")
        tabs.addTab(QLabel("History prototype placeholder"), "History")

        self.setCentralWidget(tabs)

    def _library_tab(self, items: list[MockItem]) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)

        table = QTableView()
        model = ComponentTableModel(items)
        table.setModel(model)
        table.resizeColumnsToContents()
        inspector = QPlainTextEdit()
        inspector.setReadOnly(True)
        inspector.setMinimumWidth(320)
        inspector.setPlainText("Select a cell to inspect it.")

        table.selectionModel().currentChanged.connect(lambda index: self._show_cell(index, model, inspector))

        layout.addWidget(table, 4)
        layout.addWidget(inspector, 1)
        return widget

    def _show_cell(self, index: QModelIndex, model: ComponentTableModel, inspector: QPlainTextEdit) -> None:
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
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()

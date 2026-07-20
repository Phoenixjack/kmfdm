from PySide6.QtCore import Qt

from kmfdm.gui.main_window import ComponentTableModel, mock_symbol_items


def test_no_op_edit_does_not_mark_cell_changed() -> None:
    model = ComponentTableModel(mock_symbol_items())
    value_index = model.index(1, model.columns.index("Value"))
    cell = model.items[1].cells["Value"]

    assert not cell.is_changed

    assert model.setData(value_index, "USB-C-16P", Qt.EditRole)

    assert not cell.is_changed


def test_apply_checkbox_can_be_unchecked_and_checked_again() -> None:
    model = ComponentTableModel(mock_symbol_items())
    apply_index = model.index(0, model.columns.index("Apply"))

    assert model.data(apply_index, Qt.CheckStateRole) == Qt.CheckState.Checked

    assert model.setData(apply_index, Qt.CheckState.Unchecked, Qt.CheckStateRole)
    assert model.data(apply_index, Qt.CheckStateRole) == Qt.CheckState.Unchecked

    assert model.setData(apply_index, Qt.CheckState.Checked, Qt.CheckStateRole)
    assert model.data(apply_index, Qt.CheckStateRole) == Qt.CheckState.Checked

from PySide6.QtCore import Qt

from kmfdm.config import load_bundled_policy_profiles
from kmfdm.gui.main_window import (
    ComponentTableModel,
    attach_policy_findings_to_mock_items,
    mock_audit_items,
    mock_footprint_items,
    mock_symbol_items,
)
from kmfdm.services.policy_audit import audit_items_against_policies


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


def test_policy_finding_attaches_to_matching_mock_cell() -> None:
    symbol_items = mock_symbol_items()
    footprint_items = mock_footprint_items()
    findings = audit_items_against_policies(
        mock_audit_items(symbol_items, footprint_items),
        load_bundled_policy_profiles(),
    )

    attach_policy_findings_to_mock_items(symbol_items, footprint_items, findings)

    tps_mpn = symbol_items[0].cells["MPN"]
    assert any(issue.rule_name == "Manufacturer part-number aliases" for issue in tps_mpn.issues)
    assert any(issue.policy_name == "Manufacturer Part Policy" for issue in tps_mpn.issues)
    assert "Manufacturer part-number aliases" in tps_mpn.tooltip_text()
    assert "Policy: Manufacturer Part Policy" in tps_mpn.tooltip_text()


def test_missing_field_policy_finding_does_not_create_mock_cell() -> None:
    symbol_items = mock_symbol_items()
    footprint_items = mock_footprint_items()
    findings = audit_items_against_policies(
        mock_audit_items(symbol_items, footprint_items),
        load_bundled_policy_profiles(),
    )

    attach_policy_findings_to_mock_items(symbol_items, footprint_items, findings)

    assert "Supplier" not in symbol_items[0].cells

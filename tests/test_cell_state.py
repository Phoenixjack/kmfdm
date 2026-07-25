from kmfdm.models import CellState, ChangeKind, ChangeSource, Issue, IssueSeverity


def test_cell_state_reports_changed_value() -> None:
    cell = CellState(
        original_value="Texas instruments",
        working_value="Texas Instruments",
        change_source=ChangeSource.MANUAL,
        change_kind=ChangeKind.VALUE_CHANGED,
    )

    assert cell.is_changed
    assert "Original: Texas instruments" in cell.tooltip_text()


def test_cell_state_reports_issue_tooltip() -> None:
    cell = CellState(
        original_value="",
        working_value="",
        issues=[Issue(IssueSeverity.WARNING, "Missing datasheet", "Datasheet field is empty.")],
    )

    assert not cell.is_changed
    assert "WARNING: Missing datasheet" in cell.tooltip_text()
    assert "Datasheet field is empty." in cell.tooltip_text()

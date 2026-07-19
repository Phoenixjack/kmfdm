# Architecture

## High-Level Shape

KMFDM should separate domain logic from GUI code.

Recommended package layout:

```text
src/kmfdm/
    app.py
    models/
    parsers/
    services/
    rules/
    history/
    gui/
```

The GUI may depend on services and models. Core parsing, audit, change management, validation, writing, and history code must not depend on PySide6 widgets.

## GUI

Use PySide6 with Qt model/view architecture.

Primary widgets:

- `QMainWindow` for the application shell.
- `QTabWidget` for Symbols, Footprints, Audit and Rules, Changes, and History.
- `QTableView` for library item grids.
- Custom `QAbstractTableModel` classes for cell state and table behavior.
- Inspector panels for selected cell details.

Each table cell should be modeled as application state, not as widget-local state.

Conceptual cell state:

```python
class CellState:
    original_value: str
    working_value: str
    change_source: ChangeSource | None
    change_kind: ChangeKind | None
    included_in_save: bool
    editable: bool
    inherited: bool
    issues: list[Issue]
    change_group_id: str | None
```

The table model should expose display text, edit values, backgrounds, fonts, tooltips, icons, checkboxes, and editability through Qt roles.

## Change Model

Do not write files directly from table edits.

All edits become pending changes in an in-memory change set. Compound operations are represented as atomic change groups.

Examples:

- Field value changed.
- Field added.
- Field deleted.
- Field renamed.
- Value moved.
- Value copied.
- Automatic normalization.

The save preview should show only affected fields and operation labels such as `VALUE CHANGED`, `FIELD DELETED`, and `VALUE MOVED`.

## Partial Saves

KMFDM supports row-level and per-change inclusion controls.

After a partial save:

- Saved changes become the new baseline.
- Unsaved changes remain pending.
- Revert applies only to still-pending changes.
- Full restoration before the partial save requires using the backup.

## KiCad Parsing and Writing

Use a proper S-expression parser with typed adapters for known KiCad constructs.

Do not use regex against raw KiCad library files for parsing or writing. Regex is appropriate only after values have been parsed into fields.

Writer goals:

- Preserve unknown nodes.
- Preserve ordering where practical.
- Avoid touching files without actual changes.
- Avoid changing unrelated formatting.
- Validate generated output by parsing it again before replacing originals.
- Use a KMFDM generator identifier when generating full KiCad files.

## Safe Save

Recommended save procedure:

1. Check whether source files changed externally.
2. Generate proposed outputs into temporary files.
3. Parse generated outputs again.
4. Confirm expected item and field counts.
5. Create backups.
6. Replace original files.
7. Roll back already-replaced files if replacement fails partway through.
8. Reload and verify saved results.
9. Append a `.kmfdm-history.jsonl` event.

## History

Use one append-only JSON Lines file per KMFDM workspace:

```text
.kmfdm-history.jsonl
```

Each event is one JSON object per line.

KMFDM history records only changes performed by KMFDM. If current file hashes no longer match the latest recorded `after_sha256`, record an external modification boundary and treat current files as the new baseline after user acknowledgement.

## Link Validation

Link validation is deferred. When implemented, results should be graded rather than binary:

- Valid.
- Valid redirected.
- Probably valid.
- Broken.
- Access restricted.
- Temporarily unavailable.
- Indeterminate.
- Not checked.

Avoid claiming that every HTTP 200 response proves a purchase page or datasheet is semantically valid.

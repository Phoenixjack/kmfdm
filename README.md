# KMFDM

KiCad Management of Field-Defined Metadata.

KMFDM is a desktop metadata auditor and bulk editor for native KiCad symbol and footprint libraries.

The project is intentionally separate from the KiCad Import Assistant. The importer gets downloaded assets into controlled libraries; KMFDM helps keep those libraries consistent, readable, and maintainable afterward.

## Status

Early bootstrap. The first development slice is a PySide6 mock-data GUI prototype before real KiCad parsing is attached.

## Icon

The application icon is stored as a multi-size ICO package resource and applied to the PySide6 application and main window. On Windows, KMFDM also sets an application user-model ID so the title bar and taskbar can use the KMFDM icon instead of the Python launcher icon.

## Planned MVP

- Symbols and Footprints data-grid views.
- Cell-level change highlighting, issue markers, tooltips, and inspector details.
- Row-level and per-change save inclusion controls.
- Selective change preview.
- Regex compliance inspection only.
- User-defined metadata policies.
- Fab Value length auditing.
- Safe save with backups and validation.
- Single append-only `.kmfdm-history.jsonl` sidecar history.

## Development

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e .[dev]
.\.venv\Scripts\python -m kmfdm
```

## Project Docs

- `AGENTS.md` contains Codex working instructions.
- `PROJECT_BRIEF.md` captures the project scope and MVP boundary.
- `ARCHITECTURE.md` captures the technical shape.
- `CONFIGURATION.md` starts the policy configuration reference.

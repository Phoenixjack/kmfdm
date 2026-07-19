# KMFDM Project Brief

## Name

KMFDM stands for KiCad Management of Field-Defined Metadata.

The public description is:

> A desktop metadata auditor and bulk editor for native KiCad symbol and footprint libraries.

The private spirit is still, correctly, megalomaniacal.

## Problem

KiCad libraries collect inconsistent metadata over time:

- Missing fields.
- Close-but-unequal field names such as `Cost` and `Price`.
- Long `Value` fields that clutter footprint Fab layers.
- Malformed datasheet or purchase links.
- Inconsistent manufacturer and part-number fields.
- Underused footprint descriptions and keywords.
- 3D model paths or symbol footprint references that may no longer resolve.

KiCad includes useful built-in field editing, but KMFDM is intended to work across multiple libraries, audit metadata consistency, support footprints as well as symbols, preview changes safely, and keep a history of KMFDM-performed edits.

## Scope

KMFDM edits metadata belonging to library definitions, not objects already placed in schematics or boards.

Initial targets:

- Packed `.kicad_sym` symbol libraries.
- `.pretty` footprint libraries containing `.kicad_mod` files.

Later targets may include unpacked symbol libraries, project/global library table discovery, and richer link validation.

## MVP Features

- PySide6 GUI with Symbols, Footprints, Audit and Rules, Changes, and History views.
- Editable spreadsheet-like tables.
- Cell-level change state, issue markers, tooltips, and inspector details.
- Row-level save inclusion checkboxes.
- Per-change checkboxes in the Changes tab.
- Atomic change groups for moves, renames, merges, and deletes.
- Selective preview showing only actual changes.
- Partial save behavior where saved changes become the new baseline.
- Required KiCad structural validation.
- User-defined metadata policies.
- Regex compliance inspection only.
- Required-field, alias, whitespace, case, and length audit rules.
- Fab Value length audit aimed at keeping visible footprint values readable.
- Collision checking for proposed shortened values.
- Footprint description and keyword auditing.
- Backups, validation, safe save, revert, and reload.
- Single append-only `.kmfdm-history.jsonl` sidecar history log per workspace.

## Deferred Features

- Regex replacement.
- Automatic intelligent value shortening.
- Rendered-width calculations for Fab text.
- Repairing already-placed PCB footprint values.
- Distributor or manufacturer API lookups.
- Automatic URL replacement.
- Browser automation for supplier pages.
- Claims that every HTTP 200 link is valid.
- Full embedded edit history in every symbol or footprint.

## Policy Philosophy

KMFDM enforces KiCad file integrity. It does not enforce one universal metadata philosophy.

Built-in enforcement is limited to structural safety:

- Files must parse.
- Protected KiCad fields and structures must remain valid.
- Reserved names must not be misused.
- Unsupported or unknown file versions must not be overwritten blindly.
- Generated output must pass validation before replacing originals.

Everything else is user policy:

- Required custom fields.
- Canonical field names.
- Aliases.
- Regex checks.
- Fab readability limits.
- URL checks.
- Description and keyword expectations.
- Save blocking behavior for policy failures.

Example policies may be shipped as suggestions, but disabled by default.

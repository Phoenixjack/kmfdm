# Roadmap

## Current Slice: Mock GUI Feedback Loop

- Exercise the PySide6 table prototype with fake symbol and footprint data.
- Refine cell editing, tooltips, color states, and save inclusion controls.
- Add a basic color legend so visual states are discoverable.
- Add bottom-window command buttons for save, revert, and exit workflows.
- Add menu-accessible mock Configuration and Preferences dialogs.
- Add placeholder Help menu policy guidance.
- Add starter example policy files.

## Near-Term

- Expand persisted workspace settings beyond the first `.kmfdm-workspace.json` foundation.
- Add library root discovery and include/exclude controls for symbol and footprint libraries.
- Build out the Changes tab with mock change groups and per-change inclusion controls.
- Build the selective preview dialog using mock changes.
- Build a prototype History tab for `.kmfdm-history.jsonl` entries.
- Add status-bar counts for loaded libraries, items, issues, and pending changes.
- Add table filtering for issues, pending changes, and selected libraries.
- Add tests around table-model edit and check-state behavior.
- Mirror relevant KiCad Import Assistant profile concepts in the KMFDM Configuration dialog.

## After the GUI Slice Feels Right

- Add KiCad S-expression parser fixtures and parser tests.
- Implement read-only scanning for `.kicad_sym` and `.pretty` libraries.
- Connect scanned KiCad data to the existing table model.
- Add the first user-defined policy schema.
- Expand Help policy guidance after policy behavior exists.
- Add audit rules for required fields, aliases, regex compliance, and Fab Value length.

## Later

- Add safe-save staging, backups, validation, and rollback.
- Add sidecar history writes.
- Add external modification detection.
- Add richer link validation.

## KIA / KMFDM Shared Configuration Goals

- Detect a nearby KiCad Import Assistant checkout or known config file when possible, without requiring a fixed folder layout.
- Offer to import or copy compatible local settings from KIA into KMFDM after user confirmation.
- Evaluate a shared user-level config layer for common values such as library root, KiCad path variable, configured library structures, and API provider keys.
- Keep app-specific settings separate when the concepts diverge.
- Explore mapping KIA import destinations and schema profiles into KMFDM library configuration and policy defaults.
- Support user-defined library structures rather than assuming one personal folder layout or the KiCad standard libraries.
- Treat KiCad standard libraries as read-only unless a later workflow explicitly supports copying selected items into user libraries.

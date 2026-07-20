# Version History

## v0.0.3 - 2026-07-20

- Added `.kmfdm-workspace.json` as the ignored local workspace configuration file.
- Added a workspace configuration model and JSON load/save helpers.
- Wired the Configuration dialog to persisted library root, path variable, symbol libraries, and footprint libraries.

## v0.0.2 - 2026-07-20

- Fixed no-op table edits being marked as manual changes.
- Made row save-inclusion controls easier to discover in the mock GUI.
- Added a Help menu cell color legend.
- Added bottom-window Save Selected, Revert Selected, Revert All, and Exit buttons.
- Added Edit menu entries for Configuration and Preferences.
- Added a mock Configuration dialog for library root and included-library selection.
- Added a Help menu placeholder for Policy Guidance.
- Added starter policy example files under `examples/policies/`.
- Added `ROADMAP.md` with the Library Configuration dialog as a near-term feature.
- Centered the Apply column checkbox rendering.
- Removed misleading KiCad standard library examples from the mock Configuration dialog.
- Added KIA/KMFDM shared configuration and interop goals to the roadmap.

## v0.0.1 - 2026-07-19

Initial project bootstrap.

- Created the KMFDM project foundation.
- Added Codex working instructions in `AGENTS.md`.
- Added project planning docs: `PROJECT_BRIEF.md`, `ARCHITECTURE.md`, and `CONFIGURATION.md`.
- Expanded the README with project purpose, status, planned MVP, and development commands.
- Added Python packaging with `pyproject.toml`.
- Added a minimal `src/kmfdm` package.
- Added an initial PySide6 mock-data GUI scaffold.
- Added the first cell-state domain model.
- Added initial model tests.
- Added a Python-focused `.gitignore`.

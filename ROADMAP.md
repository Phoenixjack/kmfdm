# Roadmap

## Current Slice: Mock GUI Feedback Loop

- Exercise the PySide6 table prototype with fake symbol and footprint data.
- Refine cell editing, tooltips, color states, and save inclusion controls.
- Add a basic color legend so visual states are discoverable.
- Add bottom-window command buttons for save, revert, and exit workflows.
- Add menu-accessible mock Configuration and Preferences dialogs.
- Add Help menu policy guidance for the starter Audit workflow.
- Add starter example policy files.
- Add table controls for filtering visible mock rows by source library and visible columns.
- Drive the table placeholder rows from saved Configuration libraries instead of hardcoded demo libraries.
- Add read-only KiCad S-expression scanning for configured `.kicad_sym` and `.pretty` libraries.
- Connect scanned KiCad symbol and footprint metadata to the existing table model.

## Near-Term

- Add the KMFDM icon and early application screenshots to `README.md`.
- Expand persisted workspace settings beyond the first `.kmfdm-workspace.json` foundation.
- Connect selected library layout profiles to Configuration dialog workflows.
- Expand first-run and repair guided setup for creating or recreating local workspace configuration.
- Add library root discovery and include/exclude controls for symbol and footprint libraries.
- Build out the Changes tab with mock change groups and per-change inclusion controls.
- Build the selective preview dialog using mock changes.
- Build a prototype History tab for `.kmfdm-history.jsonl` entries.
- Add status-bar counts for loaded libraries, items, issues, and pending changes.
- Add table filtering for issues and pending changes.
- Expand source-library and column filters after real KiCad scans replace mock data.
- Add tests around table-model edit and check-state behavior.
- Add issue-filter controls that use audit-generated table issue states.
- Mirror relevant KiCad Import Assistant profile concepts in the KMFDM Configuration dialog.

## After the GUI Slice Feels Right

- Persist Audit tab policy settings across launches.
- Add policy-file selection for workspace-specific policy profiles.
- Expand Help policy guidance after policy behavior exists.
- Add more user-adjustable audit rules after the starter scanned-data policy flow is validated.
- Connect the Rule Editor dialog to real policy mutation and workspace persistence.
- Add a regex-builder assistant and stronger live rule preview against selected library rows.
- Add wildcard and regex applicability controls for selected fields and libraries.

## Later

- Add an optional lower-right symbol/footprint preview panel using KiCad CLI SVG export when a KiCad CLI path is configured or discoverable.
- Add a read-only layout scanner that can suggest likely layout profiles from a selected library root.
- Add user-customizable layout profile editing after bundled starter profiles are proven useful.
- Add safe-save staging, backups, validation, and rollback.
- Add sidecar history writes.
- Add external modification detection.
- Add richer link validation.

## KIA / KMFDM Shared Configuration Goals

- Detect a nearby KiCad Import Assistant checkout or known config file when possible, without requiring a fixed folder layout.
- Offer to import or copy compatible local settings from KIA into KMFDM after user confirmation.
- Evaluate a shared user-level config layer for common values such as library root, KiCad path variable, configured library structures, and API provider keys.
- Preserve a KMFDM config namespace for KIA compatibility without requiring both apps to use the same on-disk config format.
- Keep app-specific settings separate when the concepts diverge.
- Explore mapping KIA import destinations and schema profiles into KMFDM library configuration and policy defaults.
- Support user-defined library structures rather than assuming one personal folder layout or the KiCad standard libraries.
- Treat KiCad standard libraries as read-only unless a later workflow explicitly supports copying selected items into user libraries.

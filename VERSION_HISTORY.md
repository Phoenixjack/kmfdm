# Version History

## Unreleased

- Added source-library and visible-column filters above the mock Symbols and Footprints tables.
- Added Select All and Select None commands to the mock table filter dropdowns.
- Refresh Symbols and Footprints table filters after saving Configuration changes.
- Replaced hardcoded demo table rows in the main UI with non-audited placeholders from enabled configured libraries.
- Added a small S-expression parser for read-only KiCad library scanning.
- Added read-only scanning for configured `.kicad_sym` symbol libraries and `.pretty/*.kicad_mod` footprint libraries.
- Connected scanned KiCad metadata to the Symbols and Footprints table columns.
- Added Symbols and Footprints filter pills for unsaved rows, warning issues, and error issues with live tab-local counts.
- Allow Save Selected on Symbols and Footprints to write included changed metadata cells back to scanned KiCad symbol and footprint files.
- Allow Revert Selected/Revert All on Symbols and Footprints to discard pending metadata cell edits on the active tab.
- Replaced the Changes placeholder with a live pending-change list for edited symbol and footprint metadata.
- Added an Apply checkbox column, Changes tab pending-count label, and Save Applied/Revert Applied actions for metadata review.
- Replaced the History placeholder with a read-only `.kmfdm-history.jsonl` viewer.
- Append sidecar history events when metadata and audit policy saves succeed.
- Simplified Library column and source-filter display with unique library aliases while keeping full source labels in the inspector.
- Kept full scanned metadata available to audit rules even when fields are not visible table columns.
- Added a starter library validation policy for datasheet, associated footprint, and 3D-model requirements.
- Added an audit rule that checks whether a symbol Footprint field points to an existing footprint.
- Fixed audit field preparation so policies can see canonical table fields even when raw KiCad metadata uses aliases such as `MANUFACTURER`.
- Treat `MPN` as the preferred manufacturer part-number field in starter policies, with longer part-number field names treated as aliases.
- Normalize older workspace Manufacturer Part Policy overrides so `MPN` is no longer flagged as an alias after policy defaults change.
- Added Audit tab controls for policy enablement, apply-to-new-libraries behavior, symbol/footprint target, severity, and explicit per-library applicability.
- Defaulted GRAPHICS libraries out of the starter library validation policy through unchecked library applicability instead of wildcard exemptions.
- Added a Library Validation details note explaining the GRAPHICS default opt-out.
- Added an advisory Related field coverage section when policies check fields that also appear in other policies.
- Persist Audit tab policy settings through workspace configuration and reload them across launches.
- Make Audit tab policy and rule edits pending until Save Selected, with Revert Selected and Revert All restoring the last saved audit state.
- Disable Save Selected and Revert buttons when the current tab has no pending changes, and refresh their state when switching tabs.
- Defer KiCad library scanning until after the main window is built, with a no-button progress dialog and mirrored loading text in the Symbols and Footprints inspectors.
- Replaced the native bottom status bar with an inline status label beside the persistent action buttons.
- Updated the Symbols and Footprints SVG icons with KiCad-like blue coloring and rotated the footprint glyph for closer visual parity.
- Keep apply-to-new-libraries from re-checking installed libraries that the user manually opted out of a policy.
- Replaced the Audit tab findings list with per-library violation counts so Symbols and Footprints remain the primary finding inspection views.
- Reworked the Audit tab into policy, policy-details/rules, and installed-library zones.
- Added bundled SVG tab and library-type icons for Symbols, Footprints, History, and audit library rows.
- Create an empty contained `.kicad_sym` file after confirmation when a newly added footprint library has no symbol library.
- Ask the user to choose the intended symbol library when a newly added footprint library has multiple `.kicad_sym` candidates.
- Added a per-library Violations column that shows `-` for libraries outside the selected policy and counts for applied libraries.
- Connected the Rule Editor dialog to create and edit required-field and regex rules.
- Added rule deletion with confirmation from selected Audit policies.
- Persist edited policies as workspace overrides under `.kmfdm-policies/` and reload them through workspace `policy_files`.
- Added Rule Editor field selection, required/regex controls, regex quick help, and live regex pass/fail preview.
- Added footprint 3D model extraction from KiCad `(model ...)` nodes.
- Made development launcher settings resolve to the project workspace path instead of `.venv/Scripts`, with a legacy read fallback.
- Added future roadmap note for optional KiCad CLI SVG-based symbol and footprint preview.
- Added initial dev-tool configuration for `pytest-qt` and `ruff`.
- Clearly label policy provenance for policy-generated cell issues in tooltips and inspectors.
- Connected mock policy findings to matching Symbols and Footprints table cell issue states.
- Expanded issue tooltips and inspectors with policy detail and rule names.
- Added a read-only policy audit service for mock library rows.
- Added Audit mock policy findings with finding detail display.
- Added tests for required-field, alias, regex, and max-length policy findings.
- Added the first versioned policy schema and JSON loader.
- Converted starter policy examples into disabled-by-default parseable policies.
- Bundled starter policy examples as application resources for packaged runs.
- Added tests for policy example loading, bundled policy loading, schema versions, and regex validation.
- Replaced the Audit placeholder with a read-only starter policy browser.
- Made the Configuration layout placeholder display-only instead of a selectable layout option.
- Replaced editable-looking details/inspector text boxes with framed read-only information panels.
- Shortened layout profile details to the description and core path templates.
- Added a Configuration dialog details panel for selected library layout profiles.
- Added startup setup detection for missing, unreadable, or layout-less workspace configuration.
- Require a library layout selection before accepting setup-required Configuration dialogs.
- Added persisted workspace selection for library layout profiles.
- Added a Configuration dialog layout-profile selector populated from `examples/layouts/`.
- Bundled starter layout profiles as application resources for packaged runs.
- Added library layout profile examples for flat-contained, separated-subfolder, and split-root structures.
- Added a layout profile model and JSON loader for future shared layout configuration.
- Added configuration docs for first-run and repair guided setup.
- Moved layout autodetection to a back-burner roadmap item.
- Added README disclosure that KMFDM is vibe coded with AI assistance.
- Added README reference to the related KiCad Import Assistant project.
- Moved the Megalomaniacal inside joke into project documentation instead of the GitHub short description.
- Added a roadmap item for README icon and screenshot placement.

## v0.0.4 - 2026-07-25

- Added the KMFDM multi-size icon as a package resource.
- Applied the KMFDM icon to the PySide6 application and main window.
- Added a Windows application user-model ID so the taskbar can show the KMFDM icon.
- Fixed footprint-library symbol autodetection for layouts where the matching `.kicad_sym` file lives inside the `.pretty` folder.
- Reserved a `kia_interop` workspace config section for future KIA/KMFDM config mapping.
- Moved the footprint-library section above the symbol-library section in the Configuration dialog.
- Added exact sibling symbol-library detection when adding a footprint library.

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

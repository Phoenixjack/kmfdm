# Configuration

KMFDM should treat metadata quality as user policy. This document will grow into the reference for policy files and workspace configuration.

## Configuration Layers

1. Application defaults.
2. Example policies shipped with the project.
3. Workspace policy selected by the user.
4. Session-only filters and view preferences.

Example policies are suggestions and should be disabled until the user opts in.

## Workspace Configuration

Local workspace settings are stored in `.kmfdm-workspace.json`.

This file is ignored by Git because it may contain machine-specific paths and future local provider settings.

Initial fields:

- `library_root`
- `path_variable`
- `layout_profile_id`
- `symbol_libraries`
- `footprint_libraries`
- `policy_files`
- `kia_interop`

`kia_interop` is reserved for future KiCad Import Assistant compatibility. It should leave room for copying or mapping compatible KIA private-data values such as library root, path variable, import destinations, schema profiles, and API provider settings without forcing KMFDM to share KIA's exact file format.

When a footprint library is added, KMFDM looks for matching symbol libraries in the `.pretty` folder and beside it. For example, `_testCONN.pretty` can auto-add `_testCONN.pretty/_testCONN.kicad_sym` or `_testCONN.kicad_sym`.

If no `.kicad_sym` file exists for the selected footprint library, KMFDM can create an empty contained symbol library named `{library_key}.kicad_sym` after user confirmation. If more than one candidate `.kicad_sym` file exists, KMFDM asks the user to choose the intended symbol library with a file picker.

## Library Layout Profiles

Library layout profiles describe where symbols, footprints, and models live relative to a selected library root.

These profiles should be shared in concept with KiCad Import Assistant so users do not have to describe the same local library structure twice.

Layout profiles answer questions such as:

- Where is a footprint library for a given library key?
- Where is the matching symbol library?
- Where should 3D models be found or written?
- Which symbol-library paths should be checked when a footprint library is selected?

Example layout profiles live in `examples/layouts/`:

- `flat-contained-symbols.json`
- `separated-subfolders.json`
- `split-type-roots.json`

The selected profile is stored in `.kmfdm-workspace.json` as `layout_profile_id`.
The GUI loads the same starter profiles from bundled application resources so the options remain available outside a source checkout.

The initial built-in candidates are:

```text
flat-contained-symbols
  {library_root}/{library_key}.pretty/
    {library_key}.kicad_sym
    *.kicad_mod
    *.step / *.stp

separated-subfolders
  {library_root}/{library_key}/symbols/{library_key}.kicad_sym
  {library_root}/{library_key}/footprints/{library_key}.pretty
  {library_root}/{library_key}/models/

split-type-roots
  {library_root}/Symbols/{library_key}.kicad_sym
  {library_root}/Footprints/{library_key}.pretty
  {library_root}/Models/{library_key}/
```

The Configuration dialog lets users choose one of these shipped example layouts. Later setup work should allow users to customize path templates or start from autodetected suggestions.

The first code foundation for layout profiles is a parser/validator for the example JSON files, persisted GUI selection, and an in-dialog details panel that explains the selected profile. Path-template rendering and filesystem scanning are intentionally separate later steps.

## First-Run and Repair Setup

KMFDM should eventually offer a guided setup when local configuration is missing, invalid, or intentionally recreated.

The first setup behavior is intentionally small: when KMFDM starts without a workspace config, with an unreadable workspace config, or without a selected layout profile, it opens Configuration and requires a layout choice before continuing.

Setup goals:

- Create `.kmfdm-workspace.json` from executable-shipped defaults and user choices.
- Choose or customize a library layout profile.
- Select a custom library root.
- Configure the KiCad path variable.
- Rebuild symbol and footprint library lists from a selected root folder.
- Optionally import compatible KIA settings after user confirmation.

Autodetection is a back-burner feature. When added, it should be advisory: scan a selected root folder, identify likely layout patterns, report confidence, and let the user accept, customize, or ignore the suggestion.

## Policy Concepts

Policy files are versioned JSON documents. The first schema supports enough structure to load, validate, display policy intent, and run read-only checks against scanned KiCad metadata.

Policies may define:

- Required fields.
- Canonical field names.
- Alias mappings.
- Regex compliance checks.
- Maximum length checks.
- Reference-exists checks, such as symbol Footprint fields pointing to known footprints.
- Fab Value readability checks.
- URL syntax checks.
- Footprint description and keyword checks.
- Severity.
- Save behavior.
- Per-policy applicability for Symbols, Footprints, or both.
- Explicit per-library applicability.

## Severity

Recommended values:

```text
info
warning
error
```

## Save Behavior

Recommended values:

```text
advisory
require_acknowledgement
block_save
```

`block_save` must be an explicit user policy choice, not a built-in metadata opinion.

## Initial Example

```json
{
  "policy_schema_version": 1,
  "id": "fab-readability-policy",
  "name": "Fab readability example",
  "description": "Suggested checks for keeping fabrication-layer values readable.",
  "enabled_by_default": false,
  "rules": [
    {
      "id": "footprint-value-length",
      "name": "Footprint Value stays compact",
      "type": "max_length",
      "target": "footprint",
      "field": "Value",
      "max_characters": 18,
      "severity": "warning",
      "save_behavior": "advisory"
    }
  ]
}
```

## Example Policy Files

Starter example policies live in `examples/policies/`.

These files are disabled-by-default examples for likely policy families:

- `minimal-library-policy.json`
- `procurement-fields-policy.json`
- `fab-readability-policy.json`
- `datasheet-link-policy.json`
- `library-validation-policy.json`
- `manufacturer-part-policy.json`

The GUI loads the same starter policies from bundled application resources so the Audit tab can show them outside a source checkout.
The Audit tab lets users adjust each policy's enabled state, apply-to-new-libraries behavior, symbol/footprint target, KiCad-style severity, and installed-library applicability. The installed-library table shows per-library violation counts for the selected policy. Symbols and Footprints remain the primary tabs for inspecting individual findings. Findings are attached to visible table cells, so the cell background, tooltip, and inspector show the same issue context.

The starter library validation policy begins with GRAPHICS libraries unchecked in the Audit tab instead of using wildcard exemptions. Users can still opt those libraries into the policy manually. Wildcard and regex-based applicability controls are deferred until the basic policy workflow is proven.

Supported first-pass rule types:

```text
required_field
alias_field_name
regex_check
max_length
reference_exists
```

## Regex Inspection

Regex rules are inspection-only in the MVP.

Recommended modes:

```text
must_match
must_not_match
contains_match
```

Regex replacement is deferred.

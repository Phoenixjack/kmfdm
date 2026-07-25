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
- `symbol_libraries`
- `footprint_libraries`
- `policy_files`
- `kia_interop`

`kia_interop` is reserved for future KiCad Import Assistant compatibility. It should leave room for copying or mapping compatible KIA private-data values such as library root, path variable, import destinations, schema profiles, and API provider settings without forcing KMFDM to share KIA's exact file format.

When a footprint library is added, KMFDM looks for an exact matching symbol library in the `.pretty` folder first, then beside it. For example, `_testCONN.pretty` can auto-add `_testCONN.pretty/_testCONN.kicad_sym` or `_testCONN.kicad_sym`.

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

The future setup wizard should let users choose one of these layouts, customize path templates, or start from autodetected suggestions.

## First-Run and Repair Setup

KMFDM should eventually offer a guided setup when local configuration is missing, invalid, or intentionally recreated.

Setup goals:

- Create `.kmfdm-workspace.json` from executable-shipped defaults and user choices.
- Choose or customize a library layout profile.
- Select a custom library root.
- Configure the KiCad path variable.
- Rebuild symbol and footprint library lists from a selected root folder.
- Optionally import compatible KIA settings after user confirmation.

Autodetection should be advisory. It should scan a selected root folder, identify likely layout patterns, report confidence, and let the user accept, customize, or ignore the suggestion.

## Policy Concepts

Policies may define:

- Required fields.
- Canonical field names.
- Alias mappings.
- Regex compliance checks.
- Maximum length checks.
- Fab Value readability checks.
- URL syntax checks.
- Footprint description and keyword checks.
- Severity.
- Save behavior.

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
  "name": "Fab readability example",
  "rules": [
    {
      "type": "fab_value_length",
      "target": "symbol.Value",
      "max_characters": 18,
      "collision_scope": "loaded_libraries",
      "severity": "warning",
      "save_behavior": "advisory"
    }
  ]
}
```

## Example Policy Files

Starter example policies live in `examples/policies/`.

These files are placeholders for likely policy families, not enabled defaults:

- `minimal-library-policy.json`
- `procurement-fields-policy.json`
- `fab-readability-policy.json`
- `datasheet-link-policy.json`
- `manufacturer-part-policy.json`

## Regex Inspection

Regex rules are inspection-only in the MVP.

Recommended modes:

```text
must_match
must_not_match
contains_match
```

Regex replacement is deferred.

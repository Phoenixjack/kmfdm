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

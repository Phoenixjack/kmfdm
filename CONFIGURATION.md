# Configuration

KMFDM should treat metadata quality as user policy. This document will grow into the reference for policy files and workspace configuration.

## Configuration Layers

1. Application defaults.
2. Example policies shipped with the project.
3. Workspace policy selected by the user.
4. Session-only filters and view preferences.

Example policies are suggestions and should be disabled until the user opts in.

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

## Regex Inspection

Regex rules are inspection-only in the MVP.

Recommended modes:

```text
must_match
must_not_match
contains_match
```

Regex replacement is deferred.

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any


POLICY_SCHEMA_VERSION = 1
VALID_POLICY_RULE_TYPES = {
    "required_field",
    "alias_field_name",
    "regex_check",
    "max_length",
    "reference_exists",
}
VALID_POLICY_TARGETS = {"symbol", "footprint", "both"}
VALID_POLICY_SEVERITIES = {"info", "warning", "error"}
VALID_SAVE_BEHAVIORS = {"advisory", "require_acknowledgement", "block_save"}
VALID_REGEX_MODES = {"must_match", "must_not_match", "contains_match"}


@dataclass(frozen=True)
class PolicyRule:
    rule_id: str
    name: str
    rule_type: str
    target: str
    severity: str
    save_behavior: str
    parameters: dict[str, Any]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PolicyRule:
        rule_type = _required_string(data, "type")
        if rule_type not in VALID_POLICY_RULE_TYPES:
            raise ValueError(f"Unsupported policy rule type: {rule_type}")

        target = _required_string(data, "target")
        if target not in VALID_POLICY_TARGETS:
            raise ValueError(f"Unsupported policy target: {target}")

        severity = str(data.get("severity", "warning"))
        if severity not in VALID_POLICY_SEVERITIES:
            raise ValueError(f"Unsupported policy severity: {severity}")

        save_behavior = str(data.get("save_behavior", "advisory"))
        if save_behavior not in VALID_SAVE_BEHAVIORS:
            raise ValueError(f"Unsupported policy save behavior: {save_behavior}")

        _validate_rule_payload(rule_type, data)

        base_keys = {"id", "name", "type", "target", "severity", "save_behavior"}
        return cls(
            rule_id=_required_string(data, "id"),
            name=_required_string(data, "name"),
            rule_type=rule_type,
            target=target,
            severity=severity,
            save_behavior=save_behavior,
            parameters={key: value for key, value in data.items() if key not in base_keys},
        )


@dataclass(frozen=True)
class PolicyProfile:
    profile_id: str
    name: str
    description: str
    enabled_by_default: bool
    rules: list[PolicyRule]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PolicyProfile:
        version = data.get("policy_schema_version")
        if version != POLICY_SCHEMA_VERSION:
            raise ValueError(f"Unsupported policy schema version: {version}")

        rules = data.get("rules")
        if not isinstance(rules, list):
            raise ValueError("Policy field must be a list: rules")

        return cls(
            profile_id=_required_string(data, "id"),
            name=_required_string(data, "name"),
            description=str(data.get("description", "")),
            enabled_by_default=bool(data.get("enabled_by_default", False)),
            rules=[PolicyRule.from_dict(rule) for rule in rules],
        )


def load_policy_profile(path: Path) -> PolicyProfile:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    return _policy_from_data(data, path)


def load_policy_profiles(directory: Path) -> list[PolicyProfile]:
    return [load_policy_profile(path) for path in sorted(directory.glob("*.json"))]


def load_bundled_policy_profiles() -> list[PolicyProfile]:
    directory = resources.files("kmfdm").joinpath("resources", "policies")
    profile_files = sorted(
        (item for item in directory.iterdir() if item.name.endswith(".json")),
        key=lambda item: item.name,
    )

    profiles = []
    for profile_file in profile_files:
        with profile_file.open("r", encoding="utf-8") as file:
            profiles.append(_policy_from_data(json.load(file), profile_file))

    return profiles


def _policy_from_data(data: Any, source: object) -> PolicyProfile:
    if not isinstance(data, dict):
        raise ValueError(f"Policy must contain a JSON object: {source}")

    return PolicyProfile.from_dict(data)


def _validate_rule_payload(rule_type: str, data: dict[str, Any]) -> None:
    if rule_type == "required_field":
        _required_string(data, "field")
    elif rule_type == "alias_field_name":
        _required_string(data, "canonical")
        _required_string_list(data, "aliases")
    elif rule_type == "regex_check":
        _required_string(data, "field")
        pattern = _required_string(data, "pattern")
        mode = _required_string(data, "mode")
        if mode not in VALID_REGEX_MODES:
            raise ValueError(f"Unsupported regex mode: {mode}")
        try:
            re.compile(pattern)
        except re.error as error:
            raise ValueError(f"Invalid regex pattern: {error}") from error
    elif rule_type == "max_length":
        _required_string(data, "field")
        max_characters = data.get("max_characters")
        if not isinstance(max_characters, int) or max_characters < 1:
            raise ValueError("Policy max_length rule requires a positive integer: max_characters")
    elif rule_type == "reference_exists":
        _required_string(data, "field")
        referenced_item_type = _required_string(data, "referenced_item_type")
        if referenced_item_type not in {"symbol", "footprint"}:
            raise ValueError(f"Unsupported referenced item type: {referenced_item_type}")


def _required_string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Policy field must be a non-empty string: {key}")
    return value


def _required_string_list(data: dict[str, Any], key: str) -> list[str]:
    value = data.get(key)
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"Policy field must be a non-empty string list: {key}")
    return list(value)

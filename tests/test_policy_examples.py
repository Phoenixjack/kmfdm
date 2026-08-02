import json
from pathlib import Path

from kmfdm.config import (
    POLICY_SCHEMA_VERSION,
    load_bundled_policy_profiles,
    load_policy_profile,
    load_policy_profiles,
)


def test_policy_examples_are_valid_json() -> None:
    policy_dir = Path("examples/policies")
    policy_files = sorted(policy_dir.glob("*.json"))

    assert policy_files

    for policy_file in policy_files:
        data = json.loads(policy_file.read_text(encoding="utf-8"))
        assert data["policy_schema_version"] == POLICY_SCHEMA_VERSION
        assert data["id"]
        assert data["name"]
        assert data["enabled_by_default"] is False
        assert isinstance(data["rules"], list)


def test_policy_examples_load_as_profiles() -> None:
    profiles = load_policy_profiles(Path("examples/policies"))

    assert {profile.profile_id for profile in profiles} == {
        "datasheet-link-policy",
        "fab-readability-policy",
        "library-validation-policy",
        "manufacturer-part-policy",
        "minimal-library-policy",
        "procurement-fields-policy",
    }
    assert all(profile.name for profile in profiles)
    assert all(profile.enabled_by_default is False for profile in profiles)
    assert any(rule.rule_type == "regex_check" for profile in profiles for rule in profile.rules)
    assert any(rule.rule_type == "alias_field_name" for profile in profiles for rule in profile.rules)
    assert any(rule.rule_type == "max_length" for profile in profiles for rule in profile.rules)
    assert any(rule.rule_type == "reference_exists" for profile in profiles for rule in profile.rules)


def test_bundled_policy_profiles_load() -> None:
    profiles = load_bundled_policy_profiles()

    assert {profile.profile_id for profile in profiles} == {
        "datasheet-link-policy",
        "fab-readability-policy",
        "library-validation-policy",
        "manufacturer-part-policy",
        "minimal-library-policy",
        "procurement-fields-policy",
    }


def test_policy_profile_rejects_unsupported_version(tmp_path) -> None:
    policy_path = tmp_path / "future-policy.json"
    policy_path.write_text(
        json.dumps(
            {
                "policy_schema_version": POLICY_SCHEMA_VERSION + 1,
                "id": "future",
                "name": "Future",
                "enabled_by_default": False,
                "rules": [],
            }
        ),
        encoding="utf-8",
    )

    try:
        load_policy_profile(policy_path)
    except ValueError as error:
        assert "Unsupported policy schema version" in str(error)
    else:
        raise AssertionError("Expected ValueError")


def test_policy_profile_rejects_invalid_regex(tmp_path) -> None:
    policy_path = tmp_path / "bad-regex-policy.json"
    policy_path.write_text(
        json.dumps(
            {
                "policy_schema_version": POLICY_SCHEMA_VERSION,
                "id": "bad-regex",
                "name": "Bad Regex",
                "enabled_by_default": False,
                "rules": [
                    {
                        "id": "bad",
                        "name": "Bad",
                        "type": "regex_check",
                        "target": "symbol",
                        "field": "MPN",
                        "pattern": "[",
                        "mode": "must_match",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    try:
        load_policy_profile(policy_path)
    except ValueError as error:
        assert "Invalid regex pattern" in str(error)
    else:
        raise AssertionError("Expected ValueError")

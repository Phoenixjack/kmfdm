import json
from pathlib import Path

from kmfdm.config import (
    POLICY_SCHEMA_VERSION,
    load_bundled_policy_profiles,
    load_policy_profile,
    load_policy_profiles,
    save_policy_profile,
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


def test_policy_profile_saves_and_loads_round_trip(tmp_path) -> None:
    profile = load_policy_profiles(Path("examples/policies"))[0]
    policy_path = tmp_path / "saved-policy.json"

    save_policy_profile(profile, policy_path)

    assert load_policy_profile(policy_path) == profile


def test_manufacturer_policy_migrates_old_mpn_alias_override(tmp_path) -> None:
    policy_path = tmp_path / "manufacturer-part-policy.json"
    policy_path.write_text(
        json.dumps(
            {
                "policy_schema_version": POLICY_SCHEMA_VERSION,
                "id": "manufacturer-part-policy",
                "name": "Manufacturer Part Policy",
                "enabled_by_default": False,
                "rules": [
                    {
                        "id": "mpn-aliases",
                        "name": "Manufacturer part-number aliases",
                        "type": "alias_field_name",
                        "target": "both",
                        "canonical": "Manufacturer Part Number",
                        "aliases": ["MPN", "Mfr Part Number", "Manufacturer PN"],
                    },
                    {
                        "id": "mpn-character-shape",
                        "name": "Manufacturer part number uses expected characters",
                        "type": "regex_check",
                        "target": "symbol",
                        "field": "Manufacturer Part Number",
                        "pattern": "^[A-Za-z0-9._/+()#-]+$",
                        "mode": "must_match",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    profile = load_policy_profile(policy_path)
    alias_rule = next(rule for rule in profile.rules if rule.rule_id == "mpn-aliases")
    regex_rule = next(rule for rule in profile.rules if rule.rule_id == "mpn-character-shape")

    assert alias_rule.parameters["canonical"] == "MPN"
    assert "MPN" not in alias_rule.parameters["aliases"]
    assert "Manufacturer Part Number" in alias_rule.parameters["aliases"]
    assert regex_rule.parameters["field"] == "MPN"


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

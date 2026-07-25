from pathlib import Path

from kmfdm.config import load_policy_profiles
from kmfdm.services.policy_audit import AuditItem, audit_items_against_policies


def test_policy_audit_reports_required_field() -> None:
    policies = load_policy_profiles_from_examples()
    items = [
        AuditItem(
            item_type="symbol",
            library="Connectors",
            name="USB_C_Receptacle",
            fields={"Value": "USB-C-16P", "Datasheet": ""},
        )
    ]

    findings = audit_items_against_policies(items, policies)

    assert any(finding.rule_id == "manufacturer-required" for finding in findings)


def test_policy_audit_reports_alias_field_name() -> None:
    policies = load_policy_profiles_from_examples()
    items = [
        AuditItem(
            item_type="symbol",
            library="Analog",
            name="TPS54560",
            fields={"Value": "TPS54560", "MPN": "TPS54560BDDAR"},
        )
    ]

    findings = audit_items_against_policies(items, policies)

    assert any(finding.rule_id == "mpn-aliases" and finding.field == "MPN" for finding in findings)


def test_policy_audit_reports_max_length() -> None:
    policies = load_policy_profiles_from_examples()
    items = [
        AuditItem(
            item_type="footprint",
            library="Connectors.pretty",
            name="USB_C_Receptacle_SMD",
            fields={"Value": "USB_C_Receptacle_SMD_16P_MidMount_LongName"},
        )
    ]

    findings = audit_items_against_policies(items, policies)

    assert any(finding.rule_id == "footprint-value-length" for finding in findings)


def test_policy_audit_honors_ignore_blank_regex() -> None:
    policies = load_policy_profiles_from_examples()
    items = [
        AuditItem(
            item_type="footprint",
            library="Connectors.pretty",
            name="USB_C_Receptacle_SMD",
            fields={"Datasheet": ""},
        )
    ]

    findings = audit_items_against_policies(items, policies)

    assert not any(finding.rule_id == "datasheet-url-shape" for finding in findings)


def test_policy_audit_reports_regex_mismatch() -> None:
    policies = load_policy_profiles_from_examples()
    items = [
        AuditItem(
            item_type="symbol",
            library="Analog",
            name="BadPart",
            fields={"Manufacturer Part Number": "BAD PART NUMBER"},
        )
    ]

    findings = audit_items_against_policies(items, policies)

    assert any(finding.rule_id == "mpn-character-shape" for finding in findings)


def load_policy_profiles_from_examples():
    return load_policy_profiles(Path("examples/policies"))

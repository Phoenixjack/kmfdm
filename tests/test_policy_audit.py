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


def test_policy_audit_reports_library_validation_requirements() -> None:
    policies = load_policy_profiles_from_examples()
    items = [
        AuditItem(
            item_type="symbol",
            library="CONNECTORs.pretty/CONNECTORs.kicad_sym",
            name="CONN_HDMI",
            fields={"Value": "SS-53000-003", "Datasheet": "", "Footprint": ""},
        ),
        AuditItem(
            item_type="footprint",
            library="CONNECTORs.pretty",
            name="CONN_HDMI",
            fields={"Value": "CONN_HDMI", "3D Model": ""},
        ),
    ]

    findings = audit_items_against_policies(items, policies)

    assert any(finding.rule_id == "symbol-datasheet-required" for finding in findings)
    assert any(finding.rule_id == "symbol-footprint-required" for finding in findings)
    assert any(finding.rule_id == "footprint-3d-model-required" for finding in findings)


def test_policy_audit_reports_missing_symbol_footprint_reference() -> None:
    policies = load_policy_profiles_from_examples()
    items = [
        AuditItem(
            item_type="symbol",
            library="CONNECTORs.pretty/CONNECTORs.kicad_sym",
            name="CONN_HDMI",
            fields={"Value": "CONN_HDMI", "Datasheet": "https://example.com/hdmi.pdf", "Footprint": "CONNECTORs:MISSING"},
        ),
        AuditItem(
            item_type="footprint",
            library="CONNECTORs.pretty",
            name="CONN_USB_C",
            fields={"Value": "CONN_USB_C", "3D Model": "${CHRIS_KICAD_LIB}/CONNECTORs.pretty/CONN_USB_C.step"},
        ),
    ]

    findings = audit_items_against_policies(items, policies)

    assert any(finding.rule_id == "symbol-footprint-exists" for finding in findings)


def test_policy_audit_accepts_existing_symbol_footprint_reference() -> None:
    policies = load_policy_profiles_from_examples()
    items = [
        AuditItem(
            item_type="symbol",
            library="CONNECTORs.pretty/CONNECTORs.kicad_sym",
            name="CONN_HDMI",
            fields={"Value": "CONN_HDMI", "Datasheet": "https://example.com/hdmi.pdf", "Footprint": "CONNECTORs:CONN_HDMI"},
        ),
        AuditItem(
            item_type="footprint",
            library="CONNECTORs.pretty",
            name="CONN_HDMI",
            fields={"Value": "CONN_HDMI", "3D Model": "${CHRIS_KICAD_LIB}/CONNECTORs.pretty/CONN_HDMI.step"},
        ),
    ]

    findings = audit_items_against_policies(items, policies)

    assert not any(finding.rule_id == "symbol-footprint-exists" for finding in findings)


def load_policy_profiles_from_examples():
    return load_policy_profiles(Path("examples/policies"))

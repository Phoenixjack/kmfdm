from __future__ import annotations

import re
from dataclasses import dataclass

from kmfdm.config import PolicyProfile, PolicyRule


@dataclass(frozen=True)
class AuditItem:
    item_type: str
    library: str
    name: str
    fields: dict[str, str]


@dataclass(frozen=True)
class PolicyFinding:
    policy_id: str
    policy_name: str
    rule_id: str
    rule_name: str
    rule_type: str
    severity: str
    save_behavior: str
    item_type: str
    library: str
    item_name: str
    field: str
    message: str

    @property
    def item_label(self) -> str:
        return f"{self.library}:{self.item_name}"


def audit_items_against_policies(
    items: list[AuditItem],
    policies: list[PolicyProfile],
) -> list[PolicyFinding]:
    findings: list[PolicyFinding] = []
    for policy in policies:
        for rule in policy.rules:
            for item in items:
                if _rule_applies_to_item(rule, item):
                    findings.extend(_audit_item_against_rule(item, policy, rule))
    return findings


def _rule_applies_to_item(rule: PolicyRule, item: AuditItem) -> bool:
    return rule.target == "both" or rule.target == item.item_type


def _audit_item_against_rule(
    item: AuditItem,
    policy: PolicyProfile,
    rule: PolicyRule,
) -> list[PolicyFinding]:
    if rule.rule_type == "required_field":
        return _audit_required_field(item, policy, rule)
    if rule.rule_type == "alias_field_name":
        return _audit_alias_field_name(item, policy, rule)
    if rule.rule_type == "regex_check":
        return _audit_regex_check(item, policy, rule)
    if rule.rule_type == "max_length":
        return _audit_max_length(item, policy, rule)
    return []


def _audit_required_field(
    item: AuditItem,
    policy: PolicyProfile,
    rule: PolicyRule,
) -> list[PolicyFinding]:
    field = str(rule.parameters["field"])
    value = item.fields.get(field, "")
    if value.strip():
        return []
    return [
        _finding(
            item,
            policy,
            rule,
            field,
            f"Required field '{field}' is missing or blank.",
        )
    ]


def _audit_alias_field_name(
    item: AuditItem,
    policy: PolicyProfile,
    rule: PolicyRule,
) -> list[PolicyFinding]:
    canonical = str(rule.parameters["canonical"])
    aliases = list(rule.parameters["aliases"])
    findings = []
    for alias in aliases:
        if alias in item.fields and canonical not in item.fields:
            findings.append(
                _finding(
                    item,
                    policy,
                    rule,
                    alias,
                    f"Field '{alias}' matches preferred field '{canonical}'.",
                )
            )
    return findings


def _audit_regex_check(
    item: AuditItem,
    policy: PolicyProfile,
    rule: PolicyRule,
) -> list[PolicyFinding]:
    field = str(rule.parameters["field"])
    value = item.fields.get(field, "")
    ignore_blank = bool(rule.parameters.get("ignore_blank", False))
    if ignore_blank and not value.strip():
        return []

    pattern = str(rule.parameters["pattern"])
    mode = str(rule.parameters["mode"])
    if _regex_passes(value, pattern, mode):
        return []

    return [
        _finding(
            item,
            policy,
            rule,
            field,
            f"Field '{field}' does not satisfy regex mode '{mode}'.",
        )
    ]


def _audit_max_length(
    item: AuditItem,
    policy: PolicyProfile,
    rule: PolicyRule,
) -> list[PolicyFinding]:
    field = str(rule.parameters["field"])
    value = item.fields.get(field, "")
    max_characters = int(rule.parameters["max_characters"])
    if len(value) <= max_characters:
        return []
    return [
        _finding(
            item,
            policy,
            rule,
            field,
            f"Field '{field}' is {len(value)} characters; limit is {max_characters}.",
        )
    ]


def _regex_passes(value: str, pattern: str, mode: str) -> bool:
    compiled = re.compile(pattern)
    if mode == "must_match":
        return compiled.fullmatch(value) is not None
    if mode == "must_not_match":
        return compiled.search(value) is None
    if mode == "contains_match":
        return compiled.search(value) is not None
    return False


def _finding(
    item: AuditItem,
    policy: PolicyProfile,
    rule: PolicyRule,
    field: str,
    message: str,
) -> PolicyFinding:
    return PolicyFinding(
        policy_id=policy.profile_id,
        policy_name=policy.name,
        rule_id=rule.rule_id,
        rule_name=rule.name,
        rule_type=rule.rule_type,
        severity=rule.severity,
        save_behavior=rule.save_behavior,
        item_type=item.item_type,
        library=item.library,
        item_name=item.name,
        field=field,
        message=message,
    )

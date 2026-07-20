import json
from pathlib import Path


def test_policy_examples_are_valid_json() -> None:
    policy_dir = Path("examples/policies")
    policy_files = sorted(policy_dir.glob("*.json"))

    assert policy_files

    for policy_file in policy_files:
        data = json.loads(policy_file.read_text(encoding="utf-8"))
        assert data["name"]
        assert data["enabled_by_default"] is False
        assert isinstance(data["rules"], list)

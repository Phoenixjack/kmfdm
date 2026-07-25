import json
from pathlib import Path


def test_layout_examples_are_valid_json() -> None:
    layout_dir = Path("examples/layouts")
    layout_files = sorted(layout_dir.glob("*.json"))

    assert layout_files

    for layout_file in layout_files:
        data = json.loads(layout_file.read_text(encoding="utf-8"))
        assert data["layout_profile_version"] == 1
        assert data["id"]
        assert data["name"]
        assert data["paths"]["footprint_library"]
        assert data["paths"]["symbol_library"]
        assert data["paths"]["model_directory"]
        assert isinstance(data["discovery"]["symbol_match"], list)

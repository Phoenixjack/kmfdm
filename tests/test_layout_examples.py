import json
from pathlib import Path

from kmfdm.config import (
    LAYOUT_PROFILE_VERSION,
    load_bundled_layout_profiles,
    load_layout_profile,
    load_layout_profiles,
)


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


def test_layout_examples_load_as_profiles() -> None:
    profiles = load_layout_profiles(Path("examples/layouts"))

    assert {profile.profile_id for profile in profiles} == {
        "flat-contained-symbols",
        "separated-subfolders",
        "split-type-roots",
    }
    assert all(profile.paths.footprint_library for profile in profiles)
    assert all(profile.discovery.model_extensions for profile in profiles)


def test_bundled_layout_profiles_load() -> None:
    profiles = load_bundled_layout_profiles()

    assert {profile.profile_id for profile in profiles} == {
        "flat-contained-symbols",
        "separated-subfolders",
        "split-type-roots",
    }


def test_layout_profile_rejects_unsupported_version(tmp_path) -> None:
    profile_path = tmp_path / "future-layout.json"
    profile_path.write_text(
        json.dumps(
            {
                "layout_profile_version": LAYOUT_PROFILE_VERSION + 1,
                "id": "future",
                "name": "Future",
                "paths": {},
                "discovery": {},
            }
        ),
        encoding="utf-8",
    )

    try:
        load_layout_profile(profile_path)
    except ValueError as error:
        assert "Unsupported layout profile version" in str(error)
    else:
        raise AssertionError("Expected ValueError")

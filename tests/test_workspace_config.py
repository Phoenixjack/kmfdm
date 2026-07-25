import json

from kmfdm.config import (
    LibrarySelection,
    WorkspaceConfig,
    load_workspace_config,
    matching_symbol_library_for_footprint,
    save_workspace_config,
)


def test_load_workspace_config_returns_defaults_when_missing(tmp_path) -> None:
    config = load_workspace_config(tmp_path / ".kmfdm-workspace.json")

    assert config.library_root == ""
    assert config.path_variable == ""
    assert config.layout_profile_id == ""
    assert config.symbol_libraries == []
    assert config.footprint_libraries == []


def test_save_and_load_workspace_config_round_trip(tmp_path) -> None:
    config_path = tmp_path / ".kmfdm-workspace.json"
    config = WorkspaceConfig(
        library_root="libraries",
        path_variable="KICAD_USER_LIB",
        layout_profile_id="flat-contained-symbols",
        symbol_libraries=[LibrarySelection("symbols.kicad_sym", enabled=True)],
        footprint_libraries=[LibrarySelection("Connectors.pretty", enabled=False)],
        kia_interop={"source": "reserved-for-future-kia-import"},
    )

    save_workspace_config(config, config_path)
    loaded = load_workspace_config(config_path)

    assert loaded == config


def test_workspace_config_rejects_non_object_json(tmp_path) -> None:
    config_path = tmp_path / ".kmfdm-workspace.json"
    config_path.write_text(json.dumps([]), encoding="utf-8")

    try:
        load_workspace_config(config_path)
    except ValueError as error:
        assert "JSON object" in str(error)
    else:
        raise AssertionError("Expected ValueError")


def test_matching_symbol_library_for_footprint_finds_sibling_match(tmp_path) -> None:
    footprint_library = tmp_path / "Connectors.pretty"
    symbol_library = tmp_path / "Connectors.kicad_sym"
    footprint_library.mkdir()
    symbol_library.write_text("(kicad_symbol_lib)\n", encoding="utf-8")

    assert matching_symbol_library_for_footprint(footprint_library) == symbol_library


def test_matching_symbol_library_for_footprint_finds_contained_match(tmp_path) -> None:
    footprint_library = tmp_path / "Connectors.pretty"
    symbol_library = footprint_library / "Connectors.kicad_sym"
    footprint_library.mkdir()
    symbol_library.write_text("(kicad_symbol_lib)\n", encoding="utf-8")

    assert matching_symbol_library_for_footprint(footprint_library) == symbol_library


def test_matching_symbol_library_for_footprint_prefers_contained_match(tmp_path) -> None:
    footprint_library = tmp_path / "Connectors.pretty"
    contained_symbol_library = footprint_library / "Connectors.kicad_sym"
    sibling_symbol_library = tmp_path / "Connectors.kicad_sym"
    footprint_library.mkdir()
    contained_symbol_library.write_text("(kicad_symbol_lib)\n", encoding="utf-8")
    sibling_symbol_library.write_text("(kicad_symbol_lib)\n", encoding="utf-8")

    assert matching_symbol_library_for_footprint(footprint_library) == contained_symbol_library


def test_matching_symbol_library_for_footprint_requires_exact_sibling_match(tmp_path) -> None:
    footprint_library = tmp_path / "Connectors.pretty"
    near_miss = tmp_path / "Connector.kicad_sym"
    footprint_library.mkdir()
    near_miss.write_text("(kicad_symbol_lib)\n", encoding="utf-8")

    assert matching_symbol_library_for_footprint(footprint_library) is None

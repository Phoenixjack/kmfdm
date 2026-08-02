import json

from kmfdm.config import (
    LibrarySelection,
    WorkspaceConfig,
    candidate_symbol_libraries_for_footprint,
    create_symbol_library_for_footprint,
    default_workspace_config_path,
    default_symbol_library_for_footprint,
    load_workspace_config,
    matching_symbol_library_for_footprint,
    save_workspace_config,
    workspace_setup_issue,
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


def test_workspace_setup_issue_requires_existing_config() -> None:
    config = WorkspaceConfig(layout_profile_id="flat-contained-symbols")

    assert workspace_setup_issue(config, config_exists=False) == "No workspace configuration file was found."


def test_workspace_setup_issue_requires_layout_profile() -> None:
    config = WorkspaceConfig()

    assert workspace_setup_issue(config, config_exists=True) == "No library layout has been selected."


def test_workspace_setup_issue_passes_with_layout_profile() -> None:
    config = WorkspaceConfig(layout_profile_id="flat-contained-symbols")

    assert workspace_setup_issue(config, config_exists=True) == ""


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

    assert candidate_symbol_libraries_for_footprint(footprint_library) == [
        contained_symbol_library,
        sibling_symbol_library,
    ]
    assert matching_symbol_library_for_footprint(footprint_library) is None


def test_matching_symbol_library_for_footprint_requires_exact_sibling_match(tmp_path) -> None:
    footprint_library = tmp_path / "Connectors.pretty"
    near_miss = tmp_path / "Connector.kicad_sym"
    footprint_library.mkdir()
    near_miss.write_text("(kicad_symbol_lib)\n", encoding="utf-8")

    assert matching_symbol_library_for_footprint(footprint_library) is None


def test_candidate_symbol_libraries_for_footprint_finds_multiple_contained_files(tmp_path) -> None:
    footprint_library = tmp_path / "Connectors.pretty"
    exact_symbol_library = footprint_library / "Connectors.kicad_sym"
    extra_symbol_library = footprint_library / "Alternate.kicad_sym"
    footprint_library.mkdir()
    exact_symbol_library.write_text("(kicad_symbol_lib)\n", encoding="utf-8")
    extra_symbol_library.write_text("(kicad_symbol_lib)\n", encoding="utf-8")

    assert candidate_symbol_libraries_for_footprint(footprint_library) == [
        exact_symbol_library,
        extra_symbol_library,
    ]
    assert matching_symbol_library_for_footprint(footprint_library) is None


def test_default_symbol_library_for_footprint_uses_contained_flat_layout_name(tmp_path) -> None:
    footprint_library = tmp_path / "Connectors.pretty"

    assert default_symbol_library_for_footprint(footprint_library) == footprint_library / "Connectors.kicad_sym"


def test_create_symbol_library_for_footprint_writes_empty_kicad_symbol_library(tmp_path) -> None:
    footprint_library = tmp_path / "Connectors.pretty"

    symbol_library = create_symbol_library_for_footprint(footprint_library)

    assert symbol_library == footprint_library / "Connectors.kicad_sym"
    assert symbol_library.read_text(encoding="utf-8") == (
        "(kicad_symbol_lib\n"
        "  (version 20231120)\n"
        "  (generator \"kmfdm\")\n"
        "  (generator_version \"0.1.0\")\n"
        ")\n"
    )


def test_default_workspace_config_path_finds_project_root_from_venv_script_path(tmp_path) -> None:
    project_root = tmp_path / "kmfdm"
    scripts_dir = project_root / ".venv" / "Scripts"
    package_dir = project_root / "src" / "kmfdm"
    scripts_dir.mkdir(parents=True)
    package_dir.mkdir(parents=True)
    (project_root / "pyproject.toml").write_text("[project]\nname = \"kmfdm\"\n", encoding="utf-8")

    config_path = default_workspace_config_path(scripts_dir / "kmfdm.exe")

    assert config_path == project_root / ".kmfdm-workspace.json"

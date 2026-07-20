import json

from kmfdm.config import LibrarySelection, WorkspaceConfig, load_workspace_config, save_workspace_config


def test_load_workspace_config_returns_defaults_when_missing(tmp_path) -> None:
    config = load_workspace_config(tmp_path / ".kmfdm-workspace.json")

    assert config.library_root == ""
    assert config.path_variable == ""
    assert config.symbol_libraries == []
    assert config.footprint_libraries == []


def test_save_and_load_workspace_config_round_trip(tmp_path) -> None:
    config_path = tmp_path / ".kmfdm-workspace.json"
    config = WorkspaceConfig(
        library_root="libraries",
        path_variable="KICAD_USER_LIB",
        symbol_libraries=[LibrarySelection("symbols.kicad_sym", enabled=True)],
        footprint_libraries=[LibrarySelection("Connectors.pretty", enabled=False)],
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

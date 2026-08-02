from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


CONFIG_SCHEMA_VERSION = 1
DEFAULT_CONFIG_FILENAME = ".kmfdm-workspace.json"
KICAD_SYMBOL_LIBRARY_TEMPLATE = """(kicad_symbol_lib
  (version 20231120)
  (generator "kmfdm")
  (generator_version "0.1.0")
)
"""


@dataclass
class LibrarySelection:
    path: str
    enabled: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any] | str) -> LibrarySelection:
        if isinstance(data, str):
            return cls(path=data)
        return cls(
            path=str(data.get("path", "")),
            enabled=bool(data.get("enabled", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "enabled": self.enabled,
        }


@dataclass
class WorkspaceConfig:
    library_root: str = ""
    path_variable: str = ""
    layout_profile_id: str = ""
    symbol_libraries: list[LibrarySelection] = field(default_factory=list)
    footprint_libraries: list[LibrarySelection] = field(default_factory=list)
    policy_files: list[LibrarySelection] = field(default_factory=list)
    kia_interop: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkspaceConfig:
        return cls(
            library_root=str(data.get("library_root", "")),
            path_variable=str(data.get("path_variable", "")),
            layout_profile_id=str(data.get("layout_profile_id", "")),
            symbol_libraries=_library_list_from_dict(data.get("symbol_libraries", [])),
            footprint_libraries=_library_list_from_dict(data.get("footprint_libraries", [])),
            policy_files=_library_list_from_dict(data.get("policy_files", [])),
            kia_interop=_dict_from_value(data.get("kia_interop", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "config_schema_version": CONFIG_SCHEMA_VERSION,
            "library_root": self.library_root,
            "path_variable": self.path_variable,
            "layout_profile_id": self.layout_profile_id,
            "symbol_libraries": [item.to_dict() for item in self.symbol_libraries],
            "footprint_libraries": [item.to_dict() for item in self.footprint_libraries],
            "policy_files": [item.to_dict() for item in self.policy_files],
            "kia_interop": dict(self.kia_interop),
        }


def load_workspace_config(config_path: Path | None = None) -> WorkspaceConfig:
    path = config_path or Path.cwd() / DEFAULT_CONFIG_FILENAME
    if not path.exists():
        return WorkspaceConfig()

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError(f"Workspace config must contain a JSON object: {path}")

    return WorkspaceConfig.from_dict(data)


def save_workspace_config(config: WorkspaceConfig, config_path: Path | None = None) -> None:
    path = config_path or Path.cwd() / DEFAULT_CONFIG_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config.to_dict(), indent=2) + "\n", encoding="utf-8")


def default_workspace_config_path(start_path: Path | None = None) -> Path:
    for candidate in _workspace_config_search_starts(start_path):
        base_path = candidate.parent if candidate.is_file() else candidate
        for path in [base_path, *base_path.parents]:
            if _looks_like_project_root(path):
                return path / DEFAULT_CONFIG_FILENAME
    return Path.cwd() / DEFAULT_CONFIG_FILENAME


def workspace_setup_issue(config: WorkspaceConfig, *, config_exists: bool = True) -> str:
    if not config_exists:
        return "No workspace configuration file was found."
    if not config.layout_profile_id:
        return "No library layout has been selected."
    return ""


def _library_list_from_dict(value: Any) -> list[LibrarySelection]:
    if not isinstance(value, list):
        return []
    return [LibrarySelection.from_dict(item) for item in value]


def _dict_from_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _workspace_config_search_starts(start_path: Path | None = None) -> list[Path]:
    starts = []
    if start_path is not None:
        starts.append(start_path)
    starts.extend([Path.cwd(), Path(sys.executable)])
    return starts


def _looks_like_project_root(path: Path) -> bool:
    return (path / "pyproject.toml").is_file() and (path / "src" / "kmfdm").is_dir()


def matching_symbol_library_for_footprint(footprint_library: Path | str) -> Path | None:
    candidates = candidate_symbol_libraries_for_footprint(footprint_library)
    return candidates[0] if len(candidates) == 1 else None


def candidate_symbol_libraries_for_footprint(footprint_library: Path | str) -> list[Path]:
    footprint_path = Path(footprint_library)
    if footprint_path.suffix != ".pretty":
        return []

    exact_name = f"{footprint_path.stem}.kicad_sym"
    exact_candidates = [
        footprint_path / exact_name,
        footprint_path.with_suffix(".kicad_sym"),
    ]
    discovered_candidates = sorted(footprint_path.glob("*.kicad_sym")) if footprint_path.is_dir() else []

    candidates: list[Path] = []
    for symbol_path in [*exact_candidates, *discovered_candidates]:
        if symbol_path.is_file() and symbol_path not in candidates:
            candidates.append(symbol_path)
    return candidates


def default_symbol_library_for_footprint(footprint_library: Path | str) -> Path | None:
    footprint_path = Path(footprint_library)
    if footprint_path.suffix != ".pretty":
        return None
    return footprint_path / f"{footprint_path.stem}.kicad_sym"


def create_symbol_library_for_footprint(footprint_library: Path | str) -> Path:
    symbol_library = default_symbol_library_for_footprint(footprint_library)
    if symbol_library is None:
        raise ValueError(f"Footprint library must be a .pretty directory: {footprint_library}")
    if symbol_library.exists():
        return symbol_library

    symbol_library.parent.mkdir(parents=True, exist_ok=True)
    symbol_library.write_text(KICAD_SYMBOL_LIBRARY_TEMPLATE, encoding="utf-8")
    return symbol_library

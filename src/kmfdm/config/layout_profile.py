from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any


LAYOUT_PROFILE_VERSION = 1


@dataclass(frozen=True)
class LayoutPaths:
    footprint_library: str
    symbol_library: str
    model_directory: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LayoutPaths:
        return cls(
            footprint_library=_required_string(data, "footprint_library"),
            symbol_library=_required_string(data, "symbol_library"),
            model_directory=_required_string(data, "model_directory"),
        )


@dataclass(frozen=True)
class LayoutDiscovery:
    symbol_match: list[str]
    model_extensions: list[str]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LayoutDiscovery:
        return cls(
            symbol_match=_required_string_list(data, "symbol_match"),
            model_extensions=_required_string_list(data, "model_extensions"),
        )


@dataclass(frozen=True)
class LayoutProfile:
    profile_id: str
    name: str
    description: str
    paths: LayoutPaths
    discovery: LayoutDiscovery

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LayoutProfile:
        version = data.get("layout_profile_version")
        if version != LAYOUT_PROFILE_VERSION:
            raise ValueError(f"Unsupported layout profile version: {version}")

        return cls(
            profile_id=_required_string(data, "id"),
            name=_required_string(data, "name"),
            description=str(data.get("description", "")),
            paths=LayoutPaths.from_dict(_required_dict(data, "paths")),
            discovery=LayoutDiscovery.from_dict(_required_dict(data, "discovery")),
        )


def load_layout_profile(path: Path) -> LayoutProfile:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    return _profile_from_data(data, path)


def load_bundled_layout_profiles() -> list[LayoutProfile]:
    directory = resources.files("kmfdm").joinpath("resources", "layouts")
    profile_files = sorted(
        (item for item in directory.iterdir() if item.name.endswith(".json")),
        key=lambda item: item.name,
    )

    profiles = []
    for profile_file in profile_files:
        with profile_file.open("r", encoding="utf-8") as file:
            profiles.append(_profile_from_data(json.load(file), profile_file))

    return profiles


def _profile_from_data(data: Any, source: object) -> LayoutProfile:
    if not isinstance(data, dict):
        raise ValueError(f"Layout profile must contain a JSON object: {source}")

    return LayoutProfile.from_dict(data)


def load_layout_profiles(directory: Path) -> list[LayoutProfile]:
    return [load_layout_profile(path) for path in sorted(directory.glob("*.json"))]


def _required_dict(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"Layout profile field must be an object: {key}")
    return value


def _required_string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Layout profile field must be a non-empty string: {key}")
    return value


def _required_string_list(data: dict[str, Any], key: str) -> list[str]:
    value = data.get(key)
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
        raise ValueError(f"Layout profile field must be a non-empty string list: {key}")
    return list(value)

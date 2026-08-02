from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kmfdm.config import LibrarySelection, WorkspaceConfig
from kmfdm.parsers.sexpr import SExpr, parse_sexpressions, sexpr_head


@dataclass(frozen=True)
class KiCadLibraryItem:
    item_type: str
    library: str
    name: str
    fields: dict[str, str]
    source_path: Path


def scan_workspace_libraries(
    config: WorkspaceConfig,
) -> tuple[list[KiCadLibraryItem], list[KiCadLibraryItem]]:
    return (
        scan_symbol_libraries(config.symbol_libraries),
        scan_footprint_libraries(config.footprint_libraries),
    )


def scan_symbol_libraries(selections: list[LibrarySelection]) -> list[KiCadLibraryItem]:
    items: list[KiCadLibraryItem] = []
    for selection in selections:
        if not selection.enabled:
            continue
        try:
            items.extend(scan_symbol_library(Path(selection.path)))
        except (OSError, UnicodeDecodeError, ValueError):
            continue
    return items


def scan_footprint_libraries(selections: list[LibrarySelection]) -> list[KiCadLibraryItem]:
    items: list[KiCadLibraryItem] = []
    for selection in selections:
        if not selection.enabled:
            continue
        items.extend(scan_footprint_library(Path(selection.path)))
    return items


def scan_symbol_library(path: Path) -> list[KiCadLibraryItem]:
    if not path.is_file():
        return []

    forms = parse_sexpressions(path.read_text(encoding="utf-8-sig"))
    library_form = _first_form(forms, "kicad_symbol_lib")
    if library_form is None:
        return []

    return [
        KiCadLibraryItem(
            item_type="symbol",
            library=_symbol_library_label(path),
            name=_node_string(symbol_node, 1),
            fields=_symbol_fields(symbol_node),
            source_path=path,
        )
        for symbol_node in _direct_children(library_form, "symbol")
        if _node_string(symbol_node, 1)
    ]


def scan_footprint_library(path: Path) -> list[KiCadLibraryItem]:
    if not path.is_dir():
        return []

    try:
        file_paths = sorted(path.glob("*.kicad_mod"))
    except OSError:
        return []

    return [
        item
        for file_path in file_paths
        for item in _scan_footprint_file(file_path)
    ]


def _scan_footprint_file(path: Path) -> list[KiCadLibraryItem]:
    try:
        forms = parse_sexpressions(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, ValueError):
        return []
    footprint_form = _first_form(forms, "footprint")
    if footprint_form is None:
        return []

    name = _node_string(footprint_form, 1) or path.stem
    return [
        KiCadLibraryItem(
            item_type="footprint",
            library=path.parent.name,
            name=name,
            fields=_footprint_fields(footprint_form),
            source_path=path,
        )
    ]


def _symbol_fields(symbol_node: list[SExpr]) -> dict[str, str]:
    return _property_fields(symbol_node)


def _footprint_fields(footprint_form: list[SExpr]) -> dict[str, str]:
    fields = _property_fields(footprint_form)
    value = _footprint_text(footprint_form, "value")
    if value and "Value" not in fields:
        fields["Value"] = value
    models = _model_paths(footprint_form)
    if models:
        fields["3D Model"] = "; ".join(models)
    return fields


def _property_fields(node: list[SExpr]) -> dict[str, str]:
    fields: dict[str, str] = {}
    for child in _direct_children(node, "property"):
        key = _node_string(child, 1)
        value = _node_string(child, 2)
        if key:
            fields[key] = value
    return fields


def _footprint_text(node: list[SExpr], text_kind: str) -> str:
    for child in _direct_children(node, "fp_text"):
        if _node_string(child, 1) == text_kind:
            return _node_string(child, 2)
    return ""


def _model_paths(node: list[SExpr]) -> list[str]:
    return [
        model_path
        for child in _direct_children(node, "model")
        if (model_path := _node_string(child, 1))
    ]


def _first_form(forms: list[SExpr], head: str) -> list[SExpr] | None:
    for form in forms:
        if isinstance(form, list) and sexpr_head(form) == head:
            return form
    return None


def _direct_children(node: list[SExpr], head: str) -> list[list[SExpr]]:
    return [
        child
        for child in node[1:]
        if isinstance(child, list) and sexpr_head(child) == head
    ]


def _node_string(node: list[SExpr], index: int) -> str:
    if len(node) <= index:
        return ""
    value = node[index]
    return value if isinstance(value, str) else ""


def _symbol_library_label(path: Path) -> str:
    if path.parent.suffix == ".pretty":
        return f"{path.parent.name}/{path.name}"
    return path.name

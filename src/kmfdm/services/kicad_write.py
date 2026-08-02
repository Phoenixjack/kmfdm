from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


class KiCadWriteError(RuntimeError):
    pass


@dataclass(frozen=True)
class KiCadMetadataChange:
    item_type: str
    source_path: Path
    item_name: str
    field_name: str
    value: str


@dataclass
class SpanAtom:
    value: str
    start: int
    end: int
    quoted: bool = False


@dataclass
class SpanList:
    start: int
    end: int = 0
    children: list[SpanNode] = field(default_factory=list)


SpanNode = SpanAtom | SpanList


def save_metadata_changes(changes: list[KiCadMetadataChange]) -> None:
    changes_by_path: dict[Path, list[KiCadMetadataChange]] = {}
    for change in changes:
        changes_by_path.setdefault(change.source_path, []).append(change)

    for source_path, path_changes in changes_by_path.items():
        _save_path_changes(source_path, path_changes)


def _save_path_changes(source_path: Path, changes: list[KiCadMetadataChange]) -> None:
    try:
        text = source_path.read_text(encoding="utf-8-sig")
        forms = _parse_span_sexpressions(text)
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise KiCadWriteError(f"Could not read KiCad file: {source_path}") from error

    edits: list[tuple[int, int, str]] = []
    for change in changes:
        if change.item_type == "symbol":
            _collect_symbol_change(text, forms, change, edits)
        elif change.item_type == "footprint":
            _collect_footprint_change(text, forms, change, edits)
        else:
            raise KiCadWriteError(f"Unsupported KiCad item type: {change.item_type}")

    updated_text = _apply_text_edits(text, edits)
    try:
        source_path.write_text(updated_text, encoding="utf-8")
    except OSError as error:
        raise KiCadWriteError(f"Could not write KiCad file: {source_path}") from error


def _collect_symbol_change(
    text: str,
    forms: list[SpanNode],
    change: KiCadMetadataChange,
    edits: list[tuple[int, int, str]],
) -> None:
    library_form = _first_form(forms, "kicad_symbol_lib")
    if library_form is None:
        raise KiCadWriteError(f"Missing kicad_symbol_lib form: {change.source_path}")

    symbol_node = _find_direct_child_by_name(library_form, "symbol", change.item_name)
    if symbol_node is None:
        raise KiCadWriteError(f"Missing symbol '{change.item_name}': {change.source_path}")

    _collect_property_change(text, symbol_node, change.field_name, change.value, edits)


def _collect_footprint_change(
    text: str,
    forms: list[SpanNode],
    change: KiCadMetadataChange,
    edits: list[tuple[int, int, str]],
) -> None:
    footprint_form = _first_form(forms, "footprint")
    if footprint_form is None:
        raise KiCadWriteError(f"Missing footprint form: {change.source_path}")
    if _node_string(footprint_form, 1) not in {"", change.item_name}:
        raise KiCadWriteError(f"Footprint name mismatch for '{change.item_name}': {change.source_path}")

    if change.field_name == "Value" and _find_property(footprint_form, "Value") is None:
        fp_value = _find_direct_child_by_name(footprint_form, "fp_text", "value")
        if fp_value is None:
            _collect_insert_child(text, footprint_form, _format_fp_text_value(change.value), edits)
            return
        value_atom = _node_atom(fp_value, 2)
        if value_atom is None:
            raise KiCadWriteError(f"Malformed fp_text value: {change.source_path}")
        edits.append((value_atom.start, value_atom.end, _format_value_like(value_atom, change.value)))
        return

    _collect_property_change(text, footprint_form, change.field_name, change.value, edits)


def _collect_property_change(
    text: str,
    node: SpanList,
    field_name: str,
    value: str,
    edits: list[tuple[int, int, str]],
) -> None:
    property_node = _find_property(node, field_name)
    if property_node is None:
        _collect_insert_child(text, node, _format_property(_canonical_field_name(field_name), value), edits)
        return

    value_atom = _node_atom(property_node, 2)
    if value_atom is None:
        raise KiCadWriteError(f"Malformed property '{field_name}'.")
    edits.append((value_atom.start, value_atom.end, _format_value_like(value_atom, value)))


def _collect_insert_child(
    text: str,
    parent: SpanList,
    child_text: str,
    edits: list[tuple[int, int, str]],
) -> None:
    insert_at = parent.end - 1
    while insert_at > parent.start and text[insert_at - 1].isspace():
        insert_at -= 1
    indent = " " * (_node_column(text, parent) + 2)
    edits.append((insert_at, insert_at, f"\n{indent}{child_text}"))


def _apply_text_edits(text: str, edits: list[tuple[int, int, str]]) -> str:
    updated = text
    for start, end, replacement in sorted(edits, key=lambda edit: edit[0], reverse=True):
        updated = updated[:start] + replacement + updated[end:]
    return updated


def _parse_span_sexpressions(text: str) -> list[SpanNode]:
    root = SpanList(start=0)
    stack = [root]
    index = 0
    while index < len(text):
        char = text[index]
        if char.isspace():
            index += 1
            continue
        if char == ";":
            index = _skip_comment(text, index)
            continue
        if char == "(":
            node = SpanList(start=index)
            stack[-1].children.append(node)
            stack.append(node)
            index += 1
            continue
        if char == ")":
            if len(stack) == 1:
                raise ValueError("Unexpected closing parenthesis.")
            stack[-1].end = index + 1
            stack.pop()
            index += 1
            continue
        if char == '"':
            atom, index = _read_span_string(text, index)
            stack[-1].children.append(atom)
            continue

        atom, index = _read_span_atom(text, index)
        stack[-1].children.append(atom)

    if len(stack) != 1:
        raise ValueError("Unclosed parenthesis.")
    root.end = len(text)
    return root.children


def _skip_comment(text: str, index: int) -> int:
    while index < len(text) and text[index] not in "\r\n":
        index += 1
    return index


def _read_span_string(text: str, index: int) -> tuple[SpanAtom, int]:
    start = index
    index += 1
    chars: list[str] = []
    while index < len(text):
        char = text[index]
        if char == "\\":
            if index + 1 >= len(text):
                raise ValueError("Unclosed string escape.")
            chars.append(text[index + 1])
            index += 2
            continue
        if char == '"':
            return SpanAtom("".join(chars), start, index + 1, quoted=True), index + 1
        chars.append(char)
        index += 1
    raise ValueError("Unclosed string.")


def _read_span_atom(text: str, index: int) -> tuple[SpanAtom, int]:
    start = index
    while index < len(text) and not text[index].isspace() and text[index] not in "();":
        index += 1
    return SpanAtom(text[start:index], start, index), index


def _first_form(forms: list[SpanNode], head: str) -> SpanList | None:
    for form in forms:
        if isinstance(form, SpanList) and _node_head(form) == head:
            return form
    return None


def _direct_children(node: SpanList, head: str) -> list[SpanList]:
    return [
        child
        for child in node.children[1:]
        if isinstance(child, SpanList) and _node_head(child) == head
    ]


def _find_direct_child_by_name(node: SpanList, head: str, name: str) -> SpanList | None:
    for child in _direct_children(node, head):
        if _node_string(child, 1) == name:
            return child
    return None


def _find_property(node: SpanList, field_name: str) -> SpanList | None:
    aliases = _field_aliases(field_name)
    for child in _direct_children(node, "property"):
        if _node_string(child, 1).casefold() in aliases:
            return child
    return None


def _node_head(node: SpanList) -> str:
    return _node_string(node, 0)


def _node_string(node: SpanList, index: int) -> str:
    atom = _node_atom(node, index)
    return "" if atom is None else atom.value


def _node_atom(node: SpanList, index: int) -> SpanAtom | None:
    if len(node.children) <= index:
        return None
    child = node.children[index]
    return child if isinstance(child, SpanAtom) else None


def _field_aliases(field_name: str) -> set[str]:
    aliases = {
        "Manufacturer": ["Manufacturer", "MANUFACTURER", "MFR", "MFG"],
        "MPN": [
            "MPN",
            "Manufacturer Part Number",
            "Manufacturer_Part_Number",
            "MANUFACTURER_PART_NUMBER",
            "PARTNUMBER",
            "PART_NUMBER",
        ],
        "Datasheet": ["Datasheet", "DATASHEET", "Data Sheet", "DATA_SHEET"],
        "Value": ["Value"],
    }.get(field_name, [field_name])
    return {alias.casefold() for alias in aliases}


def _canonical_field_name(field_name: str) -> str:
    return field_name


def _format_value_like(original_atom: SpanAtom, value: str) -> str:
    return _quote_string(value) if original_atom.quoted or _needs_quote(value) else value


def _format_property(field_name: str, value: str) -> str:
    return f'(property {_quote_string(field_name)} {_quote_string(value)})'


def _format_fp_text_value(value: str) -> str:
    return f'(fp_text value {_quote_string(value)})'


def _quote_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _needs_quote(value: str) -> bool:
    return not value or any(char.isspace() or char in '();"\\' for char in value)


def _node_column(text: str, node: SpanList) -> int:
    line_start = text.rfind("\n", 0, node.start) + 1
    return node.start - line_start

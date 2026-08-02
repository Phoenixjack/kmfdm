from __future__ import annotations

SExpr = str | list["SExpr"]


class SExpressionParseError(ValueError):
    pass


def parse_sexpressions(text: str) -> list[SExpr]:
    tokens = _tokenize(text)
    root: list[SExpr] = []
    stack: list[list[SExpr]] = [root]

    for token in tokens:
        if token == "(":
            node: list[SExpr] = []
            stack[-1].append(node)
            stack.append(node)
        elif token == ")":
            if len(stack) == 1:
                raise SExpressionParseError("Unexpected closing parenthesis.")
            stack.pop()
        else:
            stack[-1].append(token)

    if len(stack) != 1:
        raise SExpressionParseError("Unclosed parenthesis.")

    return root


def sexpr_head(node: SExpr) -> str | None:
    if isinstance(node, list) and node and isinstance(node[0], str):
        return node[0]
    return None


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char.isspace():
            index += 1
            continue
        if char == ";":
            index = _skip_comment(text, index)
            continue
        if char in "()":
            tokens.append(char)
            index += 1
            continue
        if char == '"':
            value, index = _read_string(text, index)
            tokens.append(value)
            continue

        value, index = _read_atom(text, index)
        tokens.append(value)

    return tokens


def _skip_comment(text: str, index: int) -> int:
    while index < len(text) and text[index] not in "\r\n":
        index += 1
    return index


def _read_string(text: str, index: int) -> tuple[str, int]:
    index += 1
    chars: list[str] = []
    while index < len(text):
        char = text[index]
        if char == "\\":
            if index + 1 >= len(text):
                raise SExpressionParseError("Unclosed string escape.")
            chars.append(text[index + 1])
            index += 2
            continue
        if char == '"':
            return "".join(chars), index + 1
        chars.append(char)
        index += 1

    raise SExpressionParseError("Unclosed string.")


def _read_atom(text: str, index: int) -> tuple[str, int]:
    start = index
    while index < len(text) and not text[index].isspace() and text[index] not in "();":
        index += 1
    return text[start:index], index

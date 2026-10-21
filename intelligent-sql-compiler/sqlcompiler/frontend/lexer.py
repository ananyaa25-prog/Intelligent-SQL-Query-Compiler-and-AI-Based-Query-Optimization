"""Hand-written lexical analyzer for SQL with line and column tracking."""

from __future__ import annotations

import re
from dataclasses import dataclass


class LexicalError(SyntaxError):
    """Raised when an unknown character or invalid token is encountered."""

    def __init__(self, message: str, line: int, column: int, snippet: str = ""):
        self.message = message
        self.line = line
        self.column = column
        self.snippet = snippet
        full = f"Lexical error at line {line}, column {column}: {message}"
        if snippet:
            full = f"{full}\n{snippet}"
        super().__init__(full)


@dataclass
class Token:
    type: str
    value: str
    position: int
    line: int = 1
    column: int = 1


KEYWORDS = {
    "SELECT", "FROM", "WHERE", "AND", "OR", "NOT",
    "IN", "BETWEEN", "LIKE", "IS", "NULL", "AS", "ORDER", "BY",
    "ASC", "DESC", "LIMIT", "OFFSET", "GROUP", "HAVING",
    "COUNT", "SUM", "AVG", "MIN", "MAX", "DISTINCT",
    "JOIN", "INNER", "LEFT", "RIGHT", "ON", "UNION",
    "TRUE", "FALSE"
}

# Regex pattern for SQL tokens
TOKEN_PATTERN = re.compile(
    r"""
    (?P<WHITESPACE>\s+)
    |(?P<COMMENT>--[^\n]*|/\*[\s\S]*?\*/)
    |(?P<NUMBER>\d+(?:\.\d+)?)
    |(?P<STRING>'(?:''|[^'])*'|"(?:\\"|[^"])*")
    |(?P<OPERATOR><=|>=|<>|!=|=|<|>|\+|-|\*|/)
    |(?P<PUNCTUATION>[(),.;])
    |(?P<IDENTIFIER>[A-Za-z_][A-Za-z0-9_$]*)
    |(?P<MISMATCH>.)
    """,
    re.VERBOSE,
)


def format_caret_snippet(sql: str, line: int, column: int) -> str:
    """Produce a source snippet pointing a caret at the specified line and column."""
    lines = sql.splitlines()
    if 1 <= line <= len(lines):
        line_text = lines[line - 1]
        indent = " " * max(0, column - 1)
        return f"{line_text}\n{indent}^"
    return ""


def tokenize(sql: str) -> list[Token]:
    """Convert SQL text into a sequence of tokens with line and column tracking."""
    tokens = []
    line_num = 1
    line_start = 0

    for match in TOKEN_PATTERN.finditer(sql):
        kind = match.lastgroup
        value = match.group()
        position = match.start()
        column = position - line_start + 1

        if kind == "WHITESPACE":
            newline_count = value.count("\n")
            if newline_count > 0:
                line_num += newline_count
                line_start = match.start() + value.rfind("\n") + 1
            continue

        if kind == "COMMENT":
            newline_count = value.count("\n")
            if newline_count > 0:
                line_num += newline_count
                line_start = match.start() + value.rfind("\n") + 1
            continue

        if kind == "MISMATCH":
            snippet = format_caret_snippet(sql, line_num, column)
            raise LexicalError(
                f"Unexpected character {value!r}",
                line=line_num,
                column=column,
                snippet=snippet,
            )

        if kind == "IDENTIFIER" and value.upper() in KEYWORDS:
            kind = "KEYWORD"

        tokens.append(Token(
            type=kind,
            value=value,
            position=position,
            line=line_num,
            column=column,
        ))

    return tokens

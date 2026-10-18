
import re
from dataclasses import dataclass


@dataclass
class Token:
    type: str
    value: str
    position: int


KEYWORDS = {
    "SELECT", "FROM", "WHERE", "AND", "OR", "NOT",
    "IN", "LIKE", "IS", "NULL", "AS", "ORDER", "BY",
    "ASC", "DESC", "LIMIT", "OFFSET", "GROUP", "HAVING",
    "COUNT", "SUM", "AVG", "MIN", "MAX", "DISTINCT",
    "JOIN", "INNER", "LEFT", "RIGHT", "ON", "UNION"
}

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


def tokenize(sql: str) -> list[Token]:
    """Convert SQL text into a sequence of tokens."""
    tokens = []

    for match in TOKEN_PATTERN.finditer(sql):
        kind = match.lastgroup
        value = match.group()
        position = match.start()

        if kind in {"WHITESPACE", "COMMENT"}:
            continue

        if kind == "MISMATCH":
            raise SyntaxError(
                f"Unexpected character {value!r} at position {position}"
            )

        if kind == "IDENTIFIER" and value.upper() in KEYWORDS:
            kind = "KEYWORD"

        tokens.append(Token(kind, value, position))

    return tokens


if __name__ == "__main__":
    sample_sql = (
        "SELECT name FROM students "
        "WHERE gpa >= 9.0 AND department = 'CSE';"
    )

    for token in tokenize(sample_sql):
        print(f"{token.type:<12} {token.value:<15} position={token.position}")

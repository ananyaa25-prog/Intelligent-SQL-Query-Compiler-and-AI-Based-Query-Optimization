"""Compatibility wrapper for Person 1 lexer."""

from sqlcompiler.frontend.lexer import (
    Token,
    LexicalError,
    KEYWORDS,
    TOKEN_PATTERN,
    tokenize,
    format_caret_snippet,
)

__all__ = [
    "Token",
    "LexicalError",
    "KEYWORDS",
    "TOKEN_PATTERN",
    "tokenize",
    "format_caret_snippet",
]

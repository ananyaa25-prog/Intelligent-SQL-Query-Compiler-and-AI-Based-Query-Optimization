"""Structured diagnostics for compiler semantic analysis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlcompiler.frontend.lexer import format_caret_snippet


@dataclass
class Diagnostic:
    """Represents a compiler diagnostic (error, warning, or informational note)."""
    severity: str  # "ERROR", "WARNING", "NOTE"
    code: str      # e.g. "E101" (Unknown table), "E102" (Unknown column), etc.
    message: str
    line: int = 1
    column: int = 1
    hint: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "line": self.line,
            "column": self.column,
            "hint": self.hint,
        }

    def format(self, sql: str = "") -> str:
        loc = f"line {self.line}, column {self.column}"
        header = f"[{self.code}] {self.severity.upper()} ({loc}): {self.message}"
        snippet = format_caret_snippet(sql, self.line, self.column) if sql else ""
        lines = [header]
        if snippet:
            lines.append(snippet)
        if self.hint:
            lines.append(f"Hint: {self.hint}")
        return "\n".join(lines)

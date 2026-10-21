"""Codegen module: VDBE bytecode inspection and static metrics."""

from sqlcompiler.codegen.bytecode import (
    explain_bytecode,
    compare_bytecode,
    categorize_opcode,
)

__all__ = [
    "explain_bytecode",
    "compare_bytecode",
    "categorize_opcode",
]

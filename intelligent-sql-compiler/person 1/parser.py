"""Compatibility wrapper for Person 1 parser."""

from sqlcompiler.frontend.ast_nodes import (
    SelectStmt,
    SelectItem,
    TableRef,
    Join,
    OrderByItem,
    Expression,
    Star,
    ColumnRef,
    Literal,
    BinaryOp,
    UnaryOp,
    Between,
    InList,
    IsNull,
    FunctionCall,
    ast_to_sql,
    ast_to_dict,
    ast_to_dot,
)
from sqlcompiler.frontend.parser import Parser, ParseError, parse_sql

# Backward-compatibility alias
SelectAST = SelectStmt

__all__ = [
    "SelectAST",
    "SelectStmt",
    "SelectItem",
    "TableRef",
    "Join",
    "OrderByItem",
    "Expression",
    "Star",
    "ColumnRef",
    "Literal",
    "BinaryOp",
    "UnaryOp",
    "Between",
    "InList",
    "IsNull",
    "FunctionCall",
    "Parser",
    "ParseError",
    "parse_sql",
    "ast_to_sql",
    "ast_to_dict",
    "ast_to_dot",
]

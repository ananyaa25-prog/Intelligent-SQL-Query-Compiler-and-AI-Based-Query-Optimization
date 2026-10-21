"""Compilation entrypoint for Person 1 frontend and optimizer."""

from pathlib import Path
import sys

# Support direct execution
PERSON1_DIR = Path(__file__).resolve().parent
ROOT_DIR = PERSON1_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sqlcompiler.frontend.lexer import tokenize
from sqlcompiler.frontend.parser import parse_sql
from sqlcompiler.frontend.ast_nodes import ast_to_sql, ast_to_dict, ast_to_dot
from optimizer import optimize_sql


def compile_sql(sql: str) -> dict:
    """Run SQL through lexer, parser, and optimizer."""
    if not sql or not sql.strip():
        return {
            "success": False,
            "error": "Please enter a SQL query.",
        }

    try:
        tokens = tokenize(sql)
        ast = parse_sql(sql)
        optimized_sql = optimize_sql(sql)

        return {
            "success": True,
            "tokens": [
                {
                    "type": token.type,
                    "value": token.value,
                    "position": token.position,
                    "line": token.line,
                    "column": token.column,
                }
                for token in tokens
            ],
            "ast": {
                "columns": [c.to_sql() for c in ast.columns],
                "table": ast.table,
                "where": ast.where.to_sql() if ast.where else None,
                "order_by": ", ".join(o.to_sql() for o in ast.order_by) if ast.order_by else None,
                "limit": ast.limit,
                "tree": ast_to_dict(ast),
            },
            "optimized_sql": optimized_sql,
        }

    except (SyntaxError, ValueError) as exc:
        return {
            "success": False,
            "error": str(exc),
        }


if __name__ == "__main__":
    example = (
        "SELECT student_id, name FROM students "
        "WHERE gpa >= 9.0 AND gpa >= 8.0;"
    )

    result = compile_sql(example)
    if result["success"]:
        print("TOKENS:", len(result["tokens"]))
        print("AST:", result["ast"])
        print("OPTIMIZED:", result["optimized_sql"])
    else:
        print("Error:", result["error"])

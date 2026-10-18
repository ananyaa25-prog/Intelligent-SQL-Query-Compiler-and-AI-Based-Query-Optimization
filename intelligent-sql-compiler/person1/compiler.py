
from pathlib import Path
import sys

# Support imports both from the project root and direct script execution.
PERSON1_DIR = Path(__file__).resolve().parent
if str(PERSON1_DIR) not in sys.path:
    sys.path.insert(0, str(PERSON1_DIR))

from lexer import tokenize
from parser import parse_sql
from optimizer import optimize_sql


def compile_sql(sql: str) -> dict:
    """
    Run the current SQL through the lexer, parser, and optimizer.

    Returns token details, the AST, and optimized SQL.
    """
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
                }
                for token in tokens
            ],
            "ast": {
                "columns": ast.columns,
                "table": ast.table,
                "where": ast.where,
                "order_by": ast.order_by,
                "limit": ast.limit,
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
        print("TOKENS")
        for token in result["tokens"]:
            print(token)

        print("\nAST")
        print(result["ast"])

        print("\nOPTIMIZED SQL")
        print(result["optimized_sql"])
    else:
        print("Compilation error:", result["error"])

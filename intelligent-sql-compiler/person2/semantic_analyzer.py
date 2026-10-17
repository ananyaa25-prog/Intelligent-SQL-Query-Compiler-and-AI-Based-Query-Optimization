
import sqlite3
from pathlib import Path

import sqlglot
from sqlglot import exp
from sqlglot.optimizer.qualify import qualify


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "university.db"


class SemanticError(Exception):
    """Raised when a query fails semantic validation."""


def get_database_schema(conn):
    """Read actual tables and column types from SQLite."""

    schema = {}

    table_rows = conn.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
    """).fetchall()

    for (table_name,) in table_rows:
        columns = conn.execute(
            f'PRAGMA table_info("{table_name}")'
        ).fetchall()

        schema[table_name] = {
            column[1]: (column[2] or "").upper()
            for column in columns
        }

    return schema


def check_comparison_types(tree, schema):
    """Catch common comparisons between incompatible literal types."""

    numeric_types = ("INTEGER", "REAL", "NUMERIC", "FLOAT", "DOUBLE")
    text_types = ("TEXT", "CHAR", "CLOB", "VARCHAR")

    for node in tree.walk():
        if not isinstance(node, exp.Binary):
            continue

        left = node.this
        right = node.expression

        # This check targets a simple column compared with a literal.
        # It intentionally does not infer complex expression types.
        if isinstance(left, exp.Column) and isinstance(right, exp.Literal):
            column = left
            literal = right
        elif isinstance(right, exp.Column) and isinstance(left, exp.Literal):
            column = right
            literal = left
        else:
            continue

        table_name = column.table
        column_name = column.name

        if table_name:
            column_type = schema.get(table_name, {}).get(column_name)
        else:
            matches = [
                columns[column_name]
                for columns in schema.values()
                if column_name in columns
            ]
            column_type = matches[0] if len(matches) == 1 else None

        if not column_type:
            continue

        is_numeric_column = any(
            kind in column_type for kind in numeric_types
        )
        is_text_column = any(
            kind in column_type for kind in text_types
        )

        # SQLGlot marks quoted strings and numeric literals differently.
        if literal.is_string and is_numeric_column:
            raise SemanticError(
                f"Type mismatch: column '{column_name}' is numeric, "
                "but the query compares it with a string literal."
            )

        if not literal.is_string and is_text_column:
            if isinstance(literal, exp.Literal):
                raise SemanticError(
                    f"Type mismatch: column '{column_name}' is text, "
                    "but the query compares it with a numeric literal."
                )


def validate_sql(sql):
    """Validate a single read-only SELECT query against the database."""

    if not isinstance(sql, str) or not sql.strip():
        return {
            "valid": False,
            "error": "Please provide a non-empty SQL query."
        }

    if not DB_PATH.exists():
        return {
            "valid": False,
            "error": "Database not found. Run 'python database.py' first."
        }

    conn = None

    try:
        # Reject multiple SQL statements.
        statements = sqlglot.parse(sql, read="sqlite")

        if len(statements) != 1 or statements[0] is None:
            raise SemanticError(
                "Please provide exactly one SQL statement."
            )

        tree = statements[0]

        # This module initially supports read-only SELECT queries.
        if not isinstance(tree, exp.Select):
            raise SemanticError(
                "Only SELECT queries are permitted."
            )

        # Open the database in read-only mode.
        conn = sqlite3.connect(
            f"{DB_PATH.as_uri()}?mode=ro",
            uri=True
        )

        schema = get_database_schema(conn)

        # Check referenced tables against the actual database.
        for table in tree.find_all(exp.Table):
            table_name = table.name

            if table_name not in schema:
                raise SemanticError(
                    f"Unknown table '{table_name}'. "
                    f"Available tables: {', '.join(sorted(schema))}."
                )

        # SQLGlot resolves columns, aliases and qualification using
        # the database schema, and raises errors for unresolved columns.
        sqlglot_schema = {
            table: columns
            for table, columns in schema.items()
        }

        qualified_tree = qualify(
            tree.copy(),
            dialect="sqlite",
            schema=sqlglot_schema,
            validate_qualify_columns=True,
        )

        # Check common literal-versus-column type mismatches.
        check_comparison_types(qualified_tree, schema)

        return {
            "valid": True,
            "error": None,
            "message": "Semantic validation successful.",
            "normalized_sql": qualified_tree.sql(dialect="sqlite"),
        }

    except SemanticError as exc:
        return {
            "valid": False,
            "error": str(exc)
        }

    except sqlglot.errors.ParseError as exc:
        return {
            "valid": False,
            "error": f"SQL syntax error: {exc}"
        }

    except (sqlglot.errors.OptimizeError, ValueError) as exc:
        return {
            "valid": False,
            "error": f"Semantic validation failed: {exc}"
        }

    except sqlite3.Error as exc:
        return {
            "valid": False,
            "error": f"Database validation error: {exc}"
        }

    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    test_queries = [
        "SELECT name FROM students;",
        "SELECT salary FROM students;",
        "SELECT * FROM teachers;",
        "SELECT name FROM students WHERE age > 'hello';",
        "SELECT name FROM students WHERE gpa > 8;",
        "SELECT s.name, c.title FROM students s "
        "JOIN enrollments e ON s.student_id = e.student_id "
        "JOIN courses c ON e.course_id = c.course_id;",
        "DELETE FROM students;",
    ]

    for query in test_queries:
        result = validate_sql(query)

        print("\nQuery:", query)
        print("Valid:", result["valid"])

        if result["valid"]:
            print("Normalized SQL:", result["normalized_sql"])
        else:
            print("Error:", result["error"])

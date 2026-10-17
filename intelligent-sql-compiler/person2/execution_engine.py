
import sqlite3
import time
from pathlib import Path

from semantic_analyzer import DB_PATH, validate_sql


MAX_RESULT_ROWS = 500
QUERY_TIMEOUT_SECONDS = 5


def execute_sql(sql):
    """
    Validate and execute one read-only SQL query.

    Returns a dictionary containing success status, columns,
    rows, row count, execution time and an optional error.
    """

    started = time.monotonic()
    conn = None

    try:
        # Phase 1: Semantic validation.
        validation = validate_sql(sql)

        if not validation["valid"]:
            return {
                "success": False,
                "columns": [],
                "rows": [],
                "row_count": 0,
                "truncated": False,
                "execution_time_ms": round(
                    (time.monotonic() - started) * 1000, 3
                ),
                "error": validation["error"],
            }

        # Phase 2: Open the database with read-only access.
        if not DB_PATH.exists():
            raise FileNotFoundError(
                "Database not found. Run 'python database.py' first."
            )

        conn = sqlite3.connect(
            f"{DB_PATH.resolve().as_uri()}?mode=ro",
            uri=True,
            timeout=1.0,
        )

        conn.execute("PRAGMA query_only = ON")

        # Phase 3: Set a deadline for SQLite query processing.
        deadline = time.monotonic() + QUERY_TIMEOUT_SECONDS

        def should_interrupt():
            return 1 if time.monotonic() >= deadline else 0

        conn.set_progress_handler(should_interrupt, 1000)

        # Phase 4: Execute and fetch a bounded number of results.
        cursor = conn.execute(sql)
        columns = [
            description[0] for description in (cursor.description or [])
        ]

        if cursor.description is None:
            raise ValueError(
                "The query did not return a result set."
            )

        fetched = cursor.fetchmany(MAX_RESULT_ROWS + 1)
        truncated = len(fetched) > MAX_RESULT_ROWS
        fetched = fetched[:MAX_RESULT_ROWS]

        rows = [list(row) for row in fetched]

        return {
            "success": True,
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "truncated": truncated,
            "execution_time_ms": round(
                (time.monotonic() - started) * 1000, 3
            ),
            "error": None,
        }

    except FileNotFoundError as exc:
        return {
            "success": False,
            "columns": [],
            "rows": [],
            "row_count": 0,
            "truncated": False,
            "execution_time_ms": round(
                (time.monotonic() - started) * 1000, 3
            ),
            "error": str(exc),
        }

    except sqlite3.OperationalError as exc:
        message = str(exc).lower()

        if "interrupted" in message:
            error = (
                f"Query exceeded the {QUERY_TIMEOUT_SECONDS}-second "
                "execution limit."
            )
        elif "no such table" in message:
            error = "Execution failed: the referenced table does not exist."
        elif "no such column" in message:
            error = "Execution failed: the referenced column does not exist."
        else:
            error = f"SQL execution error: {exc}"

        return {
            "success": False,
            "columns": [],
            "rows": [],
            "row_count": 0,
            "truncated": False,
            "execution_time_ms": round(
                (time.monotonic() - started) * 1000, 3
            ),
            "error": error,
        }

    except (sqlite3.Error, ValueError) as exc:
        return {
            "success": False,
            "columns": [],
            "rows": [],
            "row_count": 0,
            "truncated": False,
            "execution_time_ms": round(
                (time.monotonic() - started) * 1000, 3
            ),
            "error": f"Execution failed: {exc}",
        }

    finally:
        if conn is not None:
            conn.set_progress_handler(None, 0)
            conn.close()


if __name__ == "__main__":
    queries = [
        "SELECT name, gpa FROM students WHERE gpa >= 9.0 LIMIT 5;",
        "SELECT COUNT(*) AS total_students FROM students;",
        "SELECT salary FROM students;",
        "DELETE FROM students;",
    ]

    for query in queries:
        result = execute_sql(query)

        print("\nQuery:", query)
        print("Success:", result["success"])
        print("Columns:", result["columns"])
        print("Rows:", result["rows"])
        print("Row count:", result["row_count"])
        print("Truncated:", result["truncated"])
        print("Time (ms):", result["execution_time_ms"])

        if result["error"]:
            print("Error:", result["error"])

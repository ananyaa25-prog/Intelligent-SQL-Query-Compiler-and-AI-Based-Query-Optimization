
import sqlite3
import statistics
import time

from semantic_analyzer import DB_PATH, validate_sql
from execution_engine import execute_sql


def get_readonly_connection():
    """Open the project database without write permissions."""
    if not DB_PATH.exists():
        raise FileNotFoundError(
            "Database not found. Run 'python database.py' first."
        )

    conn = sqlite3.connect(
        f"{DB_PATH.resolve().as_uri()}?mode=ro",
        uri=True,
        timeout=2.0,
    )
    conn.execute("PRAGMA query_only = ON")
    return conn


def analyze_query(sql):
    """
    Validate a query and inspect its SQLite execution plan.
    Returns structured plan details for the frontend.
    """
    validation = validate_sql(sql)

    if not validation["valid"]:
        return {
            "success": False,
            "sql": sql,
            "plan": [],
            "uses_index": False,
            "has_table_scan": False,
            "uses_temporary_structure": False,
            "error": validation["error"],
        }

    conn = None

    try:
        conn = get_readonly_connection()

        # EXPLAIN QUERY PLAN describes how SQLite intends
        # to execute this SELECT query.
        explain_sql = sql.strip().rstrip(";")
        plan_rows = conn.execute(
            "EXPLAIN QUERY PLAN " + explain_sql
        ).fetchall()

        plan = [
            {
                "id": row[0],
                "parent": row[1],
                "detail": row[3],
            }
            for row in plan_rows
        ]

        details = [
            item["detail"].upper()
            for item in plan
        ]

        uses_index = any(
            "USING INDEX" in detail
            or "USING COVERING INDEX" in detail
            for detail in details
        )

        has_table_scan = any(
            "SCAN " in detail
            and "USING INDEX" not in detail
            and "USING COVERING INDEX" not in detail
            for detail in details
        )

        uses_temporary_structure = any(
            "USE TEMP B-TREE" in detail
            for detail in details
        )

        return {
            "success": True,
            "sql": sql,
            "plan": plan,
            "uses_index": uses_index,
            "has_table_scan": has_table_scan,
            "uses_temporary_structure": uses_temporary_structure,
            "error": None,
        }

    except sqlite3.Error as exc:
        return {
            "success": False,
            "sql": sql,
            "plan": [],
            "uses_index": False,
            "has_table_scan": False,
            "uses_temporary_structure": False,
            "error": f"Plan analysis failed: {exc}",
        }

    finally:
        if conn is not None:
            conn.close()


def benchmark_query(sql, repetitions=7):
    """
    Measure query execution time after semantic validation.

    The first execution warms up the query, and subsequent
    executions are measured. The reported timing excludes
    semantic validation and EXPLAIN analysis.
    """
    if not isinstance(repetitions, int) or not 1 <= repetitions <= 30:
        return {
            "success": False,
            "error": "Repetitions must be an integer from 1 to 30.",
        }

    validation = validate_sql(sql)

    if not validation["valid"]:
        return {
            "success": False,
            "error": validation["error"],
        }

    conn = None

    try:
        conn = get_readonly_connection()
        conn.execute("PRAGMA query_only = ON")

        # Restrict SQLite work during each measured execution.
        deadline = time.monotonic() + 5.0

        def should_interrupt():
            return int(time.monotonic() >= deadline)

        timings = []

        # Warm-up run, not included in the reported samples.
        conn.set_progress_handler(should_interrupt, 1000)
        cursor = conn.execute(sql)
        cursor.fetchall()

        for _ in range(repetitions):
            deadline = time.monotonic() + 5.0
            start = time.perf_counter()

            cursor = conn.execute(sql)
            cursor.fetchall()

            elapsed_ms = (time.perf_counter() - start) * 1000
            timings.append(elapsed_ms)

        return {
            "success": True,
            "repetitions": repetitions,
            "times_ms": [round(t, 3) for t in timings],
            "median_ms": round(statistics.median(timings), 3),
            "minimum_ms": round(min(timings), 3),
            "maximum_ms": round(max(timings), 3),
            "error": None,
        }

    except sqlite3.Error as exc:
        return {
            "success": False,
            "error": f"Benchmark failed: {exc}",
        }

    finally:
        if conn is not None:
            conn.set_progress_handler(None, 0)
            conn.close()


def compare_queries(original_sql, optimized_sql, repetitions=7):
    """
    Compare plans and timing for two equivalent SELECT queries.

    Results are compared as multisets so row ordering does not
    affect equivalence when no ORDER BY is specified.
    """

    original_result = execute_sql(original_sql)
    optimized_result = execute_sql(optimized_sql)

    if not original_result["success"]:
        return {
            "success": False,
            "error": "Original query failed: "
            + str(original_result["error"]),
        }

    if not optimized_result["success"]:
        return {
            "success": False,
            "error": "Optimized query failed: "
            + str(optimized_result["error"]),
        }

    # A truncated result cannot establish full equivalence.
    if original_result["truncated"] or optimized_result["truncated"]:
        return {
            "success": False,
            "error": (
                "Cannot verify equivalence from truncated results. "
                "Use queries returning at most 500 rows for this comparison."
            ),
        }

    # Column order and duplicate row counts must also match.
    from collections import Counter

    same_columns = original_result["columns"] == optimized_result["columns"]
    same_rows = Counter(
        tuple(row) for row in original_result["rows"]
    ) == Counter(
        tuple(row) for row in optimized_result["rows"]
    )

    if not same_columns or not same_rows:
        return {
            "success": False,
            "error": "Queries produced different results. "
            "Performance comparison stopped.",
        }

    original_plan = analyze_query(original_sql)
    optimized_plan = analyze_query(optimized_sql)

    original_benchmark = benchmark_query(
        original_sql, repetitions
    )
    optimized_benchmark = benchmark_query(
        optimized_sql, repetitions
    )

    if not original_benchmark["success"]:
        return {
            "success": False,
            "error": original_benchmark["error"],
        }

    if not optimized_benchmark["success"]:
        return {
            "success": False,
            "error": optimized_benchmark["error"],
        }

    before = original_benchmark["median_ms"]
    after = optimized_benchmark["median_ms"]

    improvement_percent = (
        ((before - after) / before * 100)
        if before > 0
        else None
    )

    return {
        "success": True,
        "results_equivalent": True,
        "original_plan": original_plan,
        "optimized_plan": optimized_plan,
        "original_benchmark": original_benchmark,
        "optimized_benchmark": optimized_benchmark,
        "improvement_percent": (
            round(improvement_percent, 2)
            if improvement_percent is not None
            else None
        ),
    }


if __name__ == "__main__":
    test_queries = [
        (
            "Indexed department filter",
            "SELECT student_id, name FROM students "
            "WHERE department = 'Data Science'",
        ),
        (
            "Unindexed age filter",
            "SELECT student_id, name FROM students "
            "WHERE age = 21",
        ),
        (
            "Indexed GPA filter",
            "SELECT student_id, name FROM students "
            "WHERE gpa >= 9.0",
        ),
    ]

    for title, sql in test_queries:
        result = analyze_query(sql)

        print("\n" + "=" * 60)
        print(title)
        print("SQL:", sql)

        if not result["success"]:
            print("Error:", result["error"])
            continue

        for step in result["plan"]:
            print(f"Plan step {step['id']}: {step['detail']}")

        print("Uses index:", result["uses_index"])
        print("Has table scan:", result["has_table_scan"])
        print(
            "Uses temporary structure:",
            result["uses_temporary_structure"],
        )

        timing = benchmark_query(sql)

        if timing["success"]:
            print("Median execution time (ms):", timing["median_ms"])


from evaluation import compare_queries


original_sql = """
SELECT student_id, name
FROM students
WHERE gpa >= 9.0 AND gpa >= 8.0
"""

optimized_sql = """
SELECT student_id, name
FROM students
WHERE gpa >= 9.0
"""


def main():
    report = compare_queries(
        original_sql,
        optimized_sql,
        repetitions=7,
    )

    if not report["success"]:
        print("Evaluation failed:", report["error"])
        return

    before = report["original_benchmark"]
    after = report["optimized_benchmark"]

    print("=" * 55)
    print("SQL OPTIMIZATION EVALUATION")
    print("=" * 55)

    print("\nORIGINAL SQL:")
    print(original_sql.strip())

    print("\nOPTIMIZED SQL:")
    print(optimized_sql.strip())

    print("\nRESULT CORRECTNESS")
    print("Equivalent results:", report["results_equivalent"])

    print("\nPERFORMANCE")
    print(f"Original median:  {before['median_ms']} ms")
    print(f"Optimized median: {after['median_ms']} ms")

    improvement = report["improvement_percent"]

    if improvement is None:
        print("Improvement: unavailable")
    else:
        print(f"Measured improvement: {improvement:.2f}%")

    if before["median_ms"] > 0:
        speedup = before["median_ms"] / after["median_ms"]
        print(f"Speedup: {speedup:.3f}x")

    print("\nORIGINAL EXECUTION PLAN")
    for step in report["original_plan"]["plan"]:
        print("-", step["detail"])

    print("\nOPTIMIZED EXECUTION PLAN")
    for step in report["optimized_plan"]["plan"]:
        print("-", step["detail"])

    print("\nINTERPRETATION")
    print(
        "The rewrite removed a redundant condition. "
        "Equivalent results are required for correctness."
    )
    print(
        "Compare the measured times and plans; the rewrite "
        "may not improve performance if SQLite already simplifies "
        "the original query."
    )


if __name__ == "__main__":
    main()

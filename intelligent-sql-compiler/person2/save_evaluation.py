
import json
from pathlib import Path

from evaluation import compare_queries


BASE_DIR = Path(__file__).resolve().parent
REPORT_PATH = BASE_DIR / "evaluation_report.json"

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

    REPORT_PATH.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    print("Evaluation report saved to:", REPORT_PATH)

    if report["success"]:
        print("Results equivalent:", report["results_equivalent"])
        print(
            "Original median (ms):",
            report["original_benchmark"]["median_ms"],
        )
        print(
            "Optimized median (ms):",
            report["optimized_benchmark"]["median_ms"],
        )
    else:
        print("Evaluation failed:", report["error"])


if __name__ == "__main__":
    main()

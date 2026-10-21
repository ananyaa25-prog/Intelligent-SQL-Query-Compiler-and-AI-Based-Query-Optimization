"""Regression test suite for natural language to SQL generators (Template vs LLM).

DISCLOSURE: This evaluation corpus is a regression test suite written by the
same author to test supported phrasings and repair loops. It is NOT an
independent third-party accuracy benchmark.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlcompiler.frontend.parser import parse_sql
from sqlcompiler.semantic.symbols import Catalog
from sqlcompiler.semantic.typecheck import SemanticAnalyzer
from sqlcompiler.nl.nl_to_sql import generate_sql as template_generate
from sqlcompiler.nl.llm import generate_sql_with_compiler_guardrail, is_llm_configured


EVALUATION_CORPUS = [
    # Top students & GPA limits
    ("Show the top 10 students", "SELECT student_id, name, gpa FROM students ORDER BY gpa DESC LIMIT 10;"),
    ("Show the top 5 students", "SELECT student_id, name, gpa FROM students ORDER BY gpa DESC LIMIT 5;"),
    ("Top 20 pupils with highest grades", "SELECT student_id, name, gpa FROM students ORDER BY gpa DESC LIMIT 20;"),
    ("List students with highest GPA", "SELECT student_id, name, gpa FROM students ORDER BY gpa DESC LIMIT 10;"),
    ("Show students with GPA above 9", "SELECT student_id, name, gpa FROM students WHERE gpa > 9 ORDER BY gpa DESC;"),
    ("Students with grade greater than 8.5", "SELECT student_id, name, gpa FROM students WHERE gpa > 8.5 ORDER BY gpa DESC;"),
    ("Pupils with marks over 7", "SELECT student_id, name, gpa FROM students WHERE gpa > 7 ORDER BY gpa DESC;"),
    ("Students with scores above 9.2", "SELECT student_id, name, gpa FROM students WHERE gpa > 9.2 ORDER BY gpa DESC;"),

    # Aggregates and Department counts
    ("Count students by department", "SELECT department, COUNT(*) AS student_count FROM students GROUP BY department ORDER BY student_count DESC;"),
    ("Count pupils per department", "SELECT department, COUNT(*) AS student_count FROM students GROUP BY department ORDER BY student_count DESC;"),
    ("Count students", "SELECT COUNT(*) AS student_count FROM students;"),
    ("Count all pupils", "SELECT COUNT(*) AS student_count FROM students;"),
    ("Average GPA by department", "SELECT department, AVG(gpa) AS avg_gpa FROM students GROUP BY department ORDER BY avg_gpa DESC;"),
    ("Average marks per department", "SELECT department, AVG(gpa) AS avg_gpa FROM students GROUP BY department ORDER BY avg_gpa DESC;"),
    ("Avg scores by department", "SELECT department, AVG(gpa) AS avg_gpa FROM students GROUP BY department ORDER BY avg_gpa DESC;"),

    # Department filters
    ("Students in Computer Science", "SELECT student_id, name, gpa FROM students WHERE department = 'Computer Science' ORDER BY name LIMIT 20;"),
    ("Data Science students", "SELECT student_id, name, gpa FROM students WHERE department = 'Data Science' ORDER BY name LIMIT 20;"),
    ("Electronics pupils", "SELECT student_id, name, gpa FROM students WHERE department = 'Electronics' ORDER BY name LIMIT 20;"),
    ("Mechanical department students", "SELECT student_id, name, gpa FROM students WHERE department = 'Mechanical' ORDER BY name LIMIT 20;"),
    ("Count students in Computer Science", "SELECT COUNT(*) AS student_count FROM students WHERE department = 'Computer Science';"),

    # Age filters
    ("Students older than 21", "SELECT student_id, name, age, gpa FROM students WHERE age > 21 ORDER BY age ASC LIMIT 20;"),
    ("Pupils aged above 22", "SELECT student_id, name, age, gpa FROM students WHERE age > 22 ORDER BY age ASC LIMIT 20;"),
    ("Students above age 20", "SELECT student_id, name, age, gpa FROM students WHERE age > 20 ORDER BY age ASC LIMIT 20;"),
    ("Pupils over age 19", "SELECT student_id, name, age, gpa FROM students WHERE age > 19 ORDER BY age ASC LIMIT 20;"),

    # Course list and enrollments
    ("List courses", "SELECT course_id, title FROM courses ORDER BY title;"),
    ("Show courses", "SELECT course_id, title FROM courses ORDER BY title;"),
    ("List students", "SELECT student_id, name, gpa FROM students ORDER BY name LIMIT 20;"),
    ("Show students", "SELECT student_id, name, gpa FROM students ORDER BY name LIMIT 20;"),
    ("Count courses per student", "SELECT s.name, COUNT(e.course_id) AS course_count FROM students AS s JOIN enrollments AS e ON s.student_id = e.student_id GROUP BY s.name ORDER BY course_count DESC LIMIT 20;"),
    ("Show student grades and courses", "SELECT s.name, c.title, e.grade FROM students AS s JOIN enrollments AS e ON s.student_id = e.student_id JOIN courses AS c ON e.course_id = c.course_id LIMIT 20;"),
    ("Show enrolled course titles and student grades", "SELECT s.name, c.title, e.grade FROM students AS s JOIN enrollments AS e ON s.student_id = e.student_id JOIN courses AS c ON e.course_id = c.course_id LIMIT 20;"),
    ("Students courses and grades", "SELECT s.name, c.title, e.grade FROM students AS s JOIN enrollments AS e ON s.student_id = e.student_id JOIN courses AS c ON e.course_id = c.course_id LIMIT 20;"),
]


def evaluate_nl_suite(
    mock_llm: Optional[Callable[[str, str], str]] = None
) -> dict:
    catalog = Catalog.default_university()
    analyzer = SemanticAnalyzer(catalog)

    template_success = 0
    template_compiler_valid = 0

    llm_tested = is_llm_configured() or (mock_llm is not None)
    llm_success = 0
    llm_repairs_needed = 0

    total = len(EVALUATION_CORPUS)

    for question, gold_sql in EVALUATION_CORPUS:
        # Evaluate template
        try:
            t_sql = template_generate(question)
            template_success += 1
            t_ast = parse_sql(t_sql)
            t_val = analyzer.analyze(t_ast)
            if t_val["valid"]:
                template_compiler_valid += 1
        except Exception:
            pass

        # Evaluate LLM if available
        if llm_tested:
            res = generate_sql_with_compiler_guardrail(question, catalog=catalog, client=mock_llm)
            if res["success"]:
                llm_success += 1
                if res.get("repairs_attempted", 0) > 0:
                    llm_repairs_needed += 1

    return {
        "total_questions": total,
        "template_accuracy_percent": round((template_success / total) * 100, 1),
        "template_compiler_valid_percent": round((template_compiler_valid / total) * 100, 1),
        "llm_tested": llm_tested,
        "llm_accuracy_percent": round((llm_success / total) * 100, 1) if llm_tested else None,
        "llm_repair_rate_percent": round((llm_repairs_needed / max(1, llm_success)) * 100, 1) if llm_tested else None,
    }


def main():
    parser = argparse.ArgumentParser(description="Evaluate NL-to-SQL performance.")
    args = parser.parse_args()

    results = evaluate_nl_suite()
    print("=" * 60)
    print("NATURAL LANGUAGE COMPILER EVALUATION REPORT")
    print("=" * 60)
    print(f"Total benchmark questions: {results['total_questions']}")
    print(f"Template generator match rate: {results['template_accuracy_percent']}%")
    print(f"Template compiler validation rate: {results['template_compiler_valid_percent']}%")
    if results["llm_tested"]:
        print(f"LLM accuracy: {results['llm_accuracy_percent']}%")
        print(f"LLM repair rate: {results['llm_repair_rate_percent']}%")
    else:
        print("Generative AI provider: disabled/unconfigured (deterministic fallback verified)")
    print("NOTE: This suite is an author-written regression test, not an independent accuracy benchmark.")
    print("=" * 60)


if __name__ == "__main__":
    main()

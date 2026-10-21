"""Layer B: Randomized differential testing using ephemeral in-memory SQLite databases."""

from __future__ import annotations

import random
import re
import sqlite3
from typing import Any, Optional

from sqlcompiler.frontend.parser import parse_sql


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS students (
    student_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    department TEXT NOT NULL,
    age INTEGER NOT NULL CHECK (age BETWEEN 16 AND 100),
    gpa REAL NOT NULL CHECK (gpa BETWEEN 0.0 AND 10.0)
);

CREATE TABLE IF NOT EXISTS courses (
    course_id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    department TEXT NOT NULL,
    credits INTEGER NOT NULL CHECK (credits BETWEEN 1 AND 6)
);

CREATE TABLE IF NOT EXISTS enrollments (
    enrollment_id INTEGER PRIMARY KEY,
    student_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL,
    grade TEXT,
    FOREIGN KEY (student_id) REFERENCES students(student_id),
    FOREIGN KEY (course_id) REFERENCES courses(course_id),
    UNIQUE (student_id, course_id),
    CHECK (grade IS NULL OR grade IN ('S', 'A', 'B', 'C', 'D', 'F'))
);
"""

DEPARTMENTS = ["Computer Science", "Data Science", "Electronics", "Mechanical"]
GRADES = ["S", "A", "B", "C", "D", "F", None]


def extract_numeric_constants(sql: str) -> list[float]:
    """Extract numeric literals from SQL to generate targeted boundary test cases."""
    found = re.findall(r"\b\d+(?:\.\d+)?\b", sql)
    nums = []
    for s in found:
        try:
            nums.append(float(s))
        except ValueError:
            pass
    return nums


def generate_random_db(seed: int, target_nums: Optional[list[float]] = None) -> sqlite3.Connection:
    """Create an in-memory SQLite database populated with randomized, edge-case data."""
    rng = random.Random(seed)
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_SQL)

    # Edge cases: 0 rows, 1 row, boundary numbers
    num_students = rng.choice([0, 1, 2, 5, 10, 20])
    num_courses = rng.choice([0, 1, 3, 5]) if num_students > 0 else 0

    # Base candidate GPAs
    gpa_pool = [0.0, 4.0, 5.0, 7.5, 8.0, 8.5, 9.0, 9.5, 10.0]
    if target_nums:
        for n in target_nums:
            if 0.0 <= n <= 10.0:
                gpa_pool.extend([n, max(0.0, n - 0.01), min(10.0, n + 0.01)])

    age_pool = [16, 18, 20, 21, 22, 25, 30, 100]
    if target_nums:
        for n in target_nums:
            if 16 <= int(n) <= 100:
                age_pool.extend([int(n), max(16, int(n) - 1), min(100, int(n) + 1)])

    # Insert students
    students_data = []
    for sid in range(1, num_students + 1):
        name = f"Student {sid}"
        email = f"student{sid}_{seed}@example.com"
        dept = rng.choice(DEPARTMENTS)
        age = rng.choice(age_pool)
        gpa = round(rng.choice(gpa_pool), 2)
        students_data.append((sid, name, email, dept, age, gpa))

    if students_data:
        conn.executemany(
            "INSERT INTO students (student_id, name, email, department, age, gpa) VALUES (?, ?, ?, ?, ?, ?)",
            students_data
        )

    # Insert courses
    courses_data = []
    for cid in range(1, num_courses + 1):
        title = f"Course {cid}"
        dept = rng.choice(DEPARTMENTS)
        credits = rng.randint(1, 6)
        courses_data.append((cid, title, dept, credits))

    if courses_data:
        conn.executemany(
            "INSERT INTO courses (course_id, title, department, credits) VALUES (?, ?, ?, ?)",
            courses_data
        )

    # Insert enrollments
    enrollments_data = []
    eid = 1
    if num_students > 0 and num_courses > 0:
        for sid in range(1, num_students + 1):
            sample_size = rng.randint(0, min(3, num_courses))
            c_ids = rng.sample(range(1, num_courses + 1), sample_size)
            for cid in c_ids:
                grade = rng.choice(GRADES)
                enrollments_data.append((eid, sid, cid, grade))
                eid += 1

    if enrollments_data:
        conn.executemany(
            "INSERT INTO enrollments (enrollment_id, student_id, course_id, grade) VALUES (?, ?, ?, ?)",
            enrollments_data
        )

    conn.commit()
    return conn


DEFAULT_NUM_DATABASES: int = 50


def differential_test(
    original_sql: str,
    candidate_sql: str,
    num_databases: int = DEFAULT_NUM_DATABASES,
    seed: int = 42
) -> dict[str, Any]:
    """
    Run original and candidate on N in-memory random databases with edge-case data.
    Returns equivalence result and the first counterexample if a difference is found.
    """
    from collections import Counter

    # Determine if ordering is required
    try:
        orig_ast = parse_sql(original_sql)
        cand_ast = parse_sql(candidate_sql)
        ordered = bool(orig_ast.order_by) or bool(cand_ast.order_by)
    except Exception:
        ordered = "ORDER BY" in original_sql.upper() or "ORDER BY" in candidate_sql.upper()

    target_nums = list(set(extract_numeric_constants(original_sql) + extract_numeric_constants(candidate_sql)))

    for i in range(num_databases):
        db_seed = seed + i * 1009
        conn = generate_random_db(db_seed, target_nums)
        try:
            conn.execute("PRAGMA query_only = ON")

            # Execute original
            cur1 = conn.execute(original_sql)
            cols1 = [d[0] for d in cur1.description or []]
            rows1 = cur1.fetchall()

            # Execute candidate
            cur2 = conn.execute(candidate_sql)
            cols2 = [d[0] for d in cur2.description or []]
            rows2 = cur2.fetchall()

            cols_match = (cols1 == cols2)
            if ordered:
                rows_match = (rows1 == rows2)
            else:
                rows_match = (Counter(rows1) == Counter(rows2))

            if not cols_match or not rows_match:
                # Capture database summary
                s_count = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
                return {
                    "equivalent": False,
                    "layer": "Layer B",
                    "seed": seed,
                    "failing_db_index": i,
                    "failing_db_seed": db_seed,
                    "num_databases_tested": i + 1,
                    "counterexample": {
                        "db_summary": f"{s_count} students in random test database #{i}",
                        "original_columns": cols1,
                        "candidate_columns": cols2,
                        "original_rows": rows1[:10],
                        "candidate_rows": rows2[:10],
                        "original_row_count": len(rows1),
                        "candidate_row_count": len(rows2),
                    },
                    "message": f"Difference observed on random database #{i} (seed {db_seed}).",
                }
        finally:
            conn.close()

    return {
        "equivalent": True,
        "layer": "Layer B",
        "seed": seed,
        "num_databases": num_databases,
        "num_databases_tested": num_databases,
        "counterexample": None,
        "message": f"{num_databases} random in-memory databases checked; no difference found.",
    }

"""Generate a larger synthetic SQLite database for realistic performance benchmarking.

Does NOT overwrite university.db. Generates to a separate file (e.g. large_university.db).
"""

from __future__ import annotations

import argparse
import random
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCHEMA_PATH = ROOT / "person2" / "schema.sql"


DEPARTMENTS = [
    "Computer Science",
    "Data Science",
    "Electronics",
    "Mechanical",
    "Electrical",
]

COURSES = [
    ("Database Systems", "Computer Science", 4),
    ("Compiler Design", "Computer Science", 4),
    ("Machine Learning", "Data Science", 4),
    ("Statistics", "Data Science", 3),
    ("Digital Systems", "Electronics", 3),
    ("Computer Networks", "Computer Science", 3),
    ("Operating Systems", "Computer Science", 4),
    ("Thermodynamics", "Mechanical", 3),
    ("Circuit Theory", "Electrical", 3),
    ("Algorithms", "Computer Science", 4),
    ("Cloud Computing", "Computer Science", 3),
    ("Natural Language Processing", "Data Science", 4),
    ("Computer Architecture", "Electronics", 4),
    ("Robotics", "Mechanical", 3),
    ("Power Systems", "Electrical", 3),
]

GRADES = ["S", "A", "B", "C", "D", "F", None]


def create_large_database(
    output_path: Path,
    num_students: int = 200000,
    seed: int = 42,
    batch_size: int = 10000
) -> None:
    print(f"Creating large database at: {output_path}")
    print(f"Target students: {num_students:,}")

    if output_path.exists():
        output_path.unlink()

    start_time = time.monotonic()
    rng = random.Random(seed)

    with sqlite3.connect(output_path) as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA foreign_keys = ON")

        # Load schema
        schema = SCHEMA_PATH.read_text(encoding="utf-8")
        conn.executescript(schema)

        # 1. Insert courses
        conn.executemany(
            "INSERT INTO courses (course_id, title, department, credits) VALUES (?, ?, ?, ?)",
            [(i + 1, title, dept, cr) for i, (title, dept, cr) in enumerate(COURSES)]
        )
        print(f"Inserted {len(COURSES)} courses.")

        # 2. Insert students in batches
        print("Inserting students...")
        students_inserted = 0
        while students_inserted < num_students:
            chunk_size = min(batch_size, num_students - students_inserted)
            chunk = []
            for i in range(chunk_size):
                sid = students_inserted + i + 1
                dept = rng.choice(DEPARTMENTS)
                age = rng.randint(18, 30)
                gpa = round(rng.uniform(4.0, 10.0), 2)
                chunk.append((sid, f"Student {sid}", f"student{sid}@large.edu", dept, age, gpa))

            conn.executemany(
                "INSERT INTO students (student_id, name, email, department, age, gpa) VALUES (?, ?, ?, ?, ?, ?)",
                chunk
            )
            students_inserted += chunk_size
            if students_inserted % 50000 == 0 or students_inserted == num_students:
                print(f"  Inserted {students_inserted:,} / {num_students:,} students...")

        # 3. Insert enrollments (approx 3 courses per student)
        print("Inserting enrollments...")
        enrollments_inserted = 0
        eid = 1
        num_courses = len(COURSES)

        for sid in range(1, num_students + 1, batch_size):
            end_sid = min(num_students + 1, sid + batch_size)
            chunk = []
            for cur_sid in range(sid, end_sid):
                chosen_courses = rng.sample(range(1, num_courses + 1), 3)
                for cid in chosen_courses:
                    grade = rng.choice(GRADES)
                    chunk.append((eid, cur_sid, cid, grade))
                    eid += 1
            conn.executemany(
                "INSERT INTO enrollments (enrollment_id, student_id, course_id, grade) VALUES (?, ?, ?, ?)",
                chunk
            )
            enrollments_inserted += len(chunk)
            if enrollments_inserted % 150000 == 0 or eid >= (num_students * 3):
                print(f"  Inserted {enrollments_inserted:,} enrollments...")

        print("Analyzing query planner statistics (ANALYZE)...")
        conn.execute("ANALYZE")

    elapsed = time.monotonic() - start_time
    size_mb = output_path.stat().st_size / (1024 * 1024)
    print(f"Done in {elapsed:.2f}s! Final size: {size_mb:.2f} MB")


def main():
    parser = argparse.ArgumentParser(description="Generate large benchmark SQLite database.")
    parser.add_argument("--students", type=int, default=200000, help="Number of students (default 200000)")
    parser.add_argument("--output", type=str, default="person2/large_university.db", help="Output SQLite database path")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed")
    args = parser.parse_args()

    out = Path(args.output)
    create_large_database(out, num_students=args.students, seed=args.seed)


if __name__ == "__main__":
    main()

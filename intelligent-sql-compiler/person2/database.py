
import random
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "university.db"
SCHEMA_PATH = BASE_DIR / "schema.sql"

DEPARTMENTS = [
    "Computer Science",
    "Data Science",
    "Electronics",
    "Mechanical",
    "Electrical",
]

COURSE_NAMES = [
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
]

GRADES = ["S", "A", "B", "C", "D", "F"]


def create_database():
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"Schema not found: {SCHEMA_PATH}")

    random.seed(42)

    # This script rebuilds the sample database from scratch.
    # Close any application currently using university.db first.
    if DB_PATH.exists():
        DB_PATH.unlink()

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")

        schema = SCHEMA_PATH.read_text(encoding="utf-8")
        conn.executescript(schema)

        # Insert courses.
        conn.executemany(
            """
            INSERT INTO courses (course_id, title, department, credits)
            VALUES (?, ?, ?, ?)
            """,
            [
                (i + 1, title, dept, credits)
                for i, (title, dept, credits) in enumerate(COURSE_NAMES)
            ],
        )

        # Insert 1,000 students.
        students = []
        for student_id in range(1, 1001):
            department = random.choice(DEPARTMENTS)
            students.append(
                (
                    student_id,
                    f"Student {student_id}",
                    f"student{student_id}@example.com",
                    department,
                    random.randint(18, 25),
                    round(random.uniform(4.0, 10.0), 2),
                )
            )

        conn.executemany(
            """
            INSERT INTO students
                (student_id, name, email, department, age, gpa)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            students,
        )

        # Enroll each student in three distinct courses.
        enrollments = []
        enrollment_id = 1

        for student_id in range(1, 1001):
            course_ids = random.sample(range(1, 11), 3)

            for course_id in course_ids:
                enrollments.append(
                    (
                        enrollment_id,
                        student_id,
                        course_id,
                        random.choice(GRADES),
                    )
                )
                enrollment_id += 1

        conn.executemany(
            """
            INSERT INTO enrollments
                (enrollment_id, student_id, course_id, grade)
            VALUES (?, ?, ?, ?)
            """,
            enrollments,
        )

        # Gather statistics for the SQLite query planner.
        conn.execute("ANALYZE")

        student_count = conn.execute(
            "SELECT COUNT(*) FROM students"
        ).fetchone()[0]

        course_count = conn.execute(
            "SELECT COUNT(*) FROM courses"
        ).fetchone()[0]

        enrollment_count = conn.execute(
            "SELECT COUNT(*) FROM enrollments"
        ).fetchone()[0]

        print("Database created successfully!")
        print(f"Location: {DB_PATH}")
        print(f"Students: {student_count}")
        print(f"Courses: {course_count}")
        print(f"Enrollments: {enrollment_count}")


def main():
    create_database()


if __name__ == "__main__":
    main()

"""Enhanced deterministic pattern-matching NL-to-SQL generator."""

from __future__ import annotations

import re


def generate_sql(question: str) -> str:
    """
    Convert supported English requests into SQL using deterministic pattern matching.
    Includes synonyms and schema lexicon while remaining 100% deterministic (no AI required).
    """
    if not question or not question.strip():
        raise ValueError("Please enter a natural-language request.")

    text = question.lower().strip()
    text = re.sub(r"[?.!]+$", "", text)

    # 1. 3-table join: students + courses + grades
    if (
        ("course" in text and "grade" in text)
        or ("enroll" in text and ("course" in text or "title" in text or "student" in text))
    ):
        return (
            "SELECT s.name, c.title, e.grade "
            "FROM students AS s "
            "JOIN enrollments AS e ON s.student_id = e.student_id "
            "JOIN courses AS c ON e.course_id = c.course_id "
            "LIMIT 20;"
        )

    # Lexicon normalization for synonyms
    normalized = text
    normalized = re.sub(r"\bpupils?\b", "students", normalized)
    normalized = re.sub(r"\bmarks?\b|\bscores?\b", "gpa", normalized)


    # 2. Average GPA by department
    if ("average" in normalized or "avg" in normalized) and "department" in normalized:
        return (
            "SELECT department, AVG(gpa) AS avg_gpa "
            "FROM students "
            "GROUP BY department "
            "ORDER BY avg_gpa DESC;"
        )

    # 3. Courses taken per student
    if "courses per student" in normalized or ("count" in normalized and "course" in normalized and "student" in normalized):
        return (
            "SELECT s.name, COUNT(e.course_id) AS course_count "
            "FROM students AS s "
            "JOIN enrollments AS e ON s.student_id = e.student_id "
            "GROUP BY s.name "
            "ORDER BY course_count DESC "
            "LIMIT 20;"
        )

    # 4. Department filter (e.g. "students in Computer Science" or "Data Science students")
    for dept in ["computer science", "data science", "electronics", "mechanical", "electrical"]:
        if dept in normalized:
            capitalized = " ".join(w.capitalize() for w in dept.split())
            if "count" in normalized:
                return (
                    f"SELECT COUNT(*) AS student_count FROM students "
                    f"WHERE department = '{capitalized}';"
                )
            return (
                f"SELECT student_id, name, gpa FROM students "
                f"WHERE department = '{capitalized}' "
                f"ORDER BY name LIMIT 20;"
            )

    # 5. Age filter (e.g. "students older than 21", "students above age 20")
    age_match = re.search(r"(?:age|aged|older than)\s+(?:above|greater than|over|>)?\s*(\d+)", normalized)
    if age_match:
        age_val = int(age_match.group(1))
        if 16 <= age_val <= 100:
            return (
                "SELECT student_id, name, age, gpa "
                "FROM students "
                f"WHERE age > {age_val} "
                "ORDER BY age ASC LIMIT 20;"
            )

    # 6. Show students with the highest GPA (top N)
    if (
        "highest gpa" in normalized
        or re.search(r"\btop\s+\d+\s+students?\b", normalized)
        or "top students" in normalized
        or "highest grades" in normalized
    ):
        match = re.search(r"\btop\s+(\d+)\b", normalized)
        limit = int(match.group(1)) if match else 10

        if not 1 <= limit <= 100:
            raise ValueError("Please choose a limit between 1 and 100.")

        return (
            "SELECT student_id, name, gpa "
            "FROM students ORDER BY gpa DESC "
            f"LIMIT {limit};"
        )

    # 7. Students above a specified GPA threshold
    match = re.search(
        r"(?:gpa|grade)\s+(?:above|greater than|over|>=|>)\s*(\d+(?:\.\d+)?)",
        normalized,
    )
    if match:
        gpa = float(match.group(1))
        if not 0 <= gpa <= 10:
            raise ValueError("GPA must be between 0 and 10.")

        return (
            "SELECT student_id, name, gpa FROM students "
            f"WHERE gpa > {gpa:g} ORDER BY gpa DESC;"
        )

    # 8. Count students
    if "count" in normalized and "student" in normalized:
        if "department" in normalized:
            return (
                "SELECT department, COUNT(*) AS student_count "
                "FROM students GROUP BY department "
                "ORDER BY student_count DESC;"
            )
        return "SELECT COUNT(*) AS student_count FROM students;"

    # 9. List students
    if "list students" in normalized or "show students" in normalized:
        return (
            "SELECT student_id, name, gpa FROM students "
            "ORDER BY name LIMIT 20;"
        )

    # 10. List courses
    if "list courses" in normalized or "show courses" in normalized:
        return "SELECT course_id, title FROM courses ORDER BY title;"

    raise ValueError(
        "I couldn't match that request. Try: "
        "'Show the top 10 students', "
        "'Show students with GPA above 9', "
        "'Count students by department', "
        "'Average GPA by department', "
        "'Students in Computer Science', or "
        "'List courses'."
    )

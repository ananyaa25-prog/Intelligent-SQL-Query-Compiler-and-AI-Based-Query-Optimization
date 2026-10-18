
import re


def generate_sql(question: str) -> str:
    """Convert supported English requests into SQL."""

    if not question or not question.strip():
        raise ValueError("Please enter a natural-language request.")

    text = question.lower().strip()
    text = re.sub(r"[?.!]+$", "", text)

    # Show students with the highest GPA
    if (
    "highest gpa" in text
    or re.search(r"\btop\s+\d+\s+students?\b", text)
    or "top students" in text
    or "highest grades" in text
):
        match = re.search(r"\btop\s+(\d+)\b", text)
        limit = int(match.group(1)) if match else 10

        if not 1 <= limit <= 100:
            raise ValueError("Please choose a limit between 1 and 100.")

        return (
            "SELECT student_id, name, gpa "
            "FROM students ORDER BY gpa DESC "
            f"LIMIT {limit};"
        )

    # Students above a specified GPA
    match = re.search(
        r"(?:gpa|grade)\s+(?:above|greater than|over)\s+(\d+(?:\.\d+)?)",
        text,
    )
    if match:
        gpa = float(match.group(1))
        if not 0 <= gpa <= 10:
            raise ValueError("GPA must be between 0 and 10.")

        return (
            "SELECT student_id, name, gpa FROM students "
            f"WHERE gpa > {gpa:g} ORDER BY gpa DESC;"
        )

    # Count students
    if "count" in text and "student" in text:
        if "department" in text:
            return (
                "SELECT department, COUNT(*) AS student_count "
                "FROM students GROUP BY department "
                "ORDER BY student_count DESC;"
            )

        return "SELECT COUNT(*) AS student_count FROM students;"

    # List students
    if "list students" in text or "show students" in text:
        return (
            "SELECT student_id, name, gpa FROM students "
            "ORDER BY name LIMIT 20;"
        )

    # List courses
    if "list courses" in text or "show courses" in text:
        return "SELECT course_id, title FROM courses ORDER BY title;"

    raise ValueError(
        "I couldn't match that request. Try: "
        "'Show the top 10 students', "
        "'Show students with GPA above 9', "
        "'Count students by department', or "
        "'List courses'."
    )


if __name__ == "__main__":
    examples = [
        "Show the top 10 students",
        "Show students with GPA above 9",
        "Count students by department",
        "List courses",
    ]

    for question in examples:
        print(f"\nRequest: {question}")
        print(f"SQL: {generate_sql(question)}")

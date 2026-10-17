
from semantic_analyzer import validate_sql
from execution_engine import execute_sql
from evaluation import analyze_query, compare_queries


def test_unknown_table():
    result = validate_sql("SELECT * FROM teachers")
    assert result["valid"] is False


def test_unknown_column():
    result = validate_sql("SELECT salary FROM students")
    assert result["valid"] is False


def test_invalid_alias():
    result = validate_sql(
        "SELECT s.name FROM students AS x"
    )
    assert result["valid"] is False


def test_ambiguous_column():
    result = validate_sql(
        """
        SELECT student_id
        FROM students AS s
        JOIN enrollments AS e
        ON s.student_id = e.student_id
        """
    )
    assert result["valid"] is False


def test_valid_qualified_join():
    result = validate_sql(
        """
        SELECT s.name, e.grade
        FROM students AS s
        JOIN enrollments AS e
        ON s.student_id = e.student_id
        LIMIT 5
        """
    )
    assert result["valid"] is True


def test_multiple_statements_rejected():
    result = execute_sql(
        "SELECT name FROM students; SELECT title FROM courses"
    )
    assert result["success"] is False


def test_delete_rejected():
    result = execute_sql("DELETE FROM students")
    assert result["success"] is False


def test_large_results_are_bounded():
    result = execute_sql("SELECT * FROM students")

    assert result["success"] is True
    assert len(result["rows"]) <= 500
    assert result["truncated"] is True


def test_plan_analysis_rejects_invalid_query():
    result = analyze_query("SELECT salary FROM students")
    assert result["success"] is False


def test_different_results_not_compared_as_equivalent():
    result = compare_queries(
        "SELECT student_id FROM students WHERE student_id <= 5",
        "SELECT student_id FROM students WHERE student_id <= 3",
        repetitions=3,
    )
    assert result["success"] is False
    assert "different results" in result["error"].lower()


from execution_engine import execute_sql


def test_valid_select():
    result = execute_sql(
        "SELECT name FROM students LIMIT 3"
    )
    assert result["success"] is True
    assert len(result["rows"]) == 3


def test_aggregate_query():
    result = execute_sql(
        "SELECT COUNT(*) AS total FROM students"
    )
    assert result["success"] is True
    assert result["rows"][0][0] == 1000


def test_unknown_column():
    result = execute_sql(
        "SELECT salary FROM students"
    )
    assert result["success"] is False
    assert result["error"] is not None


def test_delete_rejected():
    result = execute_sql(
        "DELETE FROM students"
    )
    assert result["success"] is False


def test_multiple_statements_rejected():
    result = execute_sql(
        "SELECT name FROM students; SELECT * FROM courses"
    )
    assert result["success"] is False

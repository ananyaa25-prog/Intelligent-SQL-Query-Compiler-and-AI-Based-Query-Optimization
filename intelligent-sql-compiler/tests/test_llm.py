"""Tests for LLM-based NL-to-SQL module, compiler guardrails, and repair loops using mock clients."""

import pytest

from sqlcompiler.nl.llm import (
    generate_sql_with_compiler_guardrail,
    strip_code_fences,
    is_llm_configured,
)


def test_strip_code_fences():
    text = "```sql\nSELECT * FROM students;\n```"
    assert strip_code_fences(text) == "SELECT * FROM students;"

    text2 = "SELECT name FROM students"
    assert strip_code_fences(text2) == "SELECT name FROM students"


def test_mock_llm_first_attempt_success():
    def mock_client(system: str, user: str) -> str:
        return "SELECT student_id, name, gpa FROM students WHERE gpa >= 9.0;"

    res = generate_sql_with_compiler_guardrail("Show students with gpa over 9", client=mock_client)
    assert res["success"] is True
    assert res["source"] == "llm"
    assert res["repairs_attempted"] == 0
    assert "gpa >= 9.0" in res["sql"]


def test_mock_llm_repair_loop_on_syntax_error():
    attempts = 0

    def mock_repairing_client(system: str, user: str) -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            # First attempt: syntax error (missing condition after WHERE)
            return "SELECT name FROM students WHERE;"
        # Second attempt: corrected syntax
        return "SELECT name FROM students WHERE gpa >= 9.0;"

    res = generate_sql_with_compiler_guardrail("Students with gpa above 9", client=mock_repairing_client)
    assert res["success"] is True
    assert res["source"] == "llm (after 1 repair)"
    assert res["repairs_attempted"] == 1
    assert len(res["repair_logs"]) == 1
    assert "ParseError" in res["repair_logs"][0]


def test_mock_llm_security_rejects_non_select():
    def mock_evil_client(system: str, user: str) -> str:
        return "DROP TABLE students;"

    res = generate_sql_with_compiler_guardrail("Delete students", client=mock_evil_client, max_repairs=1)
    # Security constraint stops non-SELECT, falls back or reports error
    assert any("Security constraint" in log or "Rejected non-SELECT" in log for log in res["repair_logs"])


def test_unconfigured_llm_falls_back_to_template():
    # Without client and without env keys
    res = generate_sql_with_compiler_guardrail("Show the top 5 students", client=None)
    assert res["success"] is True
    assert res["source"] == "template"
    assert "LIMIT 5" in res["sql"]

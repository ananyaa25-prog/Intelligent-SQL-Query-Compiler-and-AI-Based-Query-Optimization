"""Tests for own semantic analyzer and type checker."""

import pytest
from pathlib import Path

from sqlcompiler.frontend.parser import parse_sql
from sqlcompiler.semantic.symbols import Catalog
from sqlcompiler.semantic.typecheck import SemanticAnalyzer

DB_PATH = Path("person2/university.db")


@pytest.fixture
def analyzer():
    catalog = Catalog.default_university(DB_PATH)
    return SemanticAnalyzer(catalog)


def test_valid_simple_query(analyzer):
    ast = parse_sql("SELECT student_id, name, gpa FROM students WHERE gpa >= 8.5;")
    res = analyzer.analyze(ast)
    assert res["valid"] is True
    assert res["error"] is None
    # Check type annotations
    assert ast.where.inferred_type == "BOOLEAN"
    assert ast.where.left.inferred_type == "REAL"
    assert ast.where.right.inferred_type == "REAL"


def test_unknown_table_with_suggestion(analyzer):
    ast = parse_sql("SELECT name FROM studentz;")
    res = analyzer.analyze(ast)
    assert res["valid"] is False
    assert "Unknown table 'studentz'" in res["error_message"]
    hint = res["diagnostics"][0]["hint"]
    assert "students" in hint


def test_unknown_column_with_suggestion(analyzer):
    ast = parse_sql("SELECT salary FROM students;")
    res = analyzer.analyze(ast)
    assert res["valid"] is False
    assert "salary" in res["error_message"]


def test_invalid_table_alias(analyzer):
    ast = parse_sql("SELECT s.name FROM students AS x;")
    res = analyzer.analyze(ast)
    assert res["valid"] is False
    assert "Unknown table or alias 's'" in res["error_message"]


def test_ambiguous_column_in_join(analyzer):
    ast = parse_sql(
        "SELECT student_id FROM students s JOIN enrollments e ON s.student_id = e.student_id;"
    )
    res = analyzer.analyze(ast)
    assert res["valid"] is False
    assert "Ambiguous column 'student_id'" in res["error_message"]


def test_valid_qualified_join(analyzer):
    ast = parse_sql(
        "SELECT s.name, c.title, e.grade FROM students s "
        "JOIN enrollments e ON s.student_id = e.student_id "
        "JOIN courses c ON e.course_id = c.course_id;"
    )
    res = analyzer.analyze(ast)
    assert res["valid"] is True


def test_comparison_type_mismatch_numeric_string(analyzer):
    ast = parse_sql("SELECT name FROM students WHERE gpa = 'high';")
    res = analyzer.analyze(ast)
    assert res["valid"] is False
    assert "Type mismatch" in res["error_message"]


def test_compatible_numeric_comparison(analyzer):
    # Comparing REAL gpa with INTEGER literal 8 is valid
    ast = parse_sql("SELECT name FROM students WHERE gpa > 8;")
    res = analyzer.analyze(ast)
    assert res["valid"] is True


def test_arithmetic_on_text_rejected(analyzer):
    ast = parse_sql("SELECT name FROM students WHERE age + department > 10;")
    res = analyzer.analyze(ast)
    assert res["valid"] is False
    assert "Arithmetic operator '+' cannot be applied to TEXT" in res["error_message"]


def test_aggregate_in_where_rejected(analyzer):
    ast = parse_sql("SELECT name FROM students WHERE COUNT(*) > 5;")
    res = analyzer.analyze(ast)
    assert res["valid"] is False
    assert "Aggregate function 'COUNT' is not allowed in this context" in res["error_message"]


def test_sum_on_text_rejected(analyzer):
    ast = parse_sql("SELECT SUM(name) FROM students;")
    res = analyzer.analyze(ast)
    assert res["valid"] is False
    assert "Cannot compute SUM on TEXT column" in res["error_message"]


def test_group_by_rule_enforced(analyzer):
    # 'name' is non-aggregated and not in GROUP BY -> rejected
    ast = parse_sql("SELECT department, name, COUNT(*) FROM students GROUP BY department;")
    res = analyzer.analyze(ast)
    assert res["valid"] is False
    assert "Non-aggregated column 'name' in SELECT list must appear in GROUP BY" in res["error_message"]


def test_group_by_rule_valid(analyzer):
    ast = parse_sql("SELECT department, COUNT(*) AS cnt FROM students GROUP BY department;")
    res = analyzer.analyze(ast)
    assert res["valid"] is True


def test_having_rule_enforced(analyzer):
    # 'gpa' in HAVING must be in GROUP BY or aggregated
    ast = parse_sql("SELECT department, COUNT(*) FROM students GROUP BY department HAVING gpa > 8.0;")
    res = analyzer.analyze(ast)
    assert res["valid"] is False
    assert "HAVING must be in GROUP BY or wrapped in an aggregate" in res["error_message"]


def test_order_by_alias_resolution(analyzer):
    ast = parse_sql("SELECT department, COUNT(*) AS student_count FROM students GROUP BY department ORDER BY student_count DESC;")
    res = analyzer.analyze(ast)
    assert res["valid"] is True


def test_multiline_diagnostics_report_exact_line_and_column(analyzer):
    # 1. E102 unknown column on line 2, column 8
    sql1 = "SELECT student_id,\n       salary\nFROM students;"
    ast1 = parse_sql(sql1)
    res1 = analyzer.analyze(ast1, raw_sql=sql1)
    assert res1["valid"] is False
    diag1 = res1["diagnostics"][0]
    assert diag1["code"] == "E102"
    assert diag1["line"] == 2
    assert diag1["column"] == 8

    # 2. E303 comparison type mismatch on line 3, operator '=' at column 11
    sql2 = "SELECT name\nFROM students\nWHERE gpa = 'high';"
    ast2 = parse_sql(sql2)
    res2 = analyzer.analyze(ast2, raw_sql=sql2)
    assert res2["valid"] is False
    diag2 = res2["diagnostics"][0]
    assert diag2["code"] == "E303"
    assert diag2["line"] == 3
    assert diag2["column"] == 11

    # 3. E402 non-aggregated column in SELECT list on line 2, column 8
    sql3 = "SELECT COUNT(*),\n       name\nFROM students\nGROUP BY department;"
    ast3 = parse_sql(sql3)
    res3 = analyzer.analyze(ast3, raw_sql=sql3)
    assert res3["valid"] is False
    diag3 = res3["diagnostics"][0]
    assert diag3["code"] == "E402"
    assert diag3["line"] == 2
    assert diag3["column"] == 8


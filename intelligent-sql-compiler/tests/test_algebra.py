"""Tests for Relational Algebra IR lowering, text and DOT rendering, and cost model."""

import pytest
from pathlib import Path

from sqlcompiler.frontend.parser import parse_sql
from sqlcompiler.ir.algebra import (
    lower_ast_to_algebra,
    suggest_join_order,
    Scan,
    Select,
    Project,
    JoinNode,
)

DB_PATH = Path("person2/university.db")


def test_algebra_lowering_single_table():
    sql = "SELECT name, gpa FROM students WHERE gpa >= 9.0 LIMIT 5;"
    ast = parse_sql(sql)
    ir = lower_ast_to_algebra(ast, db_path=DB_PATH)
    assert isinstance(ir, Project)
    assert ir.estimated_rows == 5.0
    text = ir.to_text()
    assert "Scan(students)" in text
    assert "Select(sigma gpa >= 9.0)" in text
    assert "Limit(LIMIT 5)" in text


def test_algebra_lowering_joins():
    sql = (
        "SELECT s.name, e.grade FROM students s "
        "JOIN enrollments e ON s.student_id = e.student_id;"
    )
    ast = parse_sql(sql)
    ir = lower_ast_to_algebra(ast, db_path=DB_PATH)
    text = ir.to_text()
    assert "Join(INNER ON s.student_id = e.student_id)" in text
    assert "Scan(students AS s)" in text
    assert "Scan(enrollments AS e)" in text


def test_algebra_dot_generation():
    sql = "SELECT student_id, name FROM students WHERE age >= 20;"
    ast = parse_sql(sql)
    ir = lower_ast_to_algebra(ast, db_path=DB_PATH)
    dot = ir.to_dot()
    assert "digraph AlgebraIR {" in dot
    assert "Scan: students" in dot
    assert "Select (sigma)" in dot


def test_join_order_suggestion_multi_table():
    sql = (
        "SELECT s.name, c.title FROM students s "
        "JOIN enrollments e ON s.student_id = e.student_id "
        "JOIN courses c ON e.course_id = c.course_id;"
    )
    ast = parse_sql(sql)
    suggestion = suggest_join_order(ast, db_path=DB_PATH)
    assert suggestion["applicable"] is True
    assert len(suggestion["original_order"]) == 3
    assert len(suggestion["proposed_order"]) == 3
    assert "note" in suggestion
    assert "informational only" in suggestion["note"].lower()


def test_join_order_not_applicable_single_table():
    sql = "SELECT name FROM students WHERE gpa >= 9.0;"
    ast = parse_sql(sql)
    suggestion = suggest_join_order(ast, db_path=DB_PATH)
    assert suggestion["applicable"] is False

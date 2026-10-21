"""Comprehensive tests for all multi-pass optimizer passes and manager trace."""

import pytest
from pathlib import Path

from sqlcompiler.frontend.parser import parse_sql
from sqlcompiler.semantic.symbols import Catalog
from sqlcompiler.optimizer.passes import (
    ConstantFoldingPass,
    BooleanSimplificationPass,
    RangePredicateConsolidationPass,
    ContradictionDetectionPass,
    RedundantDistinctRemovalPass,
    SelectStarExpansionPass,
    PredicatePushdownPass,
    InAndBetweenNormalizationPass,
)
from sqlcompiler.optimizer.manager import optimize_with_trace, optimize_sql

DB_PATH = Path("person2/university.db")


@pytest.fixture
def catalog():
    return Catalog.default_university(DB_PATH)


# 1. Constant Folding
def test_constant_folding_arithmetic():
    ast = parse_sql("SELECT name FROM students WHERE age > 18 + 2;")
    new_ast, changed = ConstantFoldingPass().apply(ast)
    assert changed is True
    assert "age > 20" in new_ast.to_sql()


def test_constant_folding_comparison():
    ast = parse_sql("SELECT name FROM students WHERE 1 = 1 AND gpa >= 8.0;")
    new_ast, changed = ConstantFoldingPass().apply(ast)
    assert changed is True
    assert "TRUE" in new_ast.to_sql()


def test_constant_folding_does_not_fire_on_zero_division():
    ast = parse_sql("SELECT name FROM students WHERE age > 10 / 0;")
    new_ast, changed = ConstantFoldingPass().apply(ast)
    assert changed is False


# 2. Boolean Simplification
def test_boolean_simplification_and_true():
    ast = parse_sql("SELECT name FROM students WHERE gpa >= 8.0 AND TRUE;")
    new_ast, changed = BooleanSimplificationPass().apply(ast)
    assert changed is True
    assert "TRUE" not in new_ast.to_sql()
    assert "gpa >= 8.0" in new_ast.to_sql()


def test_boolean_simplification_double_not():
    ast = parse_sql("SELECT name FROM students WHERE NOT NOT gpa >= 8.0;")
    new_ast, changed = BooleanSimplificationPass().apply(ast)
    assert changed is True
    assert "NOT" not in new_ast.to_sql()
    assert "gpa >= 8.0" in new_ast.to_sql()


def test_boolean_simplification_duplicate_conjunct():
    ast = parse_sql("SELECT name FROM students WHERE gpa >= 8.0 AND gpa >= 8.0;")
    new_ast, changed = BooleanSimplificationPass().apply(ast)
    assert changed is True
    sql = new_ast.to_sql()
    assert sql.count("gpa >= 8.0") == 1


def test_boolean_simplification_does_not_fire_when_unsafe():
    ast = parse_sql("SELECT name FROM students WHERE gpa >= 8.0 AND age <= 22;")
    new_ast, changed = BooleanSimplificationPass().apply(ast)
    assert changed is False


# 3. Range Predicate Consolidation
def test_range_consolidation_lower_bounds():
    ast = parse_sql("SELECT name FROM students WHERE gpa >= 9.0 AND gpa >= 8.0;")
    new_ast, changed = RangePredicateConsolidationPass().apply(ast)
    assert changed is True
    sql = new_ast.to_sql()
    assert "gpa >= 9.0" in sql
    assert "gpa >= 8.0" not in sql


def test_range_consolidation_strictness_gt_vs_gte():
    # gpa > 8.0 is strictly tighter than gpa >= 8.0
    ast = parse_sql("SELECT name FROM students WHERE gpa > 8.0 AND gpa >= 8.0;")
    new_ast, changed = RangePredicateConsolidationPass().apply(ast)
    assert changed is True
    sql = new_ast.to_sql()
    assert "gpa > 8.0" in sql
    assert "gpa >= 8.0" not in sql


def test_range_consolidation_upper_bounds():
    ast = parse_sql("SELECT name FROM students WHERE age <= 20 AND age <= 25;")
    new_ast, changed = RangePredicateConsolidationPass().apply(ast)
    assert changed is True
    sql = new_ast.to_sql()
    assert "age <= 20" in sql
    assert "age <= 25" not in sql


def test_range_consolidation_does_not_fire_on_different_columns():
    ast = parse_sql("SELECT name FROM students WHERE gpa >= 9.0 AND age >= 20;")
    new_ast, changed = RangePredicateConsolidationPass().apply(ast)
    assert changed is False


# 4. Contradiction Detection
def test_contradiction_detection_disjoint_ranges():
    ast = parse_sql("SELECT name FROM students WHERE gpa > 9.0 AND gpa < 5.0;")
    new_ast, changed = ContradictionDetectionPass().apply(ast)
    assert changed is True
    sql = new_ast.to_sql()
    assert "1 = 0" in sql


def test_contradiction_detection_does_not_fire_when_satisfiable():
    ast = parse_sql("SELECT name FROM students WHERE gpa > 5.0 AND gpa < 9.0;")
    new_ast, changed = ContradictionDetectionPass().apply(ast)
    assert changed is False


# 5. Redundant DISTINCT Removal
def test_distinct_removal_with_primary_key(catalog):
    ast = parse_sql("SELECT DISTINCT student_id, name FROM students;")
    new_ast, changed = RedundantDistinctRemovalPass().apply(ast, catalog=catalog)
    assert changed is True
    assert "DISTINCT" not in new_ast.to_sql()


def test_distinct_removal_does_not_fire_without_primary_key(catalog):
    ast = parse_sql("SELECT DISTINCT name FROM students;")
    new_ast, changed = RedundantDistinctRemovalPass().apply(ast, catalog=catalog)
    assert changed is False
    assert "DISTINCT" in new_ast.to_sql()


# 6. SELECT * Expansion
def test_select_star_expansion(catalog):
    ast = parse_sql("SELECT * FROM courses;")
    new_ast, changed = SelectStarExpansionPass().apply(ast, catalog=catalog)
    assert changed is True
    sql = new_ast.to_sql()
    assert "*" not in sql
    assert "course_id" in sql
    assert "title" in sql
    assert "department" in sql
    assert "credits" in sql


def test_select_star_does_not_fire_on_explicit_columns(catalog):
    ast = parse_sql("SELECT course_id, title FROM courses;")
    new_ast, changed = SelectStarExpansionPass().apply(ast, catalog=catalog)
    assert changed is False


# 7. Predicate Pushdown
def test_predicate_pushdown_inner_join():
    ast = parse_sql(
        "SELECT s.name, e.grade FROM students s "
        "INNER JOIN enrollments e ON s.student_id = e.student_id "
        "WHERE e.grade = 'A';"
    )
    new_ast, changed = PredicatePushdownPass().apply(ast)
    assert changed is True
    sql = new_ast.to_sql()
    assert "e.grade = 'A'" in new_ast.joins[0].on.to_sql()
    assert new_ast.where is None


def test_predicate_pushdown_does_not_push_left_join():
    ast = parse_sql(
        "SELECT s.name, e.grade FROM students s "
        "LEFT JOIN enrollments e ON s.student_id = e.student_id "
        "WHERE e.grade = 'A';"
    )
    new_ast, changed = PredicatePushdownPass().apply(ast)
    assert changed is False


# 8. IN Normalization
def test_in_normalization_single_value():
    ast = parse_sql("SELECT name FROM students WHERE student_id IN (42);")
    new_ast, changed = InAndBetweenNormalizationPass().apply(ast)
    assert changed is True
    assert "student_id = 42" in new_ast.to_sql()


# 9. Multi-pass Manager and Trace
def test_optimize_with_trace():
    sql = (
        "SELECT student_id, name FROM students "
        "WHERE gpa >= 9.0 AND gpa >= 8.0 AND (1 = 1);"
    )
    trace = optimize_with_trace(sql)
    assert trace["changed"] is True
    assert len(trace["steps"]) >= 2
    pass_names = [s["pass_name"] for s in trace["steps"]]
    assert "Constant Folding" in pass_names
    assert "Redundant Range Consolidation" in pass_names
    assert "gpa >= 9.0" in trace["final_sql"]
    assert "gpa >= 8.0" not in trace["final_sql"]
    assert "1 = 1" not in trace["final_sql"]

"""Comprehensive tests for hand-written Lexer, Parser, and AST nodes."""

import pytest
import sqlglot

from sqlcompiler.frontend.lexer import Token, LexicalError, tokenize
from sqlcompiler.frontend.ast_nodes import (
    SelectStmt, SelectItem, TableRef, Join, BinaryOp, UnaryOp,
    ColumnRef, Literal, FunctionCall, Between, InList, IsNull, Star,
    ast_to_sql, ast_to_dict, ast_to_dot
)
from sqlcompiler.frontend.parser import Parser, ParseError, parse_sql


# 1. Lexer Tests
def test_lexer_line_and_column_tracking():
    sql = "SELECT\n  name,\n  gpa\nFROM students;"
    tokens = tokenize(sql)
    # Token 0: SELECT at line 1, col 1
    assert tokens[0].value.upper() == "SELECT"
    assert tokens[0].line == 1
    assert tokens[0].column == 1

    # Token 1: name at line 2, col 3
    assert tokens[1].value == "name"
    assert tokens[1].line == 2
    assert tokens[1].column == 3

    # Token 2: comma at line 2, col 7
    assert tokens[2].value == ","
    assert tokens[2].line == 2
    assert tokens[2].column == 7

    # Token 3: gpa at line 3, col 3
    assert tokens[3].value == "gpa"
    assert tokens[3].line == 3
    assert tokens[3].column == 3


def test_lexer_unknown_char_error_with_caret():
    sql = "SELECT name FROM students WHERE gpa ~ 9.0;"
    with pytest.raises(LexicalError) as exc_info:
        tokenize(sql)
    err = exc_info.value
    assert err.line == 1
    assert err.column == 37
    assert "~" in str(err)
    assert "^" in err.snippet


# 2. Precedence and Associativity Tests
def test_precedence_or_and():
    sql = "SELECT * FROM t WHERE a = 1 OR b = 2 AND c = 3;"
    ast = parse_sql(sql)
    # AND should bind tighter than OR: a = 1 OR (b = 2 AND c = 3)
    where = ast.where
    assert isinstance(where, BinaryOp)
    assert where.op == "OR"
    assert isinstance(where.left, BinaryOp) and where.left.op == "="
    assert isinstance(where.right, BinaryOp) and where.right.op == "AND"


def test_precedence_parentheses_override():
    sql = "SELECT * FROM t WHERE (a = 1 OR b = 2) AND c = 3;"
    ast = parse_sql(sql)
    where = ast.where
    assert isinstance(where, BinaryOp)
    assert where.op == "AND"
    assert isinstance(where.left, BinaryOp) and where.left.op == "OR"
    assert isinstance(where.right, BinaryOp) and where.right.op == "="


def test_precedence_arithmetic():
    sql = "SELECT * FROM t WHERE a + b * c > 10;"
    ast = parse_sql(sql)
    assert isinstance(ast.where, BinaryOp)
    comp_left = ast.where.left
    assert isinstance(comp_left, BinaryOp)
    assert comp_left.op == "+"
    assert isinstance(comp_left.right, BinaryOp)
    assert comp_left.right.op == "*"


def test_unary_not_precedence():
    sql = "SELECT * FROM t WHERE NOT a = 1 AND b = 2;"
    ast = parse_sql(sql)
    # NOT binds to comparison, then AND combines them
    where = ast.where
    assert isinstance(where, BinaryOp)
    assert where.op == "AND"
    assert isinstance(where.left, UnaryOp)
    assert where.left.op == "NOT"


# 3. Syntax Error Diagnostics
def test_syntax_error_missing_from_table():
    sql = "SELECT name FROM;"
    with pytest.raises(ParseError) as exc_info:
        parse_sql(sql)
    err = exc_info.value
    assert "Expected a table name after FROM" in str(err)
    assert err.expected == "table name"
    assert err.line == 1
    assert err.column == 17


def test_syntax_error_missing_where_condition():
    sql = "SELECT name FROM students WHERE;"
    with pytest.raises(ParseError) as exc_info:
        parse_sql(sql)
    err = exc_info.value
    assert "WHERE requires a condition" in str(err)


def test_syntax_error_negative_limit():
    sql = "SELECT name FROM students LIMIT -5;"
    with pytest.raises(ParseError) as exc_info:
        parse_sql(sql)
    err = exc_info.value
    assert "LIMIT requires a non-negative integer" in str(err)


def test_syntax_error_unclosed_paren():
    sql = "SELECT name FROM students WHERE (gpa >= 8.0;"
    with pytest.raises(ParseError) as exc_info:
        parse_sql(sql)
    err = exc_info.value
    assert "Expected ')'" in str(err)


# 4. AST Features and Round-Trip Tests
CORPUS_QUERIES = [
    "SELECT student_id, name, gpa FROM students;",
    "SELECT DISTINCT department FROM students;",
    "SELECT * FROM students;",
    "SELECT s.* FROM students AS s;",
    "SELECT student_id, name, gpa FROM students WHERE gpa >= 9.0 AND gpa >= 8.0 ORDER BY gpa DESC LIMIT 10;",
    "SELECT department, COUNT(*) AS student_count FROM students GROUP BY department ORDER BY student_count DESC;",
    "SELECT department, AVG(gpa) AS avg_gpa FROM students GROUP BY department HAVING AVG(gpa) >= 8.0;",
    "SELECT name FROM students WHERE age BETWEEN 18 AND 22;",
    "SELECT name FROM students WHERE department IN ('Computer Science', 'Data Science');",
    "SELECT name FROM students WHERE email LIKE '%@example.com';",
    "SELECT name FROM students WHERE grade IS NULL;",
    "SELECT name FROM students WHERE grade IS NOT NULL;",
    "SELECT s.name, c.title FROM students AS s INNER JOIN enrollments AS e ON s.student_id = e.student_id INNER JOIN courses AS c ON e.course_id = c.course_id;",
    "SELECT s.name, c.title FROM students s LEFT JOIN enrollments e ON s.student_id = e.student_id;",
    "SELECT name, gpa * 10 AS percentage FROM students WHERE age + 1 <= 25;",
    "SELECT name FROM students ORDER BY department ASC, gpa DESC;",
    "SELECT name FROM students LIMIT 10 OFFSET 5;",
    "SELECT COUNT(DISTINCT department) FROM students;",
    "SELECT SUM(credits), MAX(credits), MIN(credits) FROM courses;",
    "SELECT student_id FROM students WHERE NOT (gpa < 7.0 OR age > 24);",
    "SELECT s.name FROM students AS s WHERE s.gpa > 8.5;",
    "SELECT name FROM students WHERE (age = 20 OR age = 21) AND gpa >= 9.0;",
    "SELECT name FROM students WHERE age NOT BETWEEN 18 AND 20;",
    "SELECT name FROM students WHERE department NOT IN ('Mechanical', 'Civil');",
    "SELECT student_id, name FROM students WHERE 1 = 1;",
    "SELECT student_id, name FROM students WHERE TRUE AND gpa >= 8.0;",
    "SELECT name FROM students WHERE gpa > 8.0 AND department = 'Computer Science' LIMIT 50;",
    "SELECT s.student_id, e.course_id FROM students s JOIN enrollments e ON s.student_id = e.student_id WHERE s.age >= 20;",
    "SELECT title, credits FROM courses WHERE department = 'Data Science' ORDER BY credits DESC;",
    "SELECT course_id, COUNT(student_id) AS enrolled FROM enrollments GROUP BY course_id HAVING COUNT(student_id) > 5;",
    "SELECT s.name, e.grade FROM students s JOIN enrollments e ON s.student_id = e.student_id WHERE e.grade = 'A' ORDER BY s.name LIMIT 5;",
    "SELECT name FROM students WHERE age - 2 >= 18 AND gpa / 2.0 >= 4.0;",
]


@pytest.mark.parametrize("query", CORPUS_QUERIES)
def test_round_trip_parse_and_sql(query):
    ast1 = parse_sql(query)
    sql_generated = ast_to_sql(ast1)
    ast2 = parse_sql(sql_generated)

    # Both ASTs should be equivalent
    assert ast_to_dict(ast1) == ast_to_dict(ast2)


@pytest.mark.parametrize("query", CORPUS_QUERIES)
def test_agreement_with_sqlglot_on_corpus(query):
    # Both our parser and SQLGlot should parse the query without error
    our_ast = parse_sql(query)
    sqlglot_ast = sqlglot.parse_one(query, read="sqlite")

    assert our_ast is not None
    assert sqlglot_ast is not None

    # Check table name match if present
    if our_ast.from_table:
        sqlglot_tables = [t.name.casefold() for t in sqlglot_ast.find_all(sqlglot.exp.Table)]
        assert our_ast.from_table.name.casefold() in sqlglot_tables


def test_ast_dot_and_dict_output():
    sql = "SELECT s.name, COUNT(*) FROM students s GROUP BY s.name;"
    ast = parse_sql(sql)
    d = ast_to_dict(ast)
    assert d["type"] == "SelectStmt"
    assert len(d["columns"]) == 2

    dot = ast_to_dot(ast)
    assert "digraph AST {" in dot
    assert "SELECT" in dot
    assert "students" in dot

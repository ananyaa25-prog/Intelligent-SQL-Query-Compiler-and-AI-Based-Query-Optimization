"""Tests for VDBE bytecode inspection and comparison."""

import pytest
from pathlib import Path

from sqlcompiler.codegen.bytecode import explain_bytecode, compare_bytecode

DB_PATH = Path("person2/university.db")


def test_explain_bytecode_returns_instructions_and_metrics():
    sql = "SELECT name, gpa FROM students WHERE gpa >= 9.0 LIMIT 5;"
    res = explain_bytecode(sql, db_path=DB_PATH)
    assert res["success"] is True
    assert len(res["instructions"]) > 0
    m = res["metrics"]
    assert m["total_opcodes"] > 0
    assert "loops" in m
    assert "index_seeks" in m


def test_compare_bytecode_computes_difference():
    # Comparing redundant predicate with consolidated predicate
    orig = "SELECT student_id, name FROM students WHERE gpa >= 9.0 AND gpa >= 8.0 LIMIT 10;"
    cand = "SELECT student_id, name FROM students WHERE gpa >= 9.0 LIMIT 10;"
    comp = compare_bytecode(orig, cand, db_path=DB_PATH)
    assert comp["success"] is True
    assert "original_metrics" in comp
    assert "candidate_metrics" in comp
    assert "opcode_reduction" in comp
    assert "note" in comp

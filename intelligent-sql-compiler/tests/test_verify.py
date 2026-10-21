"""Tests for verification layer: differential testing, SMT proofs, and mutation catching."""

import pytest

from sqlcompiler.verify.difftest import differential_test, DEFAULT_NUM_DATABASES
from sqlcompiler.verify.smt import verify_predicate_equivalence, Z3_AVAILABLE
from sqlcompiler.verify.mutation import run_mutation_demo


def test_difftest_accepts_equivalent_queries():
    orig = "SELECT student_id, name, gpa FROM students WHERE gpa >= 9.0 AND gpa >= 8.0;"
    cand = "SELECT student_id, name, gpa FROM students WHERE gpa >= 9.0;"
    res = differential_test(orig, cand, num_databases=DEFAULT_NUM_DATABASES, seed=42)
    assert res["equivalent"] is True
    assert res["counterexample"] is None


def test_difftest_catches_nonequivalent_mutation():
    orig = "SELECT student_id, name, gpa FROM students WHERE gpa >= 9.0 AND gpa >= 8.0;"
    buggy = "SELECT student_id, name, gpa FROM students WHERE gpa >= 8.0;"
    res = differential_test(orig, buggy, num_databases=DEFAULT_NUM_DATABASES, seed=42)
    assert res["equivalent"] is False
    assert res["counterexample"] is not None
    assert "Difference observed" in res["message"]


def test_smt_proves_equivalent_predicates():
    if not Z3_AVAILABLE:
        pytest.skip("z3-solver is not installed")
    orig = "SELECT student_id, name, gpa FROM students WHERE gpa >= 9.0 AND gpa >= 8.0;"
    cand = "SELECT student_id, name, gpa FROM students WHERE gpa >= 9.0;"
    res = verify_predicate_equivalence(orig, cand)
    assert res["status"] == "proved"
    assert res["proved"] is True
    assert "proved predicate equivalence" in res["message"]


def test_smt_disproves_buggy_predicate_with_counterexample():
    if not Z3_AVAILABLE:
        pytest.skip("z3-solver is not installed")
    orig = "SELECT student_id, name, gpa FROM students WHERE gpa >= 9.0;"
    cand = "SELECT student_id, name, gpa FROM students WHERE gpa >= 8.0;"
    res = verify_predicate_equivalence(orig, cand)
    assert res["status"] == "disproved"
    assert res["proved"] is False
    assert res["counterexample"] is not None
    # Counterexample GPA should be in [8.0, 9.0)
    gpa_val = res["counterexample"]["gpa"]
    assert 8.0 <= gpa_val < 9.0


def test_mutation_demo_catches_all_mutants():
    results = run_mutation_demo()
    assert len(results) > 0
    for r in results:
        assert r["caught"] is True, f"Mutant '{r['mutant_name']}' was not caught by any verification layer!"
        assert len(r["caught_by_layers"]) > 0


def test_smt_fallback_when_z3_unavailable(monkeypatch):
    import sqlcompiler.verify.smt as smt_module
    import pipeline

    # Monkeypatch Z3_AVAILABLE to False
    monkeypatch.setattr(smt_module, "Z3_AVAILABLE", False)
    monkeypatch.setattr(pipeline, "Z3_AVAILABLE", False)

    orig = "SELECT student_id, name, gpa FROM students WHERE gpa >= 9.0 AND gpa >= 8.0;"
    cand = "SELECT student_id, name, gpa FROM students WHERE gpa >= 9.0;"
    res = smt_module.verify_predicate_equivalence(orig, cand)
    assert res["status"] == "z3_unavailable"
    assert res["proved"] is False
    assert "z3-solver is not installed" in res["message"]

    # Also test that run_pipeline succeeds and falls back gracefully to Layers A and B
    pipeline_res = pipeline.run_pipeline("SELECT student_id, name FROM students WHERE gpa >= 9.0 AND gpa >= 8.0 LIMIT 10;")
    assert pipeline_res["success"] is True
    assert pipeline_res["gate_details"]["verified"] is True
    assert "C: z3-solver not installed (skipped)" in pipeline_res["gate_details"]["summary"]


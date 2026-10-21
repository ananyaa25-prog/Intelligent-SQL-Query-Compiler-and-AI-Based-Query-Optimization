"""Mutation testing and demonstration suite: testing the equivalence gate with buggy optimizers."""

from __future__ import annotations

import re
from typing import Any, Optional

from sqlcompiler.verify.difftest import differential_test
from sqlcompiler.verify.smt import verify_predicate_equivalence
from sqlcompiler.engine import execute_sql



def mutate_weaker_bound(sql: str) -> str:
    """Buggy rule: keeps the WEAKER bound instead of the stronger one."""
    if "gpa >= 9.0" in sql and "gpa >= 8.0" in sql:
        return sql.replace("gpa >= 9.0 AND gpa >= 8.0", "gpa >= 8.0").replace("gpa >= 8.0 AND gpa >= 9.0", "gpa >= 8.0")
    return sql


def mutate_and_to_or(sql: str) -> str:
    """Buggy rule: inadvertently turns AND into OR."""
    return re.sub(r"\bAND\b", "OR", sql, count=1)


def mutate_strict_inequality(sql: str) -> str:
    """Buggy rule: alters >= into > (dropping boundary points)."""
    return sql.replace(">=", ">")


def mutate_invert_comparison(sql: str) -> str:
    """Buggy rule: reverses comparison direction > to <."""
    return sql.replace(">", "<")


def mutate_drop_where(sql: str) -> str:
    """Buggy rule: completely drops the WHERE clause."""
    return re.sub(r"\s+WHERE\s+.*?(?=(ORDER|LIMIT|;|$))", " ", sql, flags=re.IGNORECASE)


MUTANTS = [
    ("Keep Weaker Bound (>= 8.0)", mutate_weaker_bound, "Keep lower threshold 8.0 instead of 9.0"),
    ("Flip AND to OR", mutate_and_to_or, "Replaces conjunction AND with disjunction OR"),
    ("Drop Boundary Point (>= to >)", mutate_strict_inequality, "Changes inclusive >= into strict >"),
    ("Invert Comparison (> to <)", mutate_invert_comparison, "Inverts comparison direction from > to <"),
    ("Accidental Unconditional (Drop WHERE)", mutate_drop_where, "Accidentally drops WHERE filter"),
]


def run_mutation_demo(
    sample_sql: str = "SELECT student_id, name, gpa FROM students WHERE gpa >= 9.0 AND gpa >= 8.0 LIMIT 10;"
) -> list[dict[str, Any]]:
    """
    Apply each deliberately buggy rewrite rule to a sample query and run the
    equivalence gate (Layers A, B, C) to verify that every bug is caught.
    """
    results = []

    for name, mutator, description in MUTANTS:
        mutant_sql = mutator(sample_sql)
        if mutant_sql.strip().rstrip(";") == sample_sql.strip().rstrip(";"):
            continue

        caught_layers = []
        first_counterexample = None

        # Layer A: Check against current local sample database
        res_orig = execute_sql(sample_sql)
        res_mut = execute_sql(mutant_sql)
        if res_orig["success"] and res_mut["success"]:
            if res_orig["rows"] != res_mut["rows"]:
                caught_layers.append("Layer A (Sample DB)")
                first_counterexample = {
                    "layer": "Layer A",
                    "sample_db_orig_count": len(res_orig["rows"]),
                    "sample_db_mutant_count": len(res_mut["rows"]),
                }

        # Layer B: Differential testing
        difftest_res = differential_test(sample_sql, mutant_sql, num_databases=20, seed=123)
        if not difftest_res["equivalent"]:
            caught_layers.append("Layer B (Random DBs)")
            if not first_counterexample:
                first_counterexample = {
                    "layer": "Layer B",
                    "details": difftest_res.get("counterexample"),
                }

        # Layer C: SMT proof
        smt_res = verify_predicate_equivalence(sample_sql, mutant_sql)
        if smt_res["status"] == "disproved":
            caught_layers.append("Layer C (Z3 SMT)")
            if not first_counterexample:
                first_counterexample = {
                    "layer": "Layer C",
                    "details": smt_res.get("counterexample"),
                }

        caught = len(caught_layers) > 0
        results.append({
            "mutant_name": name,
            "description": description,
            "mutant_sql": mutant_sql,
            "caught": caught,
            "caught_by_layers": caught_layers,
            "counterexample": first_counterexample,
        })

    return results

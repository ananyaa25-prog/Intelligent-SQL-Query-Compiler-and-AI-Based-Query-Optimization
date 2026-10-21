"""Verification module: differential testing, SMT proofs, and mutation testing."""

from sqlcompiler.verify.difftest import differential_test
from sqlcompiler.verify.smt import verify_predicate_equivalence, Z3_AVAILABLE
from sqlcompiler.verify.mutation import run_mutation_demo, MUTANTS

__all__ = [
    "differential_test",
    "verify_predicate_equivalence",
    "Z3_AVAILABLE",
    "run_mutation_demo",
    "MUTANTS",
]

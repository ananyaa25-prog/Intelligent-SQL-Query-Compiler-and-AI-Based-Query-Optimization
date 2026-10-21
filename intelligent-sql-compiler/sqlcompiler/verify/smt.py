"""Layer C: Formal SMT equivalence proof with Z3 for SQL predicates under 3-valued logic."""

from __future__ import annotations

from typing import Any, Optional, Tuple

try:
    import z3
    Z3_AVAILABLE = True
except ImportError:
    Z3_AVAILABLE = False

from sqlcompiler.frontend.parser import parse_sql
from sqlcompiler.frontend.ast_nodes import (
    SelectStmt, Expression, ColumnRef, Literal,
    BinaryOp, UnaryOp, Between, IsNull
)


class SMTPredicateEncoder:
    """Translates SQL AST predicate expressions into Z3 formulas under 3-valued logic."""

    def __init__(self):
        self.cols_val: dict[str, Any] = {}
        self.cols_null: dict[str, Any] = {}

    def get_column(self, name: str) -> Tuple[Any, Any]:
        c_name = name.casefold()
        if c_name not in self.cols_val:
            self.cols_val[c_name] = z3.Real(f"val_{c_name}")
            self.cols_null[c_name] = z3.Bool(f"null_{c_name}")
        return self.cols_val[c_name], self.cols_null[c_name]

    def encode(self, expr: Expression) -> Tuple[Any, Any]:
        """
        Returns (is_true, is_null) Z3 boolean formulas.
        is_false is defined as: z3.And(z3.Not(is_true), z3.Not(is_null))
        """
        if isinstance(expr, Literal):
            if expr.value is None or expr.raw.upper() == "NULL":
                return z3.BoolVal(False), z3.BoolVal(True)
            if isinstance(expr.value, bool):
                return z3.BoolVal(expr.value), z3.BoolVal(False)
            if isinstance(expr.value, (int, float)):
                # Literals in boolean position
                return z3.BoolVal(expr.value != 0), z3.BoolVal(False)
            return z3.BoolVal(True), z3.BoolVal(False)

        if isinstance(expr, ColumnRef):
            val, is_null = self.get_column(expr.name)
            # A numeric column evaluated as boolean
            return (val != 0), is_null

        if isinstance(expr, IsNull):
            val, is_null = self.get_column(expr.expr.name) if isinstance(expr.expr, ColumnRef) else (None, z3.BoolVal(False))
            if expr.not_null:
                return z3.Not(is_null), z3.BoolVal(False)
            return is_null, z3.BoolVal(False)

        if isinstance(expr, UnaryOp) and expr.op.upper() == "NOT":
            child_true, child_null = self.encode(expr.operand)
            # NOT True -> False, NOT False -> True, NOT Null -> Null
            child_false = z3.And(z3.Not(child_true), z3.Not(child_null))
            return child_false, child_null

        if isinstance(expr, BinaryOp):
            op = expr.op.upper()

            if op == "AND":
                l_true, l_null = self.encode(expr.left)
                r_true, r_null = self.encode(expr.right)
                # True only if BOTH are true
                res_true = z3.And(l_true, r_true)
                l_false = z3.And(z3.Not(l_true), z3.Not(l_null))
                r_false = z3.And(z3.Not(r_true), z3.Not(r_null))
                # Result is False if either is False
                res_false = z3.Or(l_false, r_false)
                res_null = z3.And(z3.Not(res_true), z3.Not(res_false))
                return res_true, res_null

            if op == "OR":
                l_true, l_null = self.encode(expr.left)
                r_true, r_null = self.encode(expr.right)
                # True if either is true
                res_true = z3.Or(l_true, r_true)
                l_false = z3.And(z3.Not(l_true), z3.Not(l_null))
                r_false = z3.And(z3.Not(r_true), z3.Not(r_null))
                res_false = z3.And(l_false, r_false)
                res_null = z3.And(z3.Not(res_true), z3.Not(res_false))
                return res_true, res_null

            # Comparisons: =, !=, <, <=, >, >=
            if op in ("=", "!=", "<>", "<", "<=", ">", ">="):
                l_val, l_null = self._eval_arith(expr.left)
                r_val, r_null = self._eval_arith(expr.right)
                if l_val is None or r_val is None:
                    raise ValueError(f"Cannot encode non-arithmetic operand in comparison {op}")

                either_null = z3.Or(l_null, r_null)
                if op == "=":
                    cmp_res = (l_val == r_val)
                elif op in ("!=", "<>"):
                    cmp_res = (l_val != r_val)
                elif op == "<":
                    cmp_res = (l_val < r_val)
                elif op == "<=":
                    cmp_res = (l_val <= r_val)
                elif op == ">":
                    cmp_res = (l_val > r_val)
                elif op == ">=":
                    cmp_res = (l_val >= r_val)
                else:
                    cmp_res = z3.BoolVal(False)

                res_true = z3.And(z3.Not(either_null), cmp_res)
                return res_true, either_null

        if isinstance(expr, Between):
            # low <= expr AND expr <= high
            c1 = BinaryOp(op=">=", left=expr.expr, right=expr.low)
            c2 = BinaryOp(op="<=", left=expr.expr, right=expr.high)
            combined = BinaryOp(op="AND", left=c1, right=c2)
            if expr.not_between:
                combined = UnaryOp(op="NOT", operand=combined)
            return self.encode(combined)

        raise ValueError(f"Unsupported AST node in SMT encoder: {type(expr).__name__}")

    def _eval_arith(self, expr: Expression) -> Tuple[Optional[Any], Any]:
        if isinstance(expr, Literal) and isinstance(expr.value, (int, float)):
            return z3.RealVal(float(expr.value)), z3.BoolVal(False)
        if isinstance(expr, Literal) and expr.value is None:
            return z3.RealVal(0.0), z3.BoolVal(True)
        if isinstance(expr, ColumnRef):
            val, is_null = self.get_column(expr.name)
            return val, is_null
        if isinstance(expr, BinaryOp) and expr.op in ("+", "-", "*"):
            l_val, l_null = self._eval_arith(expr.left)
            r_val, r_null = self._eval_arith(expr.right)
            if l_val is not None and r_val is not None:
                if expr.op == "+":
                    res = l_val + r_val
                elif expr.op == "-":
                    res = l_val - r_val
                else:
                    res = l_val * r_val
                return res, z3.Or(l_null, r_null)
        return None, z3.BoolVal(False)


def verify_predicate_equivalence(original_sql: str, candidate_sql: str) -> dict[str, Any]:
    """
    Formally verify predicate equivalence between original and candidate queries using Z3.
    Returns:
      status: "proved" (UNSAT) | "disproved" (SAT with counterexample) | "not_applicable" | "z3_unavailable"
    """
    if not Z3_AVAILABLE:
        return {
            "status": "z3_unavailable",
            "proved": False,
            "layer": "Layer C",
            "message": "z3-solver is not installed; formal SMT proof skipped.",
        }

    try:
        orig_ast = parse_sql(original_sql)
        cand_ast = parse_sql(candidate_sql)
    except Exception as exc:
        return {
            "status": "not_applicable",
            "proved": False,
            "layer": "Layer C",
            "message": f"Could not parse query for SMT analysis: {exc}",
        }

    # Only single-table queries without joins
    if orig_ast.joins or cand_ast.joins:
        return {
            "status": "not_applicable",
            "proved": False,
            "layer": "Layer C",
            "message": "SMT verification currently supports single-table queries without joins.",
        }

    if not orig_ast.from_table or not cand_ast.from_table:
        return {
            "status": "not_applicable",
            "proved": False,
            "layer": "Layer C",
            "message": "SMT verification requires a FROM table.",
        }

    if orig_ast.from_table.name.casefold() != cand_ast.from_table.name.casefold():
        return {
            "status": "not_applicable",
            "proved": False,
            "layer": "Layer C",
            "message": "Original and candidate queries query different tables.",
        }

    encoder = SMTPredicateEncoder()

    try:
        # Encode original WHERE (default to TRUE if None)
        if orig_ast.where is not None:
            orig_true, _ = encoder.encode(orig_ast.where)
        else:
            orig_true = z3.BoolVal(True)

        # Encode candidate WHERE (default to TRUE if None)
        if cand_ast.where is not None:
            cand_true, _ = encoder.encode(cand_ast.where)
        else:
            cand_true = z3.BoolVal(True)

    except ValueError as exc:
        return {
            "status": "not_applicable",
            "proved": False,
            "layer": "Layer C",
            "message": f"Predicate expression outside supported SMT fragment: {exc}",
        }

    solver = z3.Solver()

    # Add domain constraints / schema CHECK constraints
    table_name = orig_ast.from_table.name.casefold()
    if table_name == "students":
        if "gpa" in encoder.cols_val:
            gpa_val, gpa_null = encoder.cols_val["gpa"], encoder.cols_null["gpa"]
            solver.add(z3.Not(gpa_null))  # gpa NOT NULL
            solver.add(gpa_val >= 0.0, gpa_val <= 10.0)
        if "age" in encoder.cols_val:
            age_val, age_null = encoder.cols_val["age"], encoder.cols_null["age"]
            solver.add(z3.Not(age_null))  # age NOT NULL
            solver.add(age_val >= 16.0, age_val <= 100.0)

    # Assert that there exists a row where original filter and candidate filter differ
    solver.add(orig_true != cand_true)

    result = solver.check()
    if result == z3.unsat:
        return {
            "status": "proved",
            "proved": True,
            "layer": "Layer C",
            "counterexample": None,
            "message": "Z3 proved predicate equivalence under SQL three-valued logic (UNSAT).",
        }
    elif result == z3.sat:
        model = solver.model()
        ce = {}
        for c_name, val_var in encoder.cols_val.items():
            if model[val_var] is not None:
                ce[c_name] = float(model[val_var].as_decimal(3).rstrip("?"))
        return {
            "status": "disproved",
            "proved": False,
            "layer": "Layer C",
            "counterexample": ce,
            "message": f"Z3 found a counterexample row demonstrating non-equivalence: {ce}",
        }
    else:
        return {
            "status": "unknown",
            "proved": False,
            "layer": "Layer C",
            "message": "Z3 solver returned unknown / timeout.",
        }

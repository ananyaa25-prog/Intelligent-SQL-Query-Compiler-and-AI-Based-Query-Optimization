"""AST optimization passes for the SQL compiler."""

from __future__ import annotations

import copy
from typing import Any, Optional

from sqlcompiler.frontend.ast_nodes import (
    SelectStmt, SelectItem, TableRef, Join, OrderByItem,
    Expression, Star, ColumnRef, Literal, BinaryOp, UnaryOp,
    Between, InList, IsNull, FunctionCall, ast_to_sql
)
from sqlcompiler.semantic.symbols import Catalog


class OptimizerPass:
    """Base class for AST transformation passes."""
    name: str = "BasePass"
    description: str = "Base optimizer pass"

    def apply(self, ast: SelectStmt, catalog: Optional[Catalog] = None) -> tuple[SelectStmt, bool]:
        raise NotImplementedError


class ConstantFoldingPass(OptimizerPass):
    """Folds constant arithmetic and literal comparisons."""
    name = "Constant Folding"
    description = "Evaluates compile-time constant arithmetic (e.g. 2+3 -> 5) and comparisons (e.g. 1=1 -> TRUE)."

    def apply(self, ast: SelectStmt, catalog: Optional[Catalog] = None) -> tuple[SelectStmt, bool]:
        new_ast = copy.deepcopy(ast)
        changed = False

        if new_ast.where is not None:
            new_where, w_changed = self._fold_expr(new_ast.where)
            if w_changed:
                new_ast.where = new_where
                changed = True

        new_cols = []
        for item in new_ast.columns:
            new_expr, e_changed = self._fold_expr(item.expr)
            if e_changed:
                new_cols.append(SelectItem(expr=new_expr, alias=item.alias))
                changed = True
            else:
                new_cols.append(item)
        new_ast.columns = new_cols

        return new_ast, changed

    def _fold_expr(self, expr: Expression) -> tuple[Expression, bool]:
        if isinstance(expr, BinaryOp):
            left, l_changed = self._fold_expr(expr.left)
            right, r_changed = self._fold_expr(expr.right)
            changed = l_changed or r_changed

            # If both sides are literals, fold if safe
            if isinstance(left, Literal) and isinstance(right, Literal):
                folded = self._eval_const_binary(expr.op, left, right)
                if folded is not None:
                    return folded, True

            if changed:
                return BinaryOp(op=expr.op, left=left, right=right), True
            return expr, False

        if isinstance(expr, UnaryOp):
            operand, op_changed = self._fold_expr(expr.operand)
            if isinstance(operand, Literal):
                folded = self._eval_const_unary(expr.op, operand)
                if folded is not None:
                    return folded, True
            if op_changed:
                return UnaryOp(op=expr.op, operand=operand), True
            return expr, False

        return expr, False

    def _eval_const_binary(self, op: str, left: Literal, right: Literal) -> Optional[Literal]:
        op = op.upper()
        lv = left.value
        rv = right.value

        # SQL NULL handling
        if lv is None or rv is None:
            if op in ("=", "!=", "<>", "<", "<=", ">", ">="):
                return Literal(value=None, raw="NULL")

        # Arithmetic
        if op in ("+", "-", "*", "/"):
            if isinstance(lv, (int, float)) and isinstance(rv, (int, float)):
                if op == "+":
                    res = lv + rv
                elif op == "-":
                    res = lv - rv
                elif op == "*":
                    res = lv * rv
                elif op == "/":
                    if rv == 0:
                        return None  # Do not fold divide-by-zero
                    res = lv / rv
                return Literal(value=res, raw=str(res))

        # Comparisons
        if op == "=":
            return Literal(value=(lv == rv), raw="TRUE" if lv == rv else "FALSE")
        if op in ("!=", "<>"):
            return Literal(value=(lv != rv), raw="TRUE" if lv != rv else "FALSE")
        if op == "<":
            return Literal(value=(lv < rv), raw="TRUE" if lv < rv else "FALSE")
        if op == "<=":
            return Literal(value=(lv <= rv), raw="TRUE" if lv <= rv else "FALSE")
        if op == ">":
            return Literal(value=(lv > rv), raw="TRUE" if lv > rv else "FALSE")
        if op == ">=":
            return Literal(value=(lv >= rv), raw="TRUE" if lv >= rv else "FALSE")

        return None

    def _eval_const_unary(self, op: str, operand: Literal) -> Optional[Literal]:
        op = op.upper()
        v = operand.value
        if op == "NOT" and isinstance(v, bool):
            return Literal(value=not v, raw="TRUE" if not v else "FALSE")
        if op == "-" and isinstance(v, (int, float)):
            return Literal(value=-v, raw=str(-v))
        if op == "+" and isinstance(v, (int, float)):
            return Literal(value=+v, raw=str(+v))
        return None


class BooleanSimplificationPass(OptimizerPass):
    """Simplifies boolean expressions respecting SQL three-valued logic."""
    name = "Boolean Simplification"
    description = "Simplifies expressions with TRUE/FALSE and double negation (e.g. x AND TRUE -> x, NOT NOT x -> x)."

    def apply(self, ast: SelectStmt, catalog: Optional[Catalog] = None) -> tuple[SelectStmt, bool]:
        if ast.where is None:
            return ast, False

        new_ast = copy.deepcopy(ast)
        new_where, changed = self._simplify(new_ast.where)
        # If WHERE reduced to TRUE, remove WHERE clause entirely
        if isinstance(new_where, Literal) and new_where.value is True:
            new_ast.where = None
            return new_ast, True

        new_ast.where = new_where
        return new_ast, changed

    def _simplify(self, expr: Expression) -> tuple[Expression, bool]:
        if isinstance(expr, UnaryOp) and expr.op.upper() == "NOT":
            inner, inner_changed = self._simplify(expr.operand)
            # NOT NOT x -> x
            if isinstance(inner, UnaryOp) and inner.op.upper() == "NOT":
                return inner.operand, True
            # NOT TRUE -> FALSE, NOT FALSE -> TRUE
            if isinstance(inner, Literal) and isinstance(inner.value, bool):
                return Literal(value=not inner.value, raw="TRUE" if not inner.value else "FALSE"), True
            if inner_changed:
                return UnaryOp(op="NOT", operand=inner), True
            return expr, False

        if isinstance(expr, BinaryOp):
            op = expr.op.upper()
            left, l_changed = self._simplify(expr.left)
            right, r_changed = self._simplify(expr.right)
            changed = l_changed or r_changed

            if op == "AND":
                # x AND TRUE -> x
                if isinstance(right, Literal) and right.value is True:
                    return left, True
                if isinstance(left, Literal) and left.value is True:
                    return right, True
                # x AND FALSE -> FALSE
                if isinstance(right, Literal) and right.value is False:
                    return Literal(value=False, raw="FALSE"), True
                if isinstance(left, Literal) and left.value is False:
                    return Literal(value=False, raw="FALSE"), True
                # Duplicate identical conjuncts: x AND x -> x
                if ast_to_sql(left) == ast_to_sql(right):
                    return left, True

            elif op == "OR":
                # x OR FALSE -> x
                if isinstance(right, Literal) and right.value is False:
                    return left, True
                if isinstance(left, Literal) and left.value is False:
                    return right, True
                # x OR TRUE -> TRUE
                if isinstance(right, Literal) and right.value is True:
                    return Literal(value=True, raw="TRUE"), True
                if isinstance(left, Literal) and left.value is True:
                    return Literal(value=True, raw="TRUE"), True
                # Duplicate identical disjuncts: x OR x -> x
                if ast_to_sql(left) == ast_to_sql(right):
                    return left, True

            if changed:
                return BinaryOp(op=op, left=left, right=right), True
            return expr, False

        return expr, False


class RangePredicateConsolidationPass(OptimizerPass):
    """
    Consolidates redundant range predicates on the same column.
    Handles >, >=, <, <=, =, and BETWEEN on numeric literals.
    """
    name = "Redundant Range Consolidation"
    description = "Removes redundant range predicates on numeric columns (e.g. gpa >= 9.0 AND gpa >= 8.0 -> gpa >= 9.0)."

    def apply(self, ast: SelectStmt, catalog: Optional[Catalog] = None) -> tuple[SelectStmt, bool]:
        if ast.where is None:
            return ast, False

        conjuncts = self._flatten_and(ast.where)
        if len(conjuncts) <= 1:
            return ast, False

        # Group numeric bounds by column
        bounds_by_col: dict[str, list[tuple[int, str, float]]] = {}
        for idx, conj in enumerate(conjuncts):
            col_info = self._extract_numeric_bound(conj)
            if col_info:
                col_name, op, val = col_info
                bounds_by_col.setdefault(col_name.casefold(), []).append((idx, op, val))

        remove_indices = set()
        for col_name, bounds in bounds_by_col.items():
            if len(bounds) < 2:
                continue

            # Consolidate lower bounds (>, >=)
            lower_bounds = [(i, op, v) for i, op, v in bounds if op in (">", ">=")]
            if len(lower_bounds) > 1:
                # Find strongest lower bound
                # Priority: highest value; if equal value, '>' is strictly tighter than '>='
                def lower_key(item):
                    _, op, val = item
                    strictness = 1 if op == ">" else 0
                    return (val, strictness)

                strongest = max(lower_bounds, key=lower_key)
                for item in lower_bounds:
                    if item[0] != strongest[0]:
                        remove_indices.add(item[0])

            # Consolidate upper bounds (<, <=)
            upper_bounds = [(i, op, v) for i, op, v in bounds if op in ("<", "<=")]
            if len(upper_bounds) > 1:
                # Find strongest upper bound
                # Priority: lowest value; if equal value, '<' is strictly tighter than '<='
                def upper_key(item):
                    _, op, val = item
                    strictness = 1 if op == "<" else 0
                    return (-val, strictness)

                strongest = max(upper_bounds, key=upper_key)
                for item in upper_bounds:
                    if item[0] != strongest[0]:
                        remove_indices.add(item[0])

        if not remove_indices:
            return ast, False

        remaining = [c for i, c in enumerate(conjuncts) if i not in remove_indices]
        if not remaining:
            return ast, False

        new_ast = copy.deepcopy(ast)
        new_where = remaining[0]
        for conj in remaining[1:]:
            new_where = BinaryOp(op="AND", left=new_where, right=conj)
        new_ast.where = new_where
        return new_ast, True

    def _flatten_and(self, expr: Expression) -> list[Expression]:
        if isinstance(expr, BinaryOp) and expr.op.upper() == "AND":
            return self._flatten_and(expr.left) + self._flatten_and(expr.right)
        return [expr]

    def _extract_numeric_bound(self, expr: Expression) -> Optional[tuple[str, str, float]]:
        if isinstance(expr, BinaryOp):
            op = expr.op.upper()
            if isinstance(expr.left, ColumnRef) and isinstance(expr.right, Literal):
                if not expr.right.is_string and isinstance(expr.right.value, (int, float)):
                    col_id = f"{expr.left.table}.{expr.left.name}" if expr.left.table else expr.left.name
                    if op in (">", ">=", "<", "<=", "="):
                        return (col_id, op, float(expr.right.value))

            # Handled flipped: 8.0 <= gpa -> gpa >= 8.0
            if isinstance(expr.left, Literal) and isinstance(expr.right, ColumnRef):
                if not expr.left.is_string and isinstance(expr.left.value, (int, float)):
                    col_id = f"{expr.right.table}.{expr.right.name}" if expr.right.table else expr.right.name
                    flipped_ops = {">": "<", ">=": "<=", "<": ">", "<=": ">=", "=": "="}
                    if op in flipped_ops:
                        return (col_id, flipped_ops[op], float(expr.left.value))
        return None


class ContradictionDetectionPass(OptimizerPass):
    """Detects provably contradictory range predicates (e.g. gpa > 9 AND gpa < 5 -> FALSE)."""
    name = "Contradiction Detection"
    description = "Detects provably unsatisfiable range predicates on the same column and rewrites to FALSE."

    def apply(self, ast: SelectStmt, catalog: Optional[Catalog] = None) -> tuple[SelectStmt, bool]:
        if ast.where is None:
            return ast, False

        conjuncts = self._flatten_and(ast.where)
        bounds_by_col: dict[str, list[tuple[str, float]]] = {}

        for conj in conjuncts:
            if isinstance(conj, BinaryOp):
                op = conj.op.upper()
                if isinstance(conj.left, ColumnRef) and isinstance(conj.right, Literal):
                    if not conj.right.is_string and isinstance(conj.right.value, (int, float)):
                        col_id = f"{conj.left.table}.{conj.left.name}" if conj.left.table else conj.left.name
                        if op in (">", ">=", "<", "<=", "="):
                            bounds_by_col.setdefault(col_id.casefold(), []).append((op, float(conj.right.value)))

        has_contradiction = False
        for col_name, bounds in bounds_by_col.items():
            low_vals = [v for op, v in bounds if op in (">", ">=")]
            high_vals = [v for op, v in bounds if op in ("<", "<=")]
            eq_vals = [v for op, v in bounds if op == "="]

            # Contradiction between two different equality requirements: col = 5 AND col = 6
            if len(set(eq_vals)) > 1:
                has_contradiction = True
                break

            # Contradiction between lower and upper bound: e.g. col > 9 AND col < 5
            if low_vals and high_vals:
                max_low = max(low_vals)
                min_high = min(high_vals)
                if max_low > min_high:
                    has_contradiction = True
                    break
                if max_low == min_high:
                    # If both are strict (e.g. col > 5 AND col < 5), contradiction!
                    has_strict_low = any(op == ">" and v == max_low for op, v in bounds)
                    has_strict_high = any(op == "<" and v == min_high for op, v in bounds)
                    if has_strict_low or has_strict_high:
                        has_contradiction = True
                        break

            # Contradiction between eq and bounds
            if eq_vals:
                ev = eq_vals[0]
                if any(ev <= v for op, v in bounds if op == ">"):
                    has_contradiction = True
                    break
                if any(ev < v for op, v in bounds if op == ">="):
                    has_contradiction = True
                    break
                if any(ev >= v for op, v in bounds if op == "<"):
                    has_contradiction = True
                    break
                if any(ev > v for op, v in bounds if op == "<="):
                    has_contradiction = True
                    break

        if has_contradiction:
            new_ast = copy.deepcopy(ast)
            # Rewrite WHERE to FALSE (or 1 = 0)
            new_ast.where = BinaryOp(
                op="=",
                left=Literal(value=1, raw="1"),
                right=Literal(value=0, raw="0")
            )
            return new_ast, True

        return ast, False

    def _flatten_and(self, expr: Expression) -> list[Expression]:
        if isinstance(expr, BinaryOp) and expr.op.upper() == "AND":
            return self._flatten_and(expr.left) + self._flatten_and(expr.right)
        return [expr]


class RedundantDistinctRemovalPass(OptimizerPass):
    """Removes DISTINCT when the select list includes the table's primary key."""
    name = "Redundant DISTINCT Removal"
    description = "Removes DISTINCT when projected columns include the single table's primary key."

    def apply(self, ast: SelectStmt, catalog: Optional[Catalog] = None) -> tuple[SelectStmt, bool]:
        if not ast.distinct or not ast.from_table or ast.joins or not catalog:
            return ast, False

        tbl_sym = catalog.tables.get(ast.from_table.name.casefold())
        if not tbl_sym or not tbl_sym.primary_key:
            return ast, False

        pk_set = {pk.casefold() for pk in tbl_sym.primary_key}

        # Check if all PK columns are present in SELECT items
        selected_cols = set()
        for item in ast.columns:
            if isinstance(item.expr, ColumnRef):
                selected_cols.add(item.expr.name.casefold())
            elif isinstance(item.expr, Star):
                # Star includes PK
                selected_cols.update(pk_set)

        if pk_set.issubset(selected_cols):
            new_ast = copy.deepcopy(ast)
            new_ast.distinct = False
            return new_ast, True

        return ast, False


class SelectStarExpansionPass(OptimizerPass):
    """Expands SELECT * into explicit columns using the catalog."""
    name = "SELECT * Expansion"
    description = "Expands wildcard '*' into explicit column names for catalog visibility."

    def apply(self, ast: SelectStmt, catalog: Optional[Catalog] = None) -> tuple[SelectStmt, bool]:
        if not catalog or not ast.from_table:
            return ast, False

        has_star = any(isinstance(item.expr, Star) for item in ast.columns)
        if not has_star:
            return ast, False

        tbl_sym = catalog.tables.get(ast.from_table.name.casefold())
        if not tbl_sym:
            return ast, False

        new_cols: list[SelectItem] = []
        changed = False

        for item in ast.columns:
            if isinstance(item.expr, Star):
                changed = True
                tbl_name = item.expr.table or ast.from_table.alias or ast.from_table.name
                target_sym = catalog.tables.get(ast.from_table.name.casefold())
                if target_sym:
                    for col_name in target_sym.columns.values():
                        new_cols.append(SelectItem(
                            expr=ColumnRef(name=col_name.name, table=tbl_name if ast.joins else None)
                        ))
            else:
                new_cols.append(item)

        if changed:
            new_ast = copy.deepcopy(ast)
            new_ast.columns = new_cols
            return new_ast, True

        return ast, False


class PredicatePushdownPass(OptimizerPass):
    """Moves single-table WHERE conjuncts below an INNER JOIN."""
    name = "Predicate Pushdown"
    description = "Pushes single-table filters below INNER joins into join conditions where equivalent."

    def apply(self, ast: SelectStmt, catalog: Optional[Catalog] = None) -> tuple[SelectStmt, bool]:
        if not ast.joins or ast.where is None:
            return ast, False

        # Only valid for INNER joins
        if any(j.join_type.upper() != "INNER" for j in ast.joins):
            return ast, False

        conjuncts = self._flatten_and(ast.where)
        if not conjuncts:
            return ast, False

        # Determine which tables each conjunct references
        table_aliases = {}
        if ast.from_table:
            table_aliases[ast.from_table.alias or ast.from_table.name] = ast.from_table.name
        for j in ast.joins:
            table_aliases[j.table.alias or j.table.name] = j.table.name

        pushed_indices = set()
        new_joins = copy.deepcopy(ast.joins)

        for i, conj in enumerate(conjuncts):
            refs = self._collect_table_refs(conj)
            if len(refs) == 1:
                ref_tbl = next(iter(refs))
                # Check if this matches a joined table
                for j_idx, join in enumerate(new_joins):
                    join_ref = join.table.alias or join.table.name
                    if ref_tbl.casefold() == join_ref.casefold():
                        # Push this conjunct into join.on
                        join.on = BinaryOp(op="AND", left=join.on, right=conj)
                        pushed_indices.add(i)
                        break

        if not pushed_indices:
            return ast, False

        remaining_where = [c for i, c in enumerate(conjuncts) if i not in pushed_indices]
        new_ast = copy.deepcopy(ast)
        new_ast.joins = new_joins
        if remaining_where:
            new_w = remaining_where[0]
            for c in remaining_where[1:]:
                new_w = BinaryOp(op="AND", left=new_w, right=c)
            new_ast.where = new_w
        else:
            new_ast.where = None

        return new_ast, True

    def _flatten_and(self, expr: Expression) -> list[Expression]:
        if isinstance(expr, BinaryOp) and expr.op.upper() == "AND":
            return self._flatten_and(expr.left) + self._flatten_and(expr.right)
        return [expr]

    def _collect_table_refs(self, expr: Expression) -> set[str]:
        refs = set()
        if isinstance(expr, ColumnRef) and expr.table:
            refs.add(expr.table)
        elif isinstance(expr, BinaryOp):
            refs.update(self._collect_table_refs(expr.left))
            refs.update(self._collect_table_refs(expr.right))
        elif isinstance(expr, UnaryOp):
            refs.update(self._collect_table_refs(expr.operand))
        return refs


class InAndBetweenNormalizationPass(OptimizerPass):
    """Simplifies single-element IN lists into equality (e.g. x IN (5) -> x = 5)."""
    name = "IN / BETWEEN Normalization"
    description = "Normalizes single-value IN lists to equality comparisons (e.g. id IN (1) -> id = 1)."

    def apply(self, ast: SelectStmt, catalog: Optional[Catalog] = None) -> tuple[SelectStmt, bool]:
        if ast.where is None:
            return ast, False

        new_ast = copy.deepcopy(ast)
        new_where, changed = self._normalize(new_ast.where)
        if changed:
            new_ast.where = new_where
            return new_ast, True
        return ast, False

    def _normalize(self, expr: Expression) -> tuple[Expression, bool]:
        if isinstance(expr, InList) and len(expr.values) == 1 and not expr.not_in:
            return BinaryOp(op="=", left=expr.expr, right=expr.values[0]), True

        if isinstance(expr, BinaryOp):
            l, lc = self._normalize(expr.left)
            r, rc = self._normalize(expr.right)
            if lc or rc:
                return BinaryOp(op=expr.op, left=l, right=r), True

        if isinstance(expr, UnaryOp):
            op, oc = self._normalize(expr.operand)
            if oc:
                return UnaryOp(op=expr.op, operand=op), True

        return expr, False

"""Semantic analyzer and type checker for SQL AST."""

from __future__ import annotations

import difflib
from typing import Any, Optional

from sqlcompiler.frontend.ast_nodes import (
    SelectStmt, SelectItem, TableRef, Join, OrderByItem,
    Expression, Star, ColumnRef, Literal, BinaryOp, UnaryOp,
    Between, InList, IsNull, FunctionCall
)
from sqlcompiler.semantic.symbols import Catalog, Scope, ColumnSymbol
from sqlcompiler.semantic.diagnostics import Diagnostic


class SemanticAnalyzer:
    """Type checker and semantic validator for SQL SELECT queries."""

    def __init__(self, catalog: Catalog):
        self.catalog = catalog
        self.diagnostics: list[Diagnostic] = []

    def add_error(self, code: str, message: str, line: int = 1, column: int = 1, hint: Optional[str] = None):
        self.diagnostics.append(Diagnostic(
            severity="ERROR",
            code=code,
            message=message,
            line=line,
            column=column,
            hint=hint,
        ))

    def add_warning(self, code: str, message: str, line: int = 1, column: int = 1, hint: Optional[str] = None):
        self.diagnostics.append(Diagnostic(
            severity="WARNING",
            code=code,
            message=message,
            line=line,
            column=column,
            hint=hint,
        ))

    def analyze(self, ast: SelectStmt, raw_sql: str = "") -> dict[str, Any]:
        """Validate query AST against catalog metadata and annotate inferred types."""
        self.diagnostics.clear()
        scope = Scope(self.catalog)

        # 1. Resolve FROM and JOIN tables into scope
        if ast.from_table:
            t_key = ast.from_table.name.casefold()
            if t_key not in self.catalog.tables:
                all_tables = sorted(self.catalog.tables.keys())
                matches = difflib.get_close_matches(t_key, all_tables, n=1, cutoff=0.6)
                hint = f"Did you mean '{matches[0]}'?" if matches else f"Available tables: {', '.join(all_tables)}."
                self.add_error("E101", f"Unknown table '{ast.from_table.name}'.", line=ast.from_table.line, column=ast.from_table.column, hint=hint)
            else:
                scope.add_table(ast.from_table.name, ast.from_table.alias)

        for join in ast.joins:
            j_key = join.table.name.casefold()
            if j_key not in self.catalog.tables:
                all_tables = sorted(self.catalog.tables.keys())
                matches = difflib.get_close_matches(j_key, all_tables, n=1, cutoff=0.6)
                hint = f"Did you mean '{matches[0]}'?" if matches else f"Available tables: {', '.join(all_tables)}."
                self.add_error("E101", f"Unknown table '{join.table.name}' in JOIN.", line=join.table.line, column=join.table.column, hint=hint)
            else:
                scope.add_table(join.table.name, join.table.alias)

        # Check JOIN ON expressions
        for join in ast.joins:
            self._typecheck_expr(join.on, scope, allow_agg=False)

        # 2. Check SELECT items and collect column aliases
        has_aggregate_in_select = False
        non_aggregated_columns: list[ColumnRef] = []

        for item in ast.columns:
            expr_type = self._typecheck_expr(item.expr, scope, allow_agg=True)
            if item.alias:
                scope.column_aliases[item.alias.casefold()] = expr_type

            # Check if this item is an aggregate
            is_agg = self._has_aggregate(item.expr)
            if is_agg:
                has_aggregate_in_select = True
            elif not isinstance(item.expr, Star):
                # Collect non-aggregated column references
                col_refs = self._collect_column_refs(item.expr)
                for cr in col_refs:
                    non_aggregated_columns.append(cr)

        # 3. Check WHERE clause
        if ast.where is not None:
            w_type = self._typecheck_expr(ast.where, scope, allow_agg=False)

        # 4. Check GROUP BY and enforce GROUP BY rule
        group_by_cols: set[str] = set()
        for g_expr in ast.group_by:
            self._typecheck_expr(g_expr, scope, allow_agg=False)
            for cr in self._collect_column_refs(g_expr):
                group_by_cols.add(cr.name.casefold())

        if ast.group_by or has_aggregate_in_select:
            # When GROUP BY or aggregates are used, non-aggregated select columns must appear in GROUP BY
            for cr in non_aggregated_columns:
                if cr.name.casefold() not in group_by_cols:
                    self.add_error(
                        "E402",
                        f"Non-aggregated column '{cr.name}' in SELECT list must appear in GROUP BY.",
                        line=cr.line,
                        column=cr.column,
                        hint=f"Add '{cr.name}' to GROUP BY clause or wrap it in an aggregate function."
                    )

        # 5. Check HAVING clause
        if ast.having is not None:
            self._typecheck_expr(ast.having, scope, allow_agg=True)
            # In standard SQL, HAVING expressions must either be aggregates or be in GROUP BY
            having_cols = self._collect_column_refs_outside_agg(ast.having)
            for hc in having_cols:
                if hc.name.casefold() not in group_by_cols:
                    self.add_error(
                        "E403",
                        f"Column '{hc.name}' in HAVING must be in GROUP BY or wrapped in an aggregate.",
                        line=hc.line,
                        column=hc.column,
                        hint=f"Wrap '{hc.name}' in an aggregate or add it to GROUP BY."
                    )

        # 6. Check ORDER BY clause
        for ob in ast.order_by:
            self._typecheck_expr(ob.expr, scope, allow_agg=True, allow_col_alias=True)

        # 7. Check LIMIT
        if ast.limit is not None and ast.limit < 0:
            self.add_error("E501", "LIMIT must be a non-negative integer.", line=ast.line, column=ast.column, hint="Provide 0 or a positive integer.")

        valid = not any(d.severity == "ERROR" for d in self.diagnostics)
        first_err = next((d for d in self.diagnostics if d.severity == "ERROR"), None)

        return {
            "valid": valid,
            "error": first_err.format(raw_sql) if first_err else None,
            "error_message": first_err.message if first_err else None,
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "annotated_ast": ast,
        }

    def _typecheck_expr(
        self,
        expr: Expression,
        scope: Scope,
        allow_agg: bool = True,
        allow_col_alias: bool = False
    ) -> str:
        """Recursively infer and validate types for an expression."""
        if isinstance(expr, Star):
            expr.inferred_type = "RECORD"
            return "RECORD"

        if isinstance(expr, Literal):
            if expr.value is None:
                t = "NULL"
            elif isinstance(expr.value, bool):
                t = "BOOLEAN"
            elif expr.is_string or isinstance(expr.value, str):
                t = "TEXT"
            elif isinstance(expr.value, int):
                t = "INTEGER"
            elif isinstance(expr.value, float):
                t = "REAL"
            else:
                t = "UNKNOWN"
            expr.inferred_type = t
            return t

        if isinstance(expr, ColumnRef):
            # Check if this resolves to a column alias in ORDER BY
            if allow_col_alias and not expr.table and expr.name.casefold() in scope.column_aliases:
                t = scope.column_aliases[expr.name.casefold()]
                expr.inferred_type = t
                return t

            sym, resolved_tbl, err = scope.resolve_column(expr.name, expr.table)
            if err:
                # Offer fuzzy matching suggestion if column not found
                all_avail_cols: list[str] = []
                for t_key in scope.available_tables:
                    ts = self.catalog.tables.get(t_key)
                    if ts:
                        all_avail_cols.extend(ts.columns.keys())
                matches = difflib.get_close_matches(expr.name.casefold(), all_avail_cols, n=1, cutoff=0.55)
                hint = f"Did you mean '{matches[0]}'?" if matches else None
                self.add_error("E102", err, line=expr.line, column=expr.column, hint=hint)
                expr.inferred_type = "UNKNOWN"
                return "UNKNOWN"

            t = sym.canonical_type if sym else "UNKNOWN"
            expr.inferred_type = t
            return t

        if isinstance(expr, FunctionCall):
            func_name = expr.name.upper()
            if not allow_agg and func_name in ("COUNT", "SUM", "AVG", "MIN", "MAX"):
                self.add_error("E401", f"Aggregate function '{func_name}' is not allowed in this context.", line=expr.line, column=expr.column, hint="Aggregates belong in SELECT or HAVING, not WHERE.")

            # Typecheck function arguments
            arg_types = [self._typecheck_expr(arg, scope, allow_agg=False) for arg in expr.args]

            if func_name == "COUNT":
                ret_type = "INTEGER"
            elif func_name in ("SUM", "AVG"):
                if arg_types and arg_types[0] == "TEXT":
                    self.add_error(
                        "E301",
                        f"Cannot compute {func_name} on TEXT column.",
                        line=expr.line,
                        column=expr.column,
                        hint=f"{func_name} requires a numeric (INTEGER or REAL) column."
                    )
                ret_type = "REAL" if func_name == "AVG" else (arg_types[0] if arg_types else "REAL")
            elif func_name in ("MIN", "MAX"):
                ret_type = arg_types[0] if arg_types else "UNKNOWN"
            else:
                ret_type = "UNKNOWN"

            expr.inferred_type = ret_type
            return ret_type

        if isinstance(expr, BinaryOp):
            left_t = self._typecheck_expr(expr.left, scope, allow_agg=allow_agg, allow_col_alias=allow_col_alias)
            right_t = self._typecheck_expr(expr.right, scope, allow_agg=allow_agg, allow_col_alias=allow_col_alias)

            op = expr.op.upper()

            # Logical operators
            if op in ("AND", "OR"):
                expr.inferred_type = "BOOLEAN"
                return "BOOLEAN"

            # Arithmetic operators
            if op in ("+", "-", "*", "/"):
                if left_t == "TEXT" or right_t == "TEXT":
                    self.add_error(
                        "E302",
                        f"Arithmetic operator '{op}' cannot be applied to TEXT operand ({left_t} {op} {right_t}).",
                        line=expr.line,
                        column=expr.column,
                        hint="Arithmetic operations require numeric operands."
                    )
                if op == "/" or left_t == "REAL" or right_t == "REAL":
                    res_t = "REAL"
                else:
                    res_t = "INTEGER"
                expr.inferred_type = res_t
                return res_t

            # Comparison operators
            if op in ("=", "!=", "<>", "<", "<=", ">", ">=", "LIKE"):
                # Check for comparison type mismatch (numeric vs string)
                if left_t != "UNKNOWN" and right_t != "UNKNOWN":
                    is_left_num = left_t in ("INTEGER", "REAL")
                    is_right_num = right_t in ("INTEGER", "REAL")
                    if (is_left_num and right_t == "TEXT") or (left_t == "TEXT" and is_right_num):
                        self.add_error(
                            "E303",
                            f"Type mismatch in comparison '{op}': cannot compare numeric ({left_t}) with string ({right_t}).",
                            line=expr.line,
                            column=expr.column,
                            hint="Ensure both sides of the comparison have compatible types."
                        )
                expr.inferred_type = "BOOLEAN"
                return "BOOLEAN"

            expr.inferred_type = "UNKNOWN"
            return "UNKNOWN"

        if isinstance(expr, UnaryOp):
            operand_t = self._typecheck_expr(expr.operand, scope, allow_agg=allow_agg)
            op = expr.op.upper()
            if op == "NOT":
                expr.inferred_type = "BOOLEAN"
                return "BOOLEAN"
            if op in ("+", "-"):
                if operand_t == "TEXT":
                    self.add_error("E302", f"Unary '{op}' cannot be applied to TEXT.", line=expr.line, column=expr.column)
                expr.inferred_type = operand_t
                return operand_t

        if isinstance(expr, Between):
            e_t = self._typecheck_expr(expr.expr, scope, allow_agg=allow_agg)
            l_t = self._typecheck_expr(expr.low, scope, allow_agg=allow_agg)
            h_t = self._typecheck_expr(expr.high, scope, allow_agg=allow_agg)
            if e_t in ("INTEGER", "REAL") and (l_t == "TEXT" or h_t == "TEXT"):
                self.add_error("E303", "Type mismatch in BETWEEN: cannot compare numeric column with text bounds.", line=expr.line, column=expr.column)
            expr.inferred_type = "BOOLEAN"
            return "BOOLEAN"

        if isinstance(expr, InList):
            e_t = self._typecheck_expr(expr.expr, scope, allow_agg=allow_agg)
            for val in expr.values:
                v_t = self._typecheck_expr(val, scope, allow_agg=allow_agg)
                if e_t in ("INTEGER", "REAL") and v_t == "TEXT":
                    self.add_error("E303", "Type mismatch in IN list: cannot compare numeric column with string literal.", line=expr.line, column=expr.column)
            expr.inferred_type = "BOOLEAN"
            return "BOOLEAN"

        if isinstance(expr, IsNull):
            self._typecheck_expr(expr.expr, scope, allow_agg=allow_agg)
            expr.inferred_type = "BOOLEAN"
            return "BOOLEAN"

        return "UNKNOWN"

    def _has_aggregate(self, expr: Expression) -> bool:
        if isinstance(expr, FunctionCall) and expr.name.upper() in ("COUNT", "SUM", "AVG", "MIN", "MAX"):
            return True
        if isinstance(expr, BinaryOp):
            return self._has_aggregate(expr.left) or self._has_aggregate(expr.right)
        if isinstance(expr, UnaryOp):
            return self._has_aggregate(expr.operand)
        if isinstance(expr, Between):
            return (
                self._has_aggregate(expr.expr)
                or self._has_aggregate(expr.low)
                or self._has_aggregate(expr.high)
            )
        if isinstance(expr, InList):
            return self._has_aggregate(expr.expr) or any(self._has_aggregate(v) for v in expr.values)
        if isinstance(expr, IsNull):
            return self._has_aggregate(expr.expr)
        return False

    def _collect_column_refs(self, expr: Expression) -> list[ColumnRef]:
        refs = []
        if isinstance(expr, ColumnRef):
            refs.append(expr)
        elif isinstance(expr, BinaryOp):
            refs.extend(self._collect_column_refs(expr.left))
            refs.extend(self._collect_column_refs(expr.right))
        elif isinstance(expr, UnaryOp):
            refs.extend(self._collect_column_refs(expr.operand))
        elif isinstance(expr, FunctionCall):
            for a in expr.args:
                refs.extend(self._collect_column_refs(a))
        elif isinstance(expr, Between):
            refs.extend(self._collect_column_refs(expr.expr))
            refs.extend(self._collect_column_refs(expr.low))
            refs.extend(self._collect_column_refs(expr.high))
        elif isinstance(expr, InList):
            refs.extend(self._collect_column_refs(expr.expr))
            for v in expr.values:
                refs.extend(self._collect_column_refs(v))
        elif isinstance(expr, IsNull):
            refs.extend(self._collect_column_refs(expr.expr))
        return refs

    def _collect_column_refs_outside_agg(self, expr: Expression) -> list[ColumnRef]:
        if isinstance(expr, FunctionCall) and expr.name.upper() in ("COUNT", "SUM", "AVG", "MIN", "MAX"):
            return []
        if isinstance(expr, ColumnRef):
            return [expr]
        refs = []
        if isinstance(expr, BinaryOp):
            refs.extend(self._collect_column_refs_outside_agg(expr.left))
            refs.extend(self._collect_column_refs_outside_agg(expr.right))
        elif isinstance(expr, UnaryOp):
            refs.extend(self._collect_column_refs_outside_agg(expr.operand))
        return refs

"""Relational algebra Intermediate Representation (IR), text/DOT renderer, and cost model."""

from __future__ import annotations

import itertools
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from sqlcompiler.frontend.ast_nodes import (
    SelectStmt, SelectItem, TableRef, Join, OrderByItem,
    Expression, ColumnRef, Literal, BinaryOp, UnaryOp,
    Between, InList, IsNull, FunctionCall, Star, ast_to_sql
)
from sqlcompiler.semantic.symbols import Catalog


@dataclass
class AlgebraNode:
    """Base class for relational algebra operators."""
    estimated_rows: float = 0.0
    cost: float = 0.0

    def to_text(self, indent: int = 0) -> str:
        raise NotImplementedError

    def to_dot(self, graph: Optional[list[str]] = None, parent_id: Optional[str] = None) -> str:
        if graph is None:
            graph = ["digraph AlgebraIR {", '  node [shape=box, fontname="Courier", style="rounded,filled", fillcolor="#e3f2fd"];']
            self._render_dot(graph, str(id(self)), None)
            graph.append("}")
            return "\n".join(graph)
        self._render_dot(graph, str(id(self)), parent_id)
        return ""

    def _render_dot(self, graph: list[str], my_id: str, parent_id: Optional[str]) -> None:
        raise NotImplementedError


@dataclass
class Scan(AlgebraNode):
    table_name: str = ""
    alias: Optional[str] = None

    def to_text(self, indent: int = 0) -> str:
        pad = "  " * indent
        tbl = f"{self.table_name} AS {self.alias}" if self.alias else self.table_name
        return f"{pad}Scan({tbl}) [est. rows: {self.estimated_rows:g}, cost: {self.cost:g}]"

    def _render_dot(self, graph: list[str], my_id: str, parent_id: Optional[str]) -> None:
        tbl = f"{self.table_name} AS {self.alias}" if self.alias else self.table_name
        lbl = f"Scan: {tbl}\\n[rows: {self.estimated_rows:g}, cost: {self.cost:g}]"
        graph.append(f'  "{my_id}" [label="{lbl}", fillcolor="#c8e6c9"];')
        if parent_id is not None:
            graph.append(f'  "{parent_id}" -> "{my_id}";')


@dataclass
class Select(AlgebraNode):
    input_node: AlgebraNode = field(default_factory=AlgebraNode)
    predicate: Expression = field(default_factory=Expression)

    def to_text(self, indent: int = 0) -> str:
        pad = "  " * indent
        pred_sql = ast_to_sql(self.predicate)
        header = f"{pad}Select(sigma {pred_sql}) [est. rows: {self.estimated_rows:g}, cost: {self.cost:g}]"
        child = self.input_node.to_text(indent + 1)
        return f"{header}\n{child}"

    def _render_dot(self, graph: list[str], my_id: str, parent_id: Optional[str]) -> None:
        pred_sql = ast_to_sql(self.predicate).replace('"', '\\"')
        lbl = f"Select (sigma)\\n{pred_sql}\\n[rows: {self.estimated_rows:g}, cost: {self.cost:g}]"
        graph.append(f'  "{my_id}" [label="{lbl}", fillcolor="#ffcdd2"];')
        if parent_id is not None:
            graph.append(f'  "{parent_id}" -> "{my_id}";')
        self.input_node._render_dot(graph, f"{my_id}_c", my_id)


@dataclass
class Project(AlgebraNode):
    input_node: AlgebraNode = field(default_factory=AlgebraNode)
    columns: list[SelectItem] = field(default_factory=list)

    def to_text(self, indent: int = 0) -> str:
        pad = "  " * indent
        cols = ", ".join(c.to_sql() for c in self.columns)
        header = f"{pad}Project(pi {cols}) [est. rows: {self.estimated_rows:g}, cost: {self.cost:g}]"
        child = self.input_node.to_text(indent + 1)
        return f"{header}\n{child}"

    def _render_dot(self, graph: list[str], my_id: str, parent_id: Optional[str]) -> None:
        cols = ", ".join(c.to_sql() for c in self.columns).replace('"', '\\"')
        lbl = f"Project (pi)\\n{cols}\\n[rows: {self.estimated_rows:g}, cost: {self.cost:g}]"
        graph.append(f'  "{my_id}" [label="{lbl}", fillcolor="#b2dfdb"];')
        if parent_id is not None:
            graph.append(f'  "{parent_id}" -> "{my_id}";')
        self.input_node._render_dot(graph, f"{my_id}_c", my_id)


@dataclass
class JoinNode(AlgebraNode):
    left: AlgebraNode = field(default_factory=AlgebraNode)
    right: AlgebraNode = field(default_factory=AlgebraNode)
    join_type: str = "INNER"
    on: Expression = field(default_factory=Expression)

    def to_text(self, indent: int = 0) -> str:
        pad = "  " * indent
        on_sql = ast_to_sql(self.on)
        header = f"{pad}Join({self.join_type} ON {on_sql}) [est. rows: {self.estimated_rows:g}, cost: {self.cost:g}]"
        l_text = self.left.to_text(indent + 1)
        r_text = self.right.to_text(indent + 1)
        return f"{header}\n{l_text}\n{r_text}"

    def _render_dot(self, graph: list[str], my_id: str, parent_id: Optional[str]) -> None:
        on_sql = ast_to_sql(self.on).replace('"', '\\"')
        lbl = f"Join ({self.join_type})\\nON {on_sql}\\n[rows: {self.estimated_rows:g}, cost: {self.cost:g}]"
        graph.append(f'  "{my_id}" [label="{lbl}", fillcolor="#d1c4e9"];')
        if parent_id is not None:
            graph.append(f'  "{parent_id}" -> "{my_id}";')
        self.left._render_dot(graph, f"{my_id}_l", my_id)
        self.right._render_dot(graph, f"{my_id}_r", my_id)


@dataclass
class AggregateNode(AlgebraNode):
    input_node: AlgebraNode = field(default_factory=AlgebraNode)
    group_by: list[Expression] = field(default_factory=list)
    aggregates: list[FunctionCall] = field(default_factory=list)

    def to_text(self, indent: int = 0) -> str:
        pad = "  " * indent
        gb = ", ".join(ast_to_sql(g) for g in self.group_by)
        header = f"{pad}Aggregate(gamma GROUP BY {gb}) [est. rows: {self.estimated_rows:g}, cost: {self.cost:g}]"
        child = self.input_node.to_text(indent + 1)
        return f"{header}\n{child}"

    def _render_dot(self, graph: list[str], my_id: str, parent_id: Optional[str]) -> None:
        gb = ", ".join(ast_to_sql(g) for g in self.group_by).replace('"', '\\"')
        lbl = f"Aggregate (gamma)\\nGROUP BY: {gb}\\n[rows: {self.estimated_rows:g}, cost: {self.cost:g}]"
        graph.append(f'  "{my_id}" [label="{lbl}", fillcolor="#ffe0b2"];')
        if parent_id is not None:
            graph.append(f'  "{parent_id}" -> "{my_id}";')
        self.input_node._render_dot(graph, f"{my_id}_c", my_id)



@dataclass
class SortNode(AlgebraNode):
    input_node: AlgebraNode = field(default_factory=AlgebraNode)
    order_by: list[OrderByItem] = field(default_factory=list)

    def to_text(self, indent: int = 0) -> str:
        pad = "  " * indent
        ob = ", ".join(o.to_sql() for o in self.order_by)
        header = f"{pad}Sort(ORDER BY {ob}) [est. rows: {self.estimated_rows:g}, cost: {self.cost:g}]"
        child = self.input_node.to_text(indent + 1)
        return f"{header}\n{child}"

    def _render_dot(self, graph: list[str], my_id: str, parent_id: Optional[str]) -> None:
        ob = ", ".join(o.to_sql() for o in self.order_by).replace('"', '\\"')
        lbl = f"Sort\\nORDER BY: {ob}\\n[rows: {self.estimated_rows:g}, cost: {self.cost:g}]"
        graph.append(f'  "{my_id}" [label="{lbl}", fillcolor="#f8bbd0"];')
        if parent_id is not None:
            graph.append(f'  "{parent_id}" -> "{my_id}";')
        self.input_node._render_dot(graph, f"{my_id}_c", my_id)


@dataclass
class LimitNode(AlgebraNode):
    input_node: AlgebraNode = field(default_factory=AlgebraNode)
    limit: int = 0
    offset: Optional[int] = None

    def to_text(self, indent: int = 0) -> str:
        pad = "  " * indent
        off = f" OFFSET {self.offset}" if self.offset else ""
        header = f"{pad}Limit(LIMIT {self.limit}{off}) [est. rows: {self.estimated_rows:g}, cost: {self.cost:g}]"
        child = self.input_node.to_text(indent + 1)
        return f"{header}\n{child}"

    def _render_dot(self, graph: list[str], my_id: str, parent_id: Optional[str]) -> None:
        off = f" OFFSET {self.offset}" if self.offset else ""
        lbl = f"Limit: {self.limit}{off}\\n[rows: {self.estimated_rows:g}, cost: {self.cost:g}]"
        graph.append(f'  "{my_id}" [label="{lbl}", fillcolor="#cfd8dc"];')
        if parent_id is not None:
            graph.append(f'  "{parent_id}" -> "{my_id}";')
        self.input_node._render_dot(graph, f"{my_id}_c", my_id)


@dataclass
class DistinctNode(AlgebraNode):
    input_node: AlgebraNode = field(default_factory=AlgebraNode)

    def to_text(self, indent: int = 0) -> str:
        pad = "  " * indent
        header = f"{pad}Distinct() [est. rows: {self.estimated_rows:g}, cost: {self.cost:g}]"
        child = self.input_node.to_text(indent + 1)
        return f"{header}\n{child}"

    def _render_dot(self, graph: list[str], my_id: str, parent_id: Optional[str]) -> None:
        lbl = f"Distinct\\n[rows: {self.estimated_rows:g}, cost: {self.cost:g}]"
        graph.append(f'  "{my_id}" [label="{lbl}", fillcolor="#e1bee7"];')
        if parent_id is not None:
            graph.append(f'  "{parent_id}" -> "{my_id}";')
        self.input_node._render_dot(graph, f"{my_id}_c", my_id)


# --- Cost Model and Lowering ---

DEFAULT_TABLE_ROWS = {
    "students": 1000.0,
    "courses": 10.0,
    "enrollments": 3000.0,
}


def get_table_cardinality(table_name: str, db_path: Optional[Path] = None) -> float:
    """Read actual row count from SQLite or fall back to default stats."""
    t_key = table_name.casefold()
    if db_path and db_path.exists():
        try:
            uri = f"{db_path.resolve().as_uri()}?mode=ro"
            with sqlite3.connect(uri, uri=True) as conn:
                row = conn.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()
                if row:
                    return float(row[0])
        except Exception:
            pass
    return DEFAULT_TABLE_ROWS.get(t_key, 100.0)


def estimate_selectivity(expr: Expression) -> float:
    """Estimate filter selectivity in [0.0, 1.0]. Clearly marked as estimate."""
    if isinstance(expr, BinaryOp):
        op = expr.op.upper()
        if op == "AND":
            return estimate_selectivity(expr.left) * estimate_selectivity(expr.right)
        if op == "OR":
            s1 = estimate_selectivity(expr.left)
            s2 = estimate_selectivity(expr.right)
            return s1 + s2 - (s1 * s2)
        if op == "=":
            return 0.1
        if op in ("<", "<=", ">", ">="):
            return 0.33
        if op in ("!=", "<>"):
            return 0.9
        if op == "LIKE":
            return 0.2
    if isinstance(expr, UnaryOp) and expr.op.upper() == "NOT":
        return max(0.0, 1.0 - estimate_selectivity(expr.operand))
    if isinstance(expr, Between):
        return 0.25
    if isinstance(expr, InList):
        return min(0.8, 0.1 * len(expr.values))
    if isinstance(expr, IsNull):
        return 0.05
    return 0.5


def lower_ast_to_algebra(
    ast: SelectStmt,
    catalog: Optional[Catalog] = None,
    db_path: Optional[Path] = None
) -> AlgebraNode:
    """Lower a SelectStmt AST to a cost-annotated relational algebra tree."""
    # 1. Base Scan
    if not ast.from_table:
        # Dummy single-row scan (e.g. SELECT 1)
        root = Scan(table_name="dual", estimated_rows=1.0, cost=1.0)
    else:
        t_name = ast.from_table.name
        rows = get_table_cardinality(t_name, db_path)
        root = Scan(
            table_name=t_name,
            alias=ast.from_table.alias,
            estimated_rows=rows,
            cost=rows,
        )

    # 2. Joins
    for join in ast.joins:
        j_name = join.table.name
        j_rows = get_table_cardinality(j_name, db_path)
        scan_right = Scan(
            table_name=j_name,
            alias=join.table.alias,
            estimated_rows=j_rows,
            cost=j_rows,
        )
        # Check PK-FK pattern heuristic
        est_out_rows = max(root.estimated_rows, j_rows)
        join_cost = root.cost + scan_right.cost + (root.estimated_rows * j_rows * 0.001)
        root = JoinNode(
            left=root,
            right=scan_right,
            join_type=join.join_type,
            on=join.on,
            estimated_rows=est_out_rows,
            cost=join_cost,
        )

    # 3. Where Selection (σ)
    if ast.where is not None:
        sel = estimate_selectivity(ast.where)
        out_rows = max(1.0, root.estimated_rows * sel)
        cost = root.cost + root.estimated_rows
        root = Select(
            input_node=root,
            predicate=ast.where,
            estimated_rows=out_rows,
            cost=cost,
        )

    # 4. Aggregation (γ)
    aggs = [item.expr for item in ast.columns if isinstance(item.expr, FunctionCall)]
    if ast.group_by or aggs:
        out_rows = max(1.0, root.estimated_rows * 0.2) if ast.group_by else 1.0
        cost = root.cost + root.estimated_rows * 1.5
        root = AggregateNode(
            input_node=root,
            group_by=ast.group_by,
            aggregates=aggs,
            estimated_rows=out_rows,
            cost=cost,
        )

    # 5. Having (σ)
    if ast.having is not None:
        sel = estimate_selectivity(ast.having)
        out_rows = max(1.0, root.estimated_rows * sel)
        cost = root.cost + root.estimated_rows
        root = Select(
            input_node=root,
            predicate=ast.having,
            estimated_rows=out_rows,
            cost=cost,
        )

    # 6. Distinct
    if ast.distinct:
        out_rows = max(1.0, root.estimated_rows * 0.8)
        cost = root.cost + root.estimated_rows * 2.0
        root = DistinctNode(
            input_node=root,
            estimated_rows=out_rows,
            cost=cost,
        )

    # 7. Sort
    if ast.order_by:
        cost = root.cost + root.estimated_rows * 2.5
        root = SortNode(
            input_node=root,
            order_by=ast.order_by,
            estimated_rows=root.estimated_rows,
            cost=cost,
        )

    # 8. Limit
    if ast.limit is not None:
        out_rows = min(float(ast.limit), root.estimated_rows)
        root = LimitNode(
            input_node=root,
            limit=ast.limit,
            offset=ast.offset,
            estimated_rows=out_rows,
            cost=root.cost,
        )

    # 9. Projection (π)
    root = Project(
        input_node=root,
        columns=ast.columns,
        estimated_rows=root.estimated_rows,
        cost=root.cost + root.estimated_rows * 0.1,
    )

    return root


def suggest_join_order(ast: SelectStmt, db_path: Optional[Path] = None) -> dict[str, Any]:
    """
    Exhaustively evaluate join order permutations for multi-table queries (up to 4 tables).
    Returns estimated cost comparison between original and proposed cheapest order.
    Informational only; clearly labeled as estimate.
    """
    if not ast.from_table or not ast.joins or len(ast.joins) > 3:
        return {
            "applicable": False,
            "reason": "Join order analysis requires between 2 and 4 joined tables.",
        }

    # Only optimize INNER joins
    if any(j.join_type.upper() != "INNER" for j in ast.joins):
        return {
            "applicable": False,
            "reason": "Join order selection is only valid for pure INNER joins.",
        }

    all_tables = [ast.from_table.name] + [j.table.name for j in ast.joins]
    cards = {t: get_table_cardinality(t, db_path) for t in all_tables}

    # Estimate original cost
    orig_algebra = lower_ast_to_algebra(ast, db_path=db_path)
    orig_cost = orig_algebra.cost

    # Evaluate permutations of table order
    best_order = all_tables
    best_cost = orig_cost

    for perm in itertools.permutations(all_tables):
        # Calculate left-deep cost heuristic: smallest relations first
        current_rows = cards[perm[0]]
        total_cost = current_rows
        for next_tbl in perm[1:]:
            next_rows = cards[next_tbl]
            join_est = max(current_rows, next_rows)
            total_cost += next_rows + (current_rows * next_rows * 0.001)
            current_rows = join_est

        if total_cost < best_cost:
            best_cost = total_cost
            best_order = list(perm)

    return {
        "applicable": True,
        "original_order": all_tables,
        "original_cost": round(orig_cost, 2),
        "proposed_order": best_order,
        "proposed_cost": round(best_cost, 2),
        "potential_gain_percent": round(max(0.0, (orig_cost - best_cost) / orig_cost * 100), 1) if orig_cost > 0 else 0.0,
        "note": "Cost values are static heuristic estimates from table statistics. Informational only; not forced onto SQLite.",
    }

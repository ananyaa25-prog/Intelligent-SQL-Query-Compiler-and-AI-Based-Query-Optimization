"""Abstract Syntax Tree node classes and utilities for SQL."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ASTNode:
    """Base class for all AST nodes."""
    line: int = field(default=1, kw_only=True)
    column: int = field(default=1, kw_only=True)

    def to_sql(self) -> str:
        raise NotImplementedError

    def to_dict(self) -> dict[str, Any]:
        raise NotImplementedError

    def to_dot(self, graph: Optional[list[str]] = None, parent_id: Optional[str] = None) -> str:
        """Render node as Graphviz DOT."""
        if graph is None:
            graph = ["digraph AST {", '  node [shape=box, fontname="Helvetica", style="rounded,filled", fillcolor="#f0f4f8"];']
            self._render_dot(graph, str(id(self)), None)
            graph.append("}")
            return "\n".join(graph)
        self._render_dot(graph, str(id(self)), parent_id)
        return ""

    def _render_dot(self, graph: list[str], my_id: str, parent_id: Optional[str]) -> None:
        label = self.__class__.__name__
        graph.append(f'  "{my_id}" [label="{label}"];')
        if parent_id is not None:
            graph.append(f'  "{parent_id}" -> "{my_id}";')


@dataclass
class Expression(ASTNode):
    """Base class for expression nodes."""
    inferred_type: Optional[str] = field(default=None, kw_only=True)



@dataclass
class Star(Expression):
    """Represents '*' or 'table.*' in select items."""
    table: Optional[str] = None

    def to_sql(self) -> str:
        return f"{self.table}.*" if self.table else "*"

    def to_dict(self) -> dict[str, Any]:
        return {"type": "Star", "table": self.table}

    def _render_dot(self, graph: list[str], my_id: str, parent_id: Optional[str]) -> None:
        lbl = f"{self.table}.*" if self.table else "*"
        graph.append(f'  "{my_id}" [label="{lbl}", fillcolor="#e1f5fe"];')
        if parent_id is not None:
            graph.append(f'  "{parent_id}" -> "{my_id}";')


@dataclass
class ColumnRef(Expression):
    """Represents a column identifier, optionally qualified by a table."""
    name: str
    table: Optional[str] = None

    def to_sql(self) -> str:
        return f"{self.table}.{self.name}" if self.table else self.name

    def to_dict(self) -> dict[str, Any]:
        res = {"type": "ColumnRef", "name": self.name}
        if self.table:
            res["table"] = self.table
        if self.inferred_type:
            res["inferred_type"] = self.inferred_type
        return res

    def _render_dot(self, graph: list[str], my_id: str, parent_id: Optional[str]) -> None:
        lbl = self.to_sql()
        if self.inferred_type:
            lbl += f"\\n({self.inferred_type})"
        graph.append(f'  "{my_id}" [label="{lbl}", fillcolor="#e8f5e9"];')
        if parent_id is not None:
            graph.append(f'  "{parent_id}" -> "{my_id}";')


@dataclass
class Literal(Expression):
    """Represents a literal value (number, string, boolean, NULL)."""
    value: Any
    raw: str = ""
    is_string: bool = False

    def to_sql(self) -> str:
        if self.value is None:
            return "NULL"
        if isinstance(self.value, bool):
            return "TRUE" if self.value else "FALSE"
        if self.is_string or isinstance(self.value, str):
            escaped = str(self.value).replace("'", "''")
            return f"'{escaped}'"
        return str(self.value)

    def to_dict(self) -> dict[str, Any]:
        res = {"type": "Literal", "value": self.value, "is_string": self.is_string}
        if self.inferred_type:
            res["inferred_type"] = self.inferred_type
        return res

    def _render_dot(self, graph: list[str], my_id: str, parent_id: Optional[str]) -> None:
        lbl = self.to_sql()
        if self.inferred_type:
            lbl += f"\\n({self.inferred_type})"
        graph.append(f'  "{my_id}" [label="{lbl}", fillcolor="#fff9c4"];')
        if parent_id is not None:
            graph.append(f'  "{parent_id}" -> "{my_id}";')


@dataclass
class BinaryOp(Expression):
    """Binary operations: comparisons, logical AND/OR, arithmetic."""
    op: str
    left: Expression
    right: Expression

    def to_sql(self) -> str:
        left_sql = self.left.to_sql()
        right_sql = self.right.to_sql()
        my_prec = _precedence(self.op)
        if isinstance(self.left, BinaryOp) and _precedence(self.left.op) < my_prec:
            left_sql = f"({left_sql})"
        if isinstance(self.right, BinaryOp):
            right_prec = _precedence(self.right.op)
            if right_prec < my_prec or (right_prec == my_prec and self.op in ("-", "/")):
                right_sql = f"({right_sql})"
        return f"{left_sql} {self.op.upper()} {right_sql}"


    def to_dict(self) -> dict[str, Any]:
        res = {
            "type": "BinaryOp",
            "op": self.op.upper(),
            "left": self.left.to_dict(),
            "right": self.right.to_dict(),
        }
        if self.inferred_type:
            res["inferred_type"] = self.inferred_type
        return res

    def _render_dot(self, graph: list[str], my_id: str, parent_id: Optional[str]) -> None:
        lbl = f"BinaryOp: {self.op.upper()}"
        if self.inferred_type:
            lbl += f"\\n({self.inferred_type})"
        graph.append(f'  "{my_id}" [label="{lbl}", fillcolor="#ede7f6"];')
        if parent_id is not None:
            graph.append(f'  "{parent_id}" -> "{my_id}";')
        self.left._render_dot(graph, f"{my_id}_l", my_id)
        self.right._render_dot(graph, f"{my_id}_r", my_id)


@dataclass
class UnaryOp(Expression):
    """Unary prefix operators like NOT, +, -."""
    op: str
    operand: Expression

    def to_sql(self) -> str:
        op_str = self.op.upper()
        operand_sql = self.operand.to_sql()
        if isinstance(self.operand, BinaryOp):
            operand_sql = f"({operand_sql})"
        if op_str in ("+", "-"):
            return f"{op_str}{operand_sql}"
        return f"{op_str} {operand_sql}"

    def to_dict(self) -> dict[str, Any]:
        res = {
            "type": "UnaryOp",
            "op": self.op.upper(),
            "operand": self.operand.to_dict(),
        }
        if self.inferred_type:
            res["inferred_type"] = self.inferred_type
        return res

    def _render_dot(self, graph: list[str], my_id: str, parent_id: Optional[str]) -> None:
        lbl = f"UnaryOp: {self.op.upper()}"
        if self.inferred_type:
            lbl += f"\\n({self.inferred_type})"
        graph.append(f'  "{my_id}" [label="{lbl}", fillcolor="#ede7f6"];')
        if parent_id is not None:
            graph.append(f'  "{parent_id}" -> "{my_id}";')
        self.operand._render_dot(graph, f"{my_id}_op", my_id)


@dataclass
class Between(Expression):
    """BETWEEN low AND high predicate."""
    expr: Expression
    low: Expression
    high: Expression
    not_between: bool = False

    def to_sql(self) -> str:
        prefix = "NOT BETWEEN" if self.not_between else "BETWEEN"
        return f"{self.expr.to_sql()} {prefix} {self.low.to_sql()} AND {self.high.to_sql()}"

    def to_dict(self) -> dict[str, Any]:
        res = {
            "type": "Between",
            "not_between": self.not_between,
            "expr": self.expr.to_dict(),
            "low": self.low.to_dict(),
            "high": self.high.to_dict(),
        }
        if self.inferred_type:
            res["inferred_type"] = self.inferred_type
        return res

    def _render_dot(self, graph: list[str], my_id: str, parent_id: Optional[str]) -> None:
        lbl = "NOT BETWEEN" if self.not_between else "BETWEEN"
        graph.append(f'  "{my_id}" [label="{lbl}", fillcolor="#ede7f6"];')
        if parent_id is not None:
            graph.append(f'  "{parent_id}" -> "{my_id}";')
        self.expr._render_dot(graph, f"{my_id}_e", my_id)
        self.low._render_dot(graph, f"{my_id}_l", my_id)
        self.high._render_dot(graph, f"{my_id}_h", my_id)


@dataclass
class InList(Expression):
    """IN (v1, v2, ...) predicate."""
    expr: Expression
    values: list[Expression]
    not_in: bool = False

    def to_sql(self) -> str:
        prefix = "NOT IN" if self.not_in else "IN"
        vals = ", ".join(v.to_sql() for v in self.values)
        return f"{self.expr.to_sql()} {prefix} ({vals})"

    def to_dict(self) -> dict[str, Any]:
        res = {
            "type": "InList",
            "not_in": self.not_in,
            "expr": self.expr.to_dict(),
            "values": [v.to_dict() for v in self.values],
        }
        if self.inferred_type:
            res["inferred_type"] = self.inferred_type
        return res

    def _render_dot(self, graph: list[str], my_id: str, parent_id: Optional[str]) -> None:
        lbl = "NOT IN" if self.not_in else "IN"
        graph.append(f'  "{my_id}" [label="{lbl}", fillcolor="#ede7f6"];')
        if parent_id is not None:
            graph.append(f'  "{parent_id}" -> "{my_id}";')
        self.expr._render_dot(graph, f"{my_id}_e", my_id)
        for i, val in enumerate(self.values):
            val._render_dot(graph, f"{my_id}_v{i}", my_id)


@dataclass
class IsNull(Expression):
    """IS NULL / IS NOT NULL predicate."""
    expr: Expression
    not_null: bool = False

    def to_sql(self) -> str:
        suffix = "IS NOT NULL" if self.not_null else "IS NULL"
        return f"{self.expr.to_sql()} {suffix}"

    def to_dict(self) -> dict[str, Any]:
        res = {
            "type": "IsNull",
            "not_null": self.not_null,
            "expr": self.expr.to_dict(),
        }
        if self.inferred_type:
            res["inferred_type"] = self.inferred_type
        return res

    def _render_dot(self, graph: list[str], my_id: str, parent_id: Optional[str]) -> None:
        lbl = "IS NOT NULL" if self.not_null else "IS NULL"
        graph.append(f'  "{my_id}" [label="{lbl}", fillcolor="#ede7f6"];')
        if parent_id is not None:
            graph.append(f'  "{parent_id}" -> "{my_id}";')
        self.expr._render_dot(graph, f"{my_id}_e", my_id)


@dataclass
class FunctionCall(Expression):
    """Aggregate or scalar function call, e.g. COUNT(*), AVG(gpa)."""
    name: str
    args: list[Expression]
    distinct: bool = False

    def to_sql(self) -> str:
        arg_strs = [a.to_sql() for a in self.args]
        dist = "DISTINCT " if self.distinct else ""
        return f"{self.name.upper()}({dist}{', '.join(arg_strs)})"

    def to_dict(self) -> dict[str, Any]:
        res = {
            "type": "FunctionCall",
            "name": self.name.upper(),
            "distinct": self.distinct,
            "args": [a.to_dict() for a in self.args],
        }
        if self.inferred_type:
            res["inferred_type"] = self.inferred_type
        return res

    def _render_dot(self, graph: list[str], my_id: str, parent_id: Optional[str]) -> None:
        lbl = f"Function: {self.name.upper()}"
        if self.distinct:
            lbl += " (DISTINCT)"
        if self.inferred_type:
            lbl += f"\\n({self.inferred_type})"
        graph.append(f'  "{my_id}" [label="{lbl}", fillcolor="#ffe0b2"];')
        if parent_id is not None:
            graph.append(f'  "{parent_id}" -> "{my_id}";')
        for i, a in enumerate(self.args):
            a._render_dot(graph, f"{my_id}_a{i}", my_id)


@dataclass
class SelectItem(ASTNode):
    """A single item in the SELECT list, with optional alias."""
    expr: Expression
    alias: Optional[str] = None

    def to_sql(self) -> str:
        s = self.expr.to_sql()
        if self.alias:
            s += f" AS {self.alias}"
        return s

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "SelectItem",
            "expr": self.expr.to_dict(),
            "alias": self.alias,
        }

    def _render_dot(self, graph: list[str], my_id: str, parent_id: Optional[str]) -> None:
        lbl = f"SelectItem (AS {self.alias})" if self.alias else "SelectItem"
        graph.append(f'  "{my_id}" [label="{lbl}", fillcolor="#e0f2f1"];')
        if parent_id is not None:
            graph.append(f'  "{parent_id}" -> "{my_id}";')
        self.expr._render_dot(graph, f"{my_id}_expr", my_id)


@dataclass
class TableRef(ASTNode):
    """Table reference in FROM or JOIN, with optional alias."""
    name: str
    alias: Optional[str] = None

    def to_sql(self) -> str:
        if self.alias:
            return f"{self.name} AS {self.alias}"
        return self.name

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "TableRef",
            "name": self.name,
            "alias": self.alias,
        }

    def _render_dot(self, graph: list[str], my_id: str, parent_id: Optional[str]) -> None:
        lbl = f"Table: {self.to_sql()}"
        graph.append(f'  "{my_id}" [label="{lbl}", fillcolor="#fff3e0"];')
        if parent_id is not None:
            graph.append(f'  "{parent_id}" -> "{my_id}";')


@dataclass
class Join(ASTNode):
    """Join clause (INNER or LEFT)."""
    join_type: str  # "INNER" or "LEFT"
    table: TableRef
    on: Expression

    def to_sql(self) -> str:
        return f"{self.join_type.upper()} JOIN {self.table.to_sql()} ON {self.on.to_sql()}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "Join",
            "join_type": self.join_type.upper(),
            "table": self.table.to_dict(),
            "on": self.on.to_dict(),
        }

    def _render_dot(self, graph: list[str], my_id: str, parent_id: Optional[str]) -> None:
        lbl = f"{self.join_type.upper()} JOIN"
        graph.append(f'  "{my_id}" [label="{lbl}", fillcolor="#f3e5f5"];')
        if parent_id is not None:
            graph.append(f'  "{parent_id}" -> "{my_id}";')
        self.table._render_dot(graph, f"{my_id}_tbl", my_id)
        self.on._render_dot(graph, f"{my_id}_on", my_id)


@dataclass
class OrderByItem(ASTNode):
    """ORDER BY expression and direction."""
    expr: Expression
    direction: str = "ASC"  # "ASC" or "DESC"

    def to_sql(self) -> str:
        s = self.expr.to_sql()
        if self.direction.upper() == "DESC":
            s += " DESC"
        return s

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "OrderByItem",
            "expr": self.expr.to_dict(),
            "direction": self.direction.upper(),
        }

    def _render_dot(self, graph: list[str], my_id: str, parent_id: Optional[str]) -> None:
        lbl = f"OrderBy: {self.direction.upper()}"
        graph.append(f'  "{my_id}" [label="{lbl}", fillcolor="#fce4ec"];')
        if parent_id is not None:
            graph.append(f'  "{parent_id}" -> "{my_id}";')
        self.expr._render_dot(graph, f"{my_id}_expr", my_id)


@dataclass
class SelectStmt(ASTNode):
    """Root node for SELECT statements."""
    columns: list[SelectItem]
    from_table: Optional[TableRef] = None
    joins: list[Join] = field(default_factory=list)
    where: Optional[Expression] = None
    group_by: list[Expression] = field(default_factory=list)
    having: Optional[Expression] = None
    order_by: list[OrderByItem] = field(default_factory=list)
    limit: Optional[int] = None
    offset: Optional[int] = None
    distinct: bool = False

    # Backward compatibility properties for Person 1 / pipeline.py:
    @property
    def table(self) -> Optional[str]:
        return self.from_table.name if self.from_table else None

    def to_sql(self) -> str:
        parts = ["SELECT"]
        if self.distinct:
            parts.append("DISTINCT")
        parts.append(", ".join(c.to_sql() for c in self.columns))

        if self.from_table:
            parts.append("FROM")
            parts.append(self.from_table.to_sql())

        for join in self.joins:
            parts.append(join.to_sql())

        if self.where is not None:
            parts.append("WHERE")
            parts.append(self.where.to_sql())

        if self.group_by:
            parts.append("GROUP BY")
            parts.append(", ".join(g.to_sql() for g in self.group_by))

        if self.having is not None:
            parts.append("HAVING")
            parts.append(self.having.to_sql())

        if self.order_by:
            parts.append("ORDER BY")
            parts.append(", ".join(o.to_sql() for o in self.order_by))

        if self.limit is not None:
            parts.append(f"LIMIT {self.limit}")
            if self.offset is not None:
                parts.append(f"OFFSET {self.offset}")

        return " ".join(parts) + ";"

    def to_dict(self) -> dict[str, Any]:
        res: dict[str, Any] = {
            "type": "SelectStmt",
            "distinct": self.distinct,
            "columns": [c.to_dict() for c in self.columns],
            "from_table": self.from_table.to_dict() if self.from_table else None,
            "joins": [j.to_dict() for j in self.joins],
            "where": self.where.to_dict() if self.where else None,
            "group_by": [g.to_dict() for g in self.group_by],
            "having": self.having.to_dict() if self.having else None,
            "order_by": [o.to_dict() for o in self.order_by],
            "limit": self.limit,
            "offset": self.offset,
        }
        return res

    def _render_dot(self, graph: list[str], my_id: str, parent_id: Optional[str]) -> None:
        lbl = "SELECT"
        if self.distinct:
            lbl += " DISTINCT"
        graph.append(f'  "{my_id}" [label="{lbl}", fillcolor="#c8e6c9", style="filled,bold"];')
        if parent_id is not None:
            graph.append(f'  "{parent_id}" -> "{my_id}";')

        # Select items
        cols_id = f"{my_id}_cols"
        graph.append(f'  "{cols_id}" [label="Columns", fillcolor="#e0f2f1"];')
        graph.append(f'  "{my_id}" -> "{cols_id}";')
        for i, c in enumerate(self.columns):
            c._render_dot(graph, f"{cols_id}_{i}", cols_id)

        # From
        if self.from_table:
            self.from_table._render_dot(graph, f"{my_id}_from", my_id)

        # Joins
        for i, j in enumerate(self.joins):
            j._render_dot(graph, f"{my_id}_join_{i}", my_id)

        # Where
        if self.where:
            where_id = f"{my_id}_where"
            graph.append(f'  "{where_id}" [label="WHERE", fillcolor="#ffcdd2"];')
            graph.append(f'  "{my_id}" -> "{where_id}";')
            self.where._render_dot(graph, f"{where_id}_expr", where_id)

        # Group By
        if self.group_by:
            gb_id = f"{my_id}_gb"
            graph.append(f'  "{gb_id}" [label="GROUP BY", fillcolor="#d1c4e9"];')
            graph.append(f'  "{my_id}" -> "{gb_id}";')
            for i, g in enumerate(self.group_by):
                g._render_dot(graph, f"{gb_id}_{i}", gb_id)

        # Having
        if self.having:
            having_id = f"{my_id}_having"
            graph.append(f'  "{having_id}" [label="HAVING", fillcolor="#d1c4e9"];')
            graph.append(f'  "{my_id}" -> "{having_id}";')
            self.having._render_dot(graph, f"{having_id}_expr", having_id)

        # Order By
        if self.order_by:
            ob_id = f"{my_id}_ob"
            graph.append(f'  "{ob_id}" [label="ORDER BY", fillcolor="#f8bbd0"];')
            graph.append(f'  "{my_id}" -> "{ob_id}";')
            for i, o in enumerate(self.order_by):
                o._render_dot(graph, f"{ob_id}_{i}", ob_id)

        # Limit
        if self.limit is not None:
            lim_id = f"{my_id}_limit"
            graph.append(f'  "{lim_id}" [label="LIMIT {self.limit}", fillcolor="#cfd8dc"];')
            graph.append(f'  "{my_id}" -> "{lim_id}";')


def _precedence(op: str) -> int:
    """Return numeric precedence for binary operator (higher binds tighter)."""
    op = op.upper()
    if op == "OR":
        return 1
    if op == "AND":
        return 2
    if op in ("=", "!=", "<>", "<", "<=", ">", ">=", "LIKE"):
        return 3
    if op in ("+", "-"):
        return 4
    if op in ("*", "/"):
        return 5
    return 0


def ast_to_sql(node: ASTNode) -> str:
    """Pretty-print an AST back to formatted SQL."""
    return node.to_sql()


def ast_to_dict(node: ASTNode) -> dict[str, Any]:
    """Convert an AST node into a dictionary suitable for JSON/UI inspection."""
    return node.to_dict()


def ast_to_dot(node: ASTNode) -> str:
    """Export an AST node to a Graphviz DOT script."""
    return node.to_dot()

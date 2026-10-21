"""Multi-pass optimizer manager with step-by-step rewrite trace."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from sqlcompiler.frontend.parser import parse_sql, ParseError
from sqlcompiler.frontend.ast_nodes import SelectStmt, ast_to_sql
from sqlcompiler.semantic.symbols import Catalog
from sqlcompiler.optimizer.passes import (
    OptimizerPass,
    ConstantFoldingPass,
    BooleanSimplificationPass,
    RangePredicateConsolidationPass,
    ContradictionDetectionPass,
    RedundantDistinctRemovalPass,
    SelectStarExpansionPass,
    PredicatePushdownPass,
    InAndBetweenNormalizationPass,
)


def get_default_passes() -> list[OptimizerPass]:
    """Returns the ordered pipeline of optimization passes."""
    return [
        SelectStarExpansionPass(),
        InAndBetweenNormalizationPass(),
        ConstantFoldingPass(),
        BooleanSimplificationPass(),
        RangePredicateConsolidationPass(),
        ContradictionDetectionPass(),
        RedundantDistinctRemovalPass(),
        PredicatePushdownPass(),
    ]


class PassManager:
    """Manages iterative execution of AST rewrite passes until a fixpoint."""

    def __init__(self, passes: Optional[list[OptimizerPass]] = None, max_iterations: int = 10):
        self.passes = passes or get_default_passes()
        self.max_iterations = max_iterations

    def run_with_trace(
        self,
        ast: SelectStmt,
        catalog: Optional[Catalog] = None
    ) -> dict[str, Any]:
        current_ast = ast
        steps = []
        total_changed = False

        for iteration in range(1, self.max_iterations + 1):
            iteration_changed = False
            for p in self.passes:
                before_sql = ast_to_sql(current_ast)
                new_ast, changed = p.apply(current_ast, catalog=catalog)
                if changed:
                    after_sql = ast_to_sql(new_ast)
                    # Only record if the SQL representation actually altered
                    if before_sql.strip().rstrip(";") != after_sql.strip().rstrip(";"):
                        steps.append({
                            "iteration": iteration,
                            "pass_name": p.name,
                            "description": p.description,
                            "before_sql": before_sql,
                            "after_sql": after_sql,
                        })
                        current_ast = new_ast
                        iteration_changed = True
                        total_changed = True

            if not iteration_changed:
                break

        return {
            "ast": current_ast,
            "final_sql": ast_to_sql(current_ast),
            "changed": total_changed,
            "steps": steps,
        }


def optimize_with_trace(
    sql: str,
    catalog: Optional[Catalog] = None,
    db_path: Optional[Path] = None
) -> dict[str, Any]:
    """
    Optimize SQL query and return the trace of fired passes and final SQL.
    Falls back gracefully if SQL cannot be parsed by the hand-written front end.
    """
    if catalog is None:
        catalog = Catalog.default_university(db_path)

    try:
        ast = parse_sql(sql)
        manager = PassManager()
        trace = manager.run_with_trace(ast, catalog=catalog)
        return trace
    except Exception:
        # Fallback: if hand-written parser cannot parse, return original SQL without changes
        return {
            "ast": None,
            "final_sql": sql,
            "changed": False,
            "steps": [],
        }


def optimize_sql(sql: str) -> str:
    """Backward-compatible function returning final optimized SQL."""
    trace = optimize_with_trace(sql)
    return trace["final_sql"]

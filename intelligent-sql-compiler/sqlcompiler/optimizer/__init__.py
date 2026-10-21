"""Optimizer module: passes, manager, and tracing."""

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
from sqlcompiler.optimizer.manager import (
    PassManager,
    get_default_passes,
    optimize_with_trace,
    optimize_sql,
)

__all__ = [
    "OptimizerPass",
    "ConstantFoldingPass",
    "BooleanSimplificationPass",
    "RangePredicateConsolidationPass",
    "ContradictionDetectionPass",
    "RedundantDistinctRemovalPass",
    "SelectStarExpansionPass",
    "PredicatePushdownPass",
    "InAndBetweenNormalizationPass",
    "PassManager",
    "get_default_passes",
    "optimize_with_trace",
    "optimize_sql",
]

"""Database and execution engine wrappers."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
P2_DIR = ROOT / "person2"
if str(P2_DIR) not in sys.path:
    sys.path.insert(0, str(P2_DIR))

from person2.semantic_analyzer import validate_sql, get_database_schema, DB_PATH
from person2.execution_engine import execute_sql
from person2.evaluation import analyze_query, benchmark_query, compare_queries
from person2.database import create_database, SCHEMA_PATH

__all__ = [
    "validate_sql",
    "get_database_schema",
    "execute_sql",
    "analyze_query",
    "benchmark_query",
    "compare_queries",
    "create_database",
    "DB_PATH",
    "SCHEMA_PATH",
]

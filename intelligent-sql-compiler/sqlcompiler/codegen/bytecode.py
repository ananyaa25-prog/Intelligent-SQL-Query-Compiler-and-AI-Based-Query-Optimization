"""VDBE Bytecode analysis, opcode categorization, and static complexity metrics."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Optional

from sqlcompiler.semantic.symbols import Catalog

SEEK_AND_INDEX_OPCODES = {
    "SEEKROWID", "SEEKGE", "SEEKGT", "SEEKLE", "SEEKLT", "SEEKSCAN",
    "FOUND", "NOTFOUND", "IDXGE", "IDXGT", "IDXLE", "IDXLT", "IDXROWID",
    "DEFERREDSEEK", "AFFINITY", "COLUMN"
}

LOOP_OPCODES = {
    "NEXT", "PREV", "SORTERNEXT", "IFPOS"
}

SORTER_OPCODES = {
    "SORTEROPEN", "SORTERDATA", "SORTERINSERT", "SORTERSORT", "SORTERNEXT"
}

SCAN_OPCODES = {
    "REWIND", "OPENREAD", "CURSORHINT"
}

FLOW_CONTROL_OPCODES = {
    "GOTO", "GOSUB", "RETURN", "HALT", "YIELD", "IF", "IFNOT", "IFNULLROW"
}


def categorize_opcode(opcode: str) -> str:
    op = opcode.upper()
    if op in LOOP_OPCODES:
        return "loops"
    if op in SEEK_AND_INDEX_OPCODES:
        return "index_seeks"
    if op in SORTER_OPCODES:
        return "sorter"
    if op in SCAN_OPCODES:
        return "scans"
    if op in FLOW_CONTROL_OPCODES:
        return "flow_control"
    return "other"


def explain_bytecode(sql: str, db_path: Optional[Path] = None) -> dict[str, Any]:
    """
    Run SQLite's plain EXPLAIN (VDBE virtual machine opcodes) inside a read-only connection.
    Computes static deterministic metrics: total opcode count and counts by category.
    """
    if db_path is None:
        db_path = Path("person2/university.db")

    if not db_path.exists():
        return {
            "success": False,
            "error": f"Database file not found: {db_path}",
            "instructions": [],
            "metrics": {},
        }

    clean_sql = sql.strip().rstrip(";")
    explain_sql = f"EXPLAIN {clean_sql}"

    try:
        uri = f"{db_path.resolve().as_uri()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as conn:
            conn.execute("PRAGMA query_only = ON")
            cursor = conn.execute(explain_sql)
            rows = cursor.fetchall()

        instructions = []
        category_counts: dict[str, int] = {
            "loops": 0,
            "index_seeks": 0,
            "sorter": 0,
            "scans": 0,
            "flow_control": 0,
            "other": 0,
        }

        for row in rows:
            addr = row[0]
            opcode = str(row[1])
            p1 = row[2]
            p2 = row[3]
            p3 = row[4]
            p4 = str(row[5]) if len(row) > 5 else ""
            p5 = row[6] if len(row) > 6 else ""
            comment = str(row[7]) if len(row) > 7 else ""

            cat = categorize_opcode(opcode)
            category_counts[cat] = category_counts.get(cat, 0) + 1

            instructions.append({
                "addr": addr,
                "opcode": opcode,
                "category": cat,
                "p1": p1,
                "p2": p2,
                "p3": p3,
                "p4": p4,
                "p5": p5,
                "comment": comment,
            })

        metrics = {
            "total_opcodes": len(instructions),
            "loops": category_counts["loops"],
            "index_seeks": category_counts["index_seeks"],
            "sorter": category_counts["sorter"],
            "scans": category_counts["scans"],
            "flow_control": category_counts["flow_control"],
            "other": category_counts["other"],
            "category_counts": category_counts,
        }

        return {
            "success": True,
            "error": None,
            "instructions": instructions,
            "metrics": metrics,
        }

    except sqlite3.Error as exc:
        return {
            "success": False,
            "error": str(exc),
            "instructions": [],
            "metrics": {},
        }


def compare_bytecode(orig_sql: str, cand_sql: str, db_path: Optional[Path] = None) -> dict[str, Any]:
    """Compare static bytecode metrics between original and candidate SQL."""
    res_orig = explain_bytecode(orig_sql, db_path=db_path)
    res_cand = explain_bytecode(cand_sql, db_path=db_path)

    if not res_orig["success"] or not res_cand["success"]:
        return {
            "success": False,
            "error": res_orig.get("error") or res_cand.get("error"),
            "original": res_orig,
            "candidate": res_cand,
        }

    m_orig = res_orig["metrics"]
    m_cand = res_cand["metrics"]

    total_diff = m_orig["total_opcodes"] - m_cand["total_opcodes"]
    pct_reduction = (
        round((total_diff / m_orig["total_opcodes"]) * 100, 2)
        if m_orig["total_opcodes"] > 0 else 0.0
    )

    return {
        "success": True,
        "original_metrics": m_orig,
        "candidate_metrics": m_cand,
        "opcode_reduction": total_diff,
        "percent_reduction": pct_reduction,
        "note": "Opcode count is a deterministic static proxy for execution complexity; physical execution timing on tiny datasets is noisy.",
    }

"""Integration boundary joining the compiler frontend, optimizer, verification gate, and execution engine."""

from __future__ import annotations

import difflib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import sqlglot

ROOT = Path(__file__).resolve().parent
PERSON1 = ROOT / "person 1"
PERSON2 = ROOT / "person2"
for directory in (str(ROOT), str(PERSON1), str(PERSON2)):
    if directory not in sys.path:
        sys.path.insert(0, directory)

# Frontend, Semantics, Optimizer, IR, Codegen, Verification, NL
from sqlcompiler.frontend.lexer import tokenize as frontend_tokenize, LexicalError
from sqlcompiler.frontend.parser import parse_sql as frontend_parse, ParseError
from sqlcompiler.frontend.ast_nodes import ast_to_sql, ast_to_dict, ast_to_dot
from sqlcompiler.semantic.symbols import Catalog
from sqlcompiler.semantic.typecheck import SemanticAnalyzer
from sqlcompiler.optimizer.manager import optimize_with_trace
from sqlcompiler.ir.algebra import lower_ast_to_algebra, suggest_join_order
from sqlcompiler.codegen.bytecode import explain_bytecode, compare_bytecode
from sqlcompiler.verify.difftest import differential_test, DEFAULT_NUM_DATABASES
from sqlcompiler.verify.smt import verify_predicate_equivalence, Z3_AVAILABLE
from sqlcompiler.verify.mutation import run_mutation_demo
from sqlcompiler.nl.llm import generate_sql_with_compiler_guardrail, is_llm_configured
from sqlcompiler.nl.nl_to_sql import generate_sql as template_generate

# Engine
from person2.semantic_analyzer import validate_sql as sqlglot_validate_sql
from person2.execution_engine import execute_sql
from person2.evaluation import analyze_query, compare_queries


def run_pipeline(text: str, input_kind: str = "SQL") -> dict[str, Any]:
    """Execute the full compiler pipeline on a SQL or natural-language query."""
    request = text.strip()
    nl_info: dict[str, Any] = {"source": "direct SQL", "repairs_attempted": 0, "repair_logs": []}

    # 1. Input Processing
    if input_kind == "Natural language":
        catalog = Catalog.default_university(PERSON2 / "university.db")
        nl_result = generate_sql_with_compiler_guardrail(request, catalog=catalog)
        if not nl_result["success"]:
            raise ValueError(nl_result.get("error", "Could not generate SQL for that request."))
        sql = nl_result["sql"]
        nl_info = {
            "source": nl_result["source"],
            "repairs_attempted": nl_result.get("repairs_attempted", 0),
            "repair_logs": nl_result.get("repair_logs", []),
            "note": nl_result.get("note", ""),
        }
    else:
        sql = request

    # 2. Lexical & Syntactic Front End
    tokens = []
    handwritten_ast = None
    handwritten_ast_dict = None
    handwritten_ast_dot = None
    handwritten_error = None
    parser_status = "hand-written parser"

    try:
        token_objs = frontend_tokenize(sql)
        tokens = [
            {
                "type": tok.type,
                "value": tok.value,
                "position": tok.position,
                "line": tok.line,
                "column": tok.column,
            }
            for tok in token_objs
        ]
        handwritten_ast = frontend_parse(sql)
        handwritten_ast_dict = ast_to_dict(handwritten_ast)
        handwritten_ast_dot = ast_to_dot(handwritten_ast)
    except (SyntaxError, ValueError) as exc:
        handwritten_error = str(exc)
        parser_status = "hand-written parser error; SQLGlot fallback"

    # SQLGlot fallback & normalization
    normalized = None
    sqlglot_parse_error = None
    try:
        parsed_glot = sqlglot.parse_one(sql, read="sqlite")
        normalized = parsed_glot.sql(dialect="sqlite")
    except (sqlglot.errors.ParseError, ValueError) as exc:
        sqlglot_parse_error = str(exc).splitlines()[0]

    # Teaching AST representation for backward compatibility with UI
    teaching_ast = None
    if handwritten_ast:
        teaching_ast = {
            "columns": [c.to_sql() for c in handwritten_ast.columns],
            "table": handwritten_ast.table,
            "where": handwritten_ast.where.to_sql() if handwritten_ast.where else None,
            "order_by": ", ".join(o.to_sql() for o in handwritten_ast.order_by) if handwritten_ast.order_by else None,
            "limit": handwritten_ast.limit,
            "tree": handwritten_ast_dict,
        }

    # 3. Semantic Validation
    catalog = Catalog.default_university(PERSON2 / "university.db")
    own_analyzer = SemanticAnalyzer(catalog)
    if handwritten_ast:
        own_validation = own_analyzer.analyze(handwritten_ast, raw_sql=sql)
    else:
        own_validation = {
            "valid": False,
            "error": handwritten_error,
            "error_message": handwritten_error,
            "diagnostics": [],
            "annotated_ast": None,
        }

    sqlglot_validation = sqlglot_validate_sql(sql)

    # Disagreement note
    semantic_disagreement = None
    if own_validation["valid"] != sqlglot_validation["valid"]:
        semantic_disagreement = (
            f"Own analyzer reported valid={own_validation['valid']} "
            f"whereas SQLGlot reported valid={sqlglot_validation['valid']}."
        )

    # If own semantic validation fails, abort pipeline before execution
    if not own_validation["valid"]:
        return {
            "success": False,
            "request": request,
            "input_kind": input_kind,
            "sql": sql,
            "tokens": tokens,
            "normalized": normalized,
            "parser_status": parser_status,
            "parse_error": sqlglot_parse_error,
            "person1_ast": teaching_ast,
            "person1_parse_error": handwritten_error,
            "ast_dot": handwritten_ast_dot,
            "validation": own_validation,
            "sqlglot_validation": sqlglot_validation,
            "semantic_disagreement": semantic_disagreement,
            "error": own_validation["error"] or handwritten_error,
            "stage": "semantic validation",
            "nl_info": nl_info,
        }

    # 4. Multi-Pass Optimizer with Step-by-Step Trace
    trace_info = optimize_with_trace(sql, catalog=catalog)
    candidate_sql = trace_info["final_sql"]
    optimizer_steps = trace_info["steps"]
    changed = candidate_sql.strip().rstrip(";") != sql.strip().rstrip(";")

    # 5. Three-Layer Equivalence Verification Gate
    comparison = None
    difftest_result = None
    smt_result = None
    gate_details: dict[str, Any] = {}
    verified = False

    if changed:
        # Layer A: Finite result comparison on sample database
        comparison = compare_queries(sql, candidate_sql, repetitions=5)
        layer_a_ok = bool(comparison and comparison.get("success"))
        layer_a_error = comparison.get("error", "") if comparison else ""
        layer_a_truncated = bool(
            not layer_a_ok
            and ("truncated" in layer_a_error.lower() or "500 rows" in layer_a_error.lower())
        )

        # Layer B: Randomized differential testing on in-memory databases
        difftest_result = differential_test(sql, candidate_sql, num_databases=DEFAULT_NUM_DATABASES, seed=42)
        layer_b_ok = bool(difftest_result.get("equivalent"))

        # Layer C: Formal SMT predicate equivalence proof with Z3
        smt_result = verify_predicate_equivalence(sql, candidate_sql)
        layer_c_disproved = (smt_result.get("status") == "disproved")

        # When Layer A is truncated, Layers B and C decide. If B finds a counterexample, always reject.
        if layer_a_ok or layer_a_truncated:
            verified = layer_b_ok and (not layer_c_disproved)
        else:
            verified = False

        if not layer_b_ok or layer_c_disproved:
            verified = False

        gate_layers_summary = []
        if layer_a_ok:
            gate_layers_summary.append("A: results match on sample DB")
        elif layer_a_truncated:
            gate_layers_summary.append("A: skipped (result exceeds 500-row cap)")
        else:
            gate_layers_summary.append("A: mismatch on sample DB")

        gate_layers_summary.append(f"B: {difftest_result.get('message', 'Layer B run')}")
        if smt_result.get("status") == "proved":
            gate_layers_summary.append("C: Z3 proved predicate equivalence (UNSAT)")
        elif smt_result.get("status") == "disproved":
            gate_layers_summary.append(f"C: Z3 found counterexample ({smt_result.get('counterexample')})")
        elif smt_result.get("status") == "z3_unavailable":
            gate_layers_summary.append("C: z3-solver not installed (skipped)")
        else:
            gate_layers_summary.append("C: not applicable (relies on Layers A & B)")

        gate_details = {
            "verified": verified,
            "summary": "; ".join(gate_layers_summary),
            "layer_a": comparison,
            "layer_b": difftest_result,
            "layer_c": smt_result,
        }
    else:
        gate_details = {
            "verified": False,
            "summary": "not applicable; no rewrite",
            "layer_a": None,
            "layer_b": None,
            "layer_c": None,
        }

    equivalence_label = (
        "verified on full current sample results" if (verified and layer_a_ok)
        else ("verified (sample DB skipped: exceeds 500-row cap; verified by Layers B and C)" if (verified and layer_a_truncated)
        else ("not applicable; no rewrite" if not changed else "unverified; original query selected"))
    )

    # Candidate selection
    selected_sql = candidate_sql if verified else sql

    # 6. Read-Only SQLite Execution
    execution = execute_sql(selected_sql)
    plan = analyze_query(selected_sql) if execution["success"] else None

    # 7. Relational Algebra IR & Join Order Selection
    algebra_ir = None
    algebra_text = None
    algebra_dot = None
    join_order_advice = None
    if handwritten_ast:
        try:
            algebra_ir = lower_ast_to_algebra(handwritten_ast, catalog=catalog, db_path=PERSON2 / "university.db")
            algebra_text = algebra_ir.to_text()
            algebra_dot = algebra_ir.to_dot()
            join_order_advice = suggest_join_order(handwritten_ast, db_path=PERSON2 / "university.db")
        except Exception:
            pass

    # 8. VDBE Bytecode Inspection & Static Metrics
    bytecode = explain_bytecode(selected_sql, db_path=PERSON2 / "university.db")
    bytecode_comparison = (
        compare_bytecode(sql, candidate_sql, db_path=PERSON2 / "university.db")
        if changed else None
    )

    # 9. Evidence Trust Score
    semantic_score = 1.0
    equivalence_score = 1.0 if not changed else (1.0 if verified else 0.0)
    plan_score = 0.5
    performance_score = 0.5
    confidence_score = 0.5
    if verified and comparison and comparison.get("success"):
        before_plan = comparison["original_plan"]
        after_plan = comparison["optimized_plan"]
        plan_score = 1.0 if len(after_plan["plan"]) < len(before_plan["plan"]) else 0.5
        improvement = comparison.get("improvement_percent")
        performance_score = 1.0 if improvement is not None and improvement > 5 else 0.5
        confidence_score = 0.8 if smt_result and smt_result.get("proved") else 0.6

    trust = round(100 * (0.25 * semantic_score + 0.30 * equivalence_score
                         + 0.15 * plan_score + 0.15 * performance_score
                         + 0.15 * confidence_score))

    rules_applied = [s["pass_name"] for s in optimizer_steps]
    transformation_label = (
        f"Applied: {', '.join(rules_applied)}." if changed
        else "No supported rewrite applied."
    )

    return {
        "success": execution["success"],
        "stage": None if execution["success"] else "execution",
        "request": request,
        "input_kind": input_kind,
        "nl_info": nl_info,
        "sql": sql,
        "tokens": tokens,
        "normalized": normalized,
        "parser_status": parser_status,
        "parse_error": sqlglot_parse_error,
        "person1_ast": teaching_ast,
        "person1_parse_error": handwritten_error,
        "ast_dict": handwritten_ast_dict,
        "ast_dot": handwritten_ast_dot,
        "validation": own_validation,
        "sqlglot_validation": sqlglot_validation,
        "semantic_disagreement": semantic_disagreement,
        "candidate_sql": candidate_sql,
        "optimizer_trace": optimizer_steps,
        "transformation": transformation_label,
        "comparison": comparison,
        "difftest_result": difftest_result,
        "smt_result": smt_result,
        "gate_details": gate_details,
        "equivalence": equivalence_label,
        "executed_sql": selected_sql,
        "execution": execution,
        "plan": plan,
        "algebra_text": algebra_text,
        "algebra_dot": algebra_dot,
        "join_order_advice": join_order_advice,
        "bytecode": bytecode,
        "bytecode_comparison": bytecode_comparison,
        "trust_score": {
            "score": trust,
            "components": {
                "semantic_validity": semantic_score,
                "result_equivalence": equivalence_score,
                "plan_evidence": plan_score,
                "measured_performance": performance_score,
                "evidence_confidence": confidence_score,
            },
            "note": "Evidence score for this run, not a probability or proof of universal equivalence. Result checks cover complete outputs on test databases; plan details and timing are machine/load dependent.",
        },
        "index_advice": _index_advice(sql, plan),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _index_advice(sql: str, plan: dict | None) -> list[dict]:
    """Offer evidence-based possible indexes; never modifies the database."""
    if not plan or not plan.get("success") or not plan.get("has_table_scan"):
        return []
    try:
        tree = sqlglot.parse_one(sql, read="sqlite")
        where = tree.args.get("where")
        if where is None:
            return []
        filtered = {column.name for column in where.find_all(sqlglot.exp.Column)}
        db = PERSON2 / "university.db"
        uri = f"{db.resolve().as_uri()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as conn:
            tables = [
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            ]
            table = next((t for t in tables if t.casefold() in sql.casefold()), None)
            if not table:
                return []
            existing = set()
            for index in conn.execute(f'PRAGMA index_list("{table}")'):
                existing.update(row[2] for row in conn.execute(f'PRAGMA index_info("{index[1]}")'))
            return [
                {
                    "table": table,
                    "column": col,
                    "reason": f"The plan scans {table} and the WHERE clause filters on {col}; no existing index covers that column.",
                    "tradeoff": "An index uses storage and adds work to inserts and updates. This is a suggestion only; no index was created.",
                }
                for col in sorted(filtered - existing)
            ]
    except Exception:
        return []


def benchmark_markdown(result: dict) -> str:
    """Generate Markdown benchmark report including multi-layer verification and static bytecode."""
    comparison = result.get("comparison")
    if not comparison:
        comparison_text = "No rewrite was produced, so no comparison was run."
    elif not comparison.get("success"):
        comparison_text = f"Comparison stopped: {comparison.get('error', 'equivalence not established')}"
    else:
        a, b = comparison["original_benchmark"], comparison["optimized_benchmark"]
        comparison_text = (
            f"Equivalence: observed full result sets match (not a universal proof).\n\n"
            f"Repetitions: {a['repetitions']} measured after warm-up.\n\n"
            f"Original median: {a['median_ms']} ms (range {a['minimum_ms']} - {a['maximum_ms']} ms).\n\n"
            f"Candidate median: {b['median_ms']} ms (range {b['minimum_ms']} - {b['maximum_ms']} ms).\n\n"
            f"Measured difference: {comparison['improvement_percent']}%.\n\n"
            f"Note on timing: On a 1,000-row database, sub-millisecond execution timing is noisy and machine-dependent; "
            f"it should not be interpreted as an established speedup. VDBE opcode count is the primary deterministic metric."
        )

    gate_info = result.get("gate_details", {})
    gate_summary = f"\n\n## Verification Gate (Three Layers)\n\nSummary: {gate_info.get('summary', 'N/A')}\n"

    bytecode_section = ""
    if (result.get("bytecode_comparison") or {}).get("success"):
        bc = result["bytecode_comparison"]
        bytecode_section = (
            f"\n\n## VDBE Bytecode Static Metrics (Primary Deterministic Metric)\n\n"
            f"- Original total opcodes: {bc['original_metrics']['total_opcodes']}\n"
            f"- Candidate total opcodes: {bc['candidate_metrics']['total_opcodes']}\n"
            f"- Opcode reduction: {bc['opcode_reduction']} ({bc['percent_reduction']}%)\n"
            f"- Note: {bc['note']}\n"
        )

    plans = ""
    if result.get("plan", {}).get("success"):
        plans = "\n\n## Selected query plan\n\n" + "\n".join(
            f"- {step['detail']}" for step in result["plan"]["plan"]
        )

    advice = (
        "\n\n## Index suggestions\n\n"
        + (
            "\n".join(
                f"- `{item['table']}.{item['column']}`: {item['reason']} Trade-off: {item['tradeoff']}"
                for item in result.get("index_advice", [])
            )
            or "No index suggestion from the current plan evidence."
        )
    )

    nl_note = ""
    if result.get("input_kind") == "Natural language":
        nl_note = f"\n\nNL Source: {result.get('nl_info', {}).get('source', 'template')}"

    return (
        f"# SQL Compiler Benchmark Report\n\nGenerated: {result.get('timestamp')}\n\n"
        f"Input ({result.get('input_kind')}):\n\n```\n{result.get('request')}\n```\n"
        f"{nl_note}\n\nOriginal SQL:\n\n```sql\n{result.get('sql')}\n```\n\n"
        f"Candidate SQL:\n\n```sql\n{result.get('candidate_sql')}\n```\n\n"
        f"Validation: {'passed' if result.get('validation', {}).get('valid') else 'failed'}\n\n"
        f"Equivalence: {result.get('equivalence')}\n\n"
        f"{gate_summary}{bytecode_section}\n## Execution Benchmark (Illustrative Only)\n\n{comparison_text}{plans}\n\n"
        "Conditions: local university SQLite sample database, read-only execution. Timing includes fetching query rows."
        + advice
    )

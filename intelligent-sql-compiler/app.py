from __future__ import annotations

import difflib
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

from pipeline import PERSON2, run_pipeline, benchmark_markdown
from sqlcompiler.verify.mutation import run_mutation_demo
from sqlcompiler.verify.smt import Z3_AVAILABLE
from sqlcompiler.nl.llm import is_llm_configured

if not (PERSON2 / "university.db").exists():
    from person2.database import create_database
    create_database()

st.set_page_config(page_title="Intelligent SQL Compiler", page_icon="⌘", layout="wide")
st.title("Intelligent SQL Query Compiler")
st.caption("College Compiler Design Project: Source -> Lexer -> Parser -> Semantic Analyzer -> Optimizer -> Verification Gate -> Codegen -> Execution")

# LLM Status Banner
if is_llm_configured():
    st.success("Generative AI provider is configured. The compiler front end and semantic validator act as strict guardrails with automatic repair loops.")
else:
    st.info("Generative AI is currently disabled (no API key configured). Natural-language requests use the deterministic template pattern generator. SQL input and compiler phases run fully offline without any external dependency.")

if "history" not in st.session_state:
    st.session_state.history = []

with st.sidebar:
    st.header("University Database")
    db_path = PERSON2 / "university.db"
    if db_path.exists():
        with sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True) as conn:
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
            for (table,) in tables:
                st.markdown(f"**{table}**")
                cols = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
                st.caption(", ".join(f"{row[1]}: {row[2] or 'unspecified'}" for row in cols))
                indexes = conn.execute(f'PRAGMA index_list("{table}")').fetchall()
                st.caption("Indexes: " + (", ".join(row[1] for row in indexes) or "none"))
    else:
        st.warning("Database not initialized. Run 'python person2/database.py'.")

    st.divider()
    st.subheader("Compiler Features")
    st.write(f"• **Z3 SMT Prover:** {'Available (Active)' if Z3_AVAILABLE else 'Unavailable (Optional)'}")
    st.write(f"• **LLM Guardrails:** {'Active' if is_llm_configured() else 'Disabled (Template Fallback)'}")
    st.write("• **Handwritten Parser:** Active (EBNF Grammar)")
    st.write("• **3-Layer Gate:** Layers A, B, C")

    st.divider()
    if st.button("Clear session history", use_container_width=True):
        st.session_state.history = []
        st.rerun()

tab_studio, tab_phases, tab_mutation, tab_lab, tab_history = st.tabs([
    "Query Studio",
    "Compiler Phases",
    "Verification Demo (Mutants)",
    "Optimization Lab",
    "Session History"
])

examples = {
    "Redundant range filter": ("SQL", "SELECT student_id, name, gpa FROM students WHERE gpa >= 9.0 AND gpa >= 8.0 ORDER BY gpa DESC LIMIT 10;"),
    "Constant folding": ("SQL", "SELECT student_id, name FROM students WHERE age > 18 + 2 AND 1 = 1;"),
    "Contradiction detection (empty)": ("SQL", "SELECT student_id, name FROM students WHERE gpa > 9.0 AND gpa < 5.0;"),
    "Redundant DISTINCT on PK": ("SQL", "SELECT DISTINCT student_id, name, department FROM students WHERE age >= 20;"),
    "3-Table Join with Join Order advice": ("SQL", "SELECT s.name, c.title, e.grade FROM students s JOIN enrollments e ON s.student_id = e.student_id JOIN courses c ON e.course_id = c.course_id WHERE s.gpa >= 8.5 LIMIT 20;"),
    "Top students (Natural language)": ("Natural language", "Show the top 10 students"),
    "Average GPA by department (Natural language)": ("Natural language", "Average GPA by department"),
    "Semantic error (Unknown column with 'Did you mean')": ("SQL", "SELECT salary FROM students;"),
    "Semantic error (Unknown table with 'Did you mean')": ("SQL", "SELECT name FROM studentz;"),
}

with tab_studio:
    example = st.selectbox("Example gallery", list(examples))
    if st.button("Load example"):
        st.session_state.input_kind, st.session_state.query_text = examples[example]

    kind = st.radio("Input type", ["SQL", "Natural language"], horizontal=True, key="input_kind")
    value = st.text_area("Query or request", height=115, key="query_text", placeholder="SELECT name FROM students LIMIT 10;")
    run = st.button("Compile and run", type="primary")

    result = st.session_state.get("last_result")
    if run:
        try:
            with st.spinner("Running compiler pipeline..."):
                result = run_pipeline(value, kind)
            st.session_state.last_result = result
            st.session_state.history.insert(0, result)
            st.session_state.history = st.session_state.history[:20]
        except ValueError as exc:
            st.error(str(exc))
            result = None

    if result:
        st.subheader("Pipeline Flow")
        stages = [
            "Input", "Lex/Parse", "Semantics", "Optimizer",
            "Verification Gate", "Codegen", "Execution"
        ]
        statuses = [
            True,
            result.get("parser_status") == "hand-written parser",
            result.get("validation", {}).get("valid", False),
            result.get("candidate_sql") is not None,
            result.get("gate_details", {}).get("verified", False) or result.get("equivalence") in ("verified on full current sample results", "not applicable; no rewrite"),
            bool(result.get("bytecode", {}).get("success")),
            result.get("execution", {}).get("success", False),
        ]
        st.write(" → ".join(("✓ " if ok else "! ") + name for name, ok in zip(stages, statuses)))

        if result.get("sql"):
            left, right = st.columns(2)
            with left:
                st.markdown("**Input / Translated SQL**")
                st.code(result["sql"], language="sql")
                if result.get("input_kind") == "Natural language":
                    st.caption(f"NL Source: {result.get('nl_info', {}).get('source')}")
            with right:
                st.markdown("**Candidate SQL (After Optimizer Passes)**")
                st.code(result.get("candidate_sql", ""), language="sql")

        if result.get("transformation"):
            st.info("Optimizer Rule: " + result["transformation"])

        if result.get("gate_details"):
            st.markdown(f"**Verification Gate:** {result['gate_details'].get('summary')}")

        if result.get("success"):
            execution = result["execution"]
            a, b, c = st.columns(3)
            a.metric("Rows returned", execution["row_count"])
            b.metric("Execution time", f"{execution['execution_time_ms']:.3f} ms")
            c.metric("Optimization evidence score", f"{result['trust_score']['score']}/100")

            if execution["truncated"]:
                st.warning("Displayed rows are capped at 500; this run's result is truncated.")
            st.dataframe(pd.DataFrame(execution["rows"], columns=execution["columns"]), use_container_width=True)

            with st.expander("Execution Plan and Index Advice"):
                st.json(result.get("plan"))
                st.json(result["trust_score"])
                if result.get("index_advice"):
                    st.json(result["index_advice"])
                else:
                    st.caption("No index suggestion from this plan.")

            st.download_button(
                "Download benchmark report",
                benchmark_markdown(result),
                file_name="sql-benchmark-report.md",
                mime="text/markdown"
            )
        else:
            st.error(f"{result.get('stage', 'Pipeline')} failed: {result.get('error') or result.get('execution', {}).get('error')}")


with tab_phases:
    st.subheader("Compiler Phases Deep-Dive")
    if not result:
        st.info("Compile a query in the Query Studio tab to inspect its detailed compiler phases.")
    else:
        # Phase 1: Tokens
        with st.expander("1. Lexical Analysis (Tokens & Source Tracking)", expanded=False):
            st.caption("Hand-written tokenizer with 1-indexed line and column coordinates.")
            if result.get("tokens"):
                st.dataframe(pd.DataFrame(result["tokens"]), use_container_width=True)
            else:
                st.write("No tokens available.")

        # Phase 2: Parser & AST
        with st.expander("2. Syntactic Analysis (EBNF Grammar & AST Parse Tree)", expanded=True):
            st.markdown(f"**Parser Engine:** `{result.get('parser_status')}`")
            if result.get("ast_dot"):
                try:
                    st.graphviz_chart(result["ast_dot"])
                except Exception:
                    st.caption("Graphviz chart rendering unavailable; showing AST tree structure:")
            if result.get("ast_dict"):
                st.json(result["ast_dict"])
            elif result.get("person1_ast"):
                st.json(result["person1_ast"])
            if result.get("person1_parse_error"):
                st.warning(result["person1_parse_error"])

        # Phase 3: Semantic Analysis
        with st.expander("3. Semantic Analysis & Type Checker", expanded=True):
            val = result.get("validation", {})
            st.write(f"**Semantic Status:** {'Passed' if val.get('valid') else 'Failed'}")
            if result.get("semantic_disagreement"):
                st.warning(result["semantic_disagreement"])
            if val.get("diagnostics"):
                st.markdown("**Structured Diagnostics:**")
                st.dataframe(pd.DataFrame(val["diagnostics"]), use_container_width=True)
            else:
                st.success("No semantic errors or warnings detected.")

        # Phase 4: Optimizer Trace
        with st.expander("4. Multi-Pass AST Optimizer Trace", expanded=True):
            trace = result.get("optimizer_trace", [])
            if trace:
                st.write(f"**{len(trace)} Optimization Pass(es) Fired:**")
                for step in trace:
                    st.markdown(f"##### Iteration {step['iteration']}: {step['pass_name']}")
                    st.caption(step['description'])
                    c1, c2 = st.columns(2)
                    c1.code(step['before_sql'], language="sql")
                    c2.code(step['after_sql'], language="sql")
                    diff = "\n".join(difflib.unified_diff(
                        step['before_sql'].splitlines(),
                        step['after_sql'].splitlines(),
                        fromfile="before",
                        tofile="after",
                        lineterm=""
                    ))
                    if diff:
                        st.code(diff, language="diff")
            else:
                st.info("No optimizer rewrite rule fired for this query (returned unchanged).")

        # Phase 5: Relational Algebra IR & Join Order
        with st.expander("5. Relational Algebra IR & Cost Model", expanded=True):
            if result.get("algebra_text"):
                c1, c2 = st.columns([1, 1])
                with c1:
                    st.markdown("**Relational Algebra Tree (IR):**")
                    st.code(result["algebra_text"])
                with c2:
                    if result.get("algebra_dot"):
                        try:
                            st.graphviz_chart(result["algebra_dot"])
                        except Exception:
                            st.write("")
            if result.get("join_order_advice"):
                adv = result["join_order_advice"]
                st.markdown("**Join-Order Selection Analysis (Informational Heuristic):**")
                if adv.get("applicable"):
                    st.write(f"Original order: `{' ⋈ '.join(adv['original_order'])}` (Cost: {adv['original_cost']})")
                    st.write(f"Proposed order: `{' ⋈ '.join(adv['proposed_order'])}` (Cost: {adv['proposed_cost']})")
                    st.caption(f"Potential estimated gain: {adv.get('potential_gain_percent')}% — {adv.get('note')}")
                else:
                    st.caption(adv.get("reason", "Not applicable"))

        # Phase 6: Verification Gate
        with st.expander("6. Three-Layer Equivalence Gate (Layers A, B, C)", expanded=True):
            gate = result.get("gate_details", {})
            st.markdown(f"**Overall Gate Decision:** {'Verified & Accepted' if gate.get('verified') else 'Unverified / No Rewrite'}")
            st.write(f"**Summary:** {gate.get('summary')}")

            # Layer A
            st.markdown("##### Layer A: Finite Current Database Comparison")
            if gate.get("layer_a"):
                st.json(gate["layer_a"])
            else:
                st.caption("Layer A did not run (query unchanged).")

            # Layer B
            st.markdown("##### Layer B: Randomized In-Memory Differential Testing")
            if gate.get("layer_b"):
                st.json(gate["layer_b"])
            else:
                st.caption("Layer B did not run (query unchanged).")

            # Layer C
            st.markdown("##### Layer C: SMT Formal Equivalence Proof with Z3")
            if gate.get("layer_c"):
                st.json(gate["layer_c"])
            else:
                st.caption("Layer C did not run.")

        # Phase 7: VDBE Bytecode
        with st.expander("7. Code Generation (SQLite VDBE Bytecode)", expanded=True):
            bc = result.get("bytecode", {})
            if bc.get("success"):
                st.markdown(f"**Total VDBE Instructions:** `{bc['metrics']['total_opcodes']}`")
                m_cols = st.columns(5)
                m_cols[0].metric("Loops", bc["metrics"]["loops"])
                m_cols[1].metric("Index Seeks", bc["metrics"]["index_seeks"])
                m_cols[2].metric("Sorter", bc["metrics"]["sorter"])
                m_cols[3].metric("Scans", bc["metrics"]["scans"])
                m_cols[4].metric("Flow Control", bc["metrics"]["flow_control"])

                if (result.get("bytecode_comparison") or {}).get("success"):
                    comp_bc = result["bytecode_comparison"]
                    st.write(f"**Static Opcode Reduction:** {comp_bc['opcode_reduction']} ({comp_bc['percent_reduction']}%)")
                    st.caption(comp_bc["note"])

                st.markdown("**Disassembled Instructions:**")
                st.dataframe(pd.DataFrame(bc["instructions"]), use_container_width=True)
            else:
                st.caption("Bytecode not available.")

        # Phase 8: Execution & Benchmark
        with st.expander("8. Execution & Query Plan", expanded=True):
            if result.get("success"):
                st.write(f"**Rows:** {result['execution']['row_count']} | **Time:** {result['execution']['execution_time_ms']} ms")
                if result.get("plan"):
                    st.dataframe(pd.DataFrame(result["plan"].get("plan", [])), use_container_width=True)


with tab_mutation:
    st.subheader("Verification Demo: Can the Gate Catch a Buggy Optimizer?")
    st.write(
        "This interactive experiment evaluates 5 deliberately faulty optimizer rewrite rules against "
        "our 3-layer equivalence gate (Layer A: Sample DB, Layer B: Differential In-Memory DBs, Layer C: Z3 SMT Proof). "
        "Every incorrect rewrite must be caught and rejected before execution."
    )
    if st.button("Run Mutation Verification Suite", type="primary"):
        with st.spinner("Testing mutants across Layers A, B, and C..."):
            mutation_results = run_mutation_demo()
        st.session_state.mutation_results = mutation_results

    mut_res = st.session_state.get("mutation_results")
    if mut_res:
        summary_rows = []
        for m in mut_res:
            summary_rows.append({
                "Mutant Name": m["mutant_name"],
                "Fault Injected": m["description"],
                "Caught?": "✓ YES" if m["caught"] else "✗ NO",
                "Caught By Layers": ", ".join(m["caught_by_layers"]),
                "Mutated SQL": m["mutant_sql"],
            })
        st.dataframe(pd.DataFrame(summary_rows), use_container_width=True)

        for m in mut_res:
            with st.expander(f"Details: {m['mutant_name']}"):
                st.code(m["mutant_sql"], language="sql")
                st.write(f"**Layers:** {', '.join(m['caught_by_layers'])}")
                if m.get("counterexample"):
                    st.json(m["counterexample"])


with tab_lab:
    st.write("Compare one original query with a candidate rewrite. The candidate is executed only after validation; comparison requires complete results (up to 500 rows).")
    original = st.text_area("Original SQL", key="lab_original")
    candidate = st.text_area("Candidate SQL", key="lab_candidate")
    if st.button("Compare candidate"):
        from person2.evaluation import compare_queries
        outcome = compare_queries(original, candidate, repetitions=7)
        st.session_state.lab_result = outcome
    outcome = st.session_state.get("lab_result")
    if outcome:
        if outcome["success"]:
            st.columns(3)[0].metric("Original median", f"{outcome['original_benchmark']['median_ms']} ms")
            st.columns(3)[1].metric("Candidate median", f"{outcome['optimized_benchmark']['median_ms']} ms")
            st.write(f"Measured timing difference: {outcome['improvement_percent']}%")
            st.caption("Note on timing: On a 1,000-row database, millisecond timing differences are noisy and machine-dependent (not an established speedup). Use VDBE opcode counts in Compiler Phases as the primary deterministic metric.")
            before = outcome["original_plan"]["plan"]
            after = outcome["optimized_plan"]["plan"]
            p1, p2 = st.columns(2)
            p1.write("Original plan"); p1.json(before)
            p2.write("Candidate plan"); p2.json(after)
            st.code("\n".join(difflib.unified_diff(original.splitlines(), candidate.splitlines(), fromfile="original.sql", tofile="candidate.sql", lineterm="")))
        else:
            st.error(outcome["error"])


with tab_history:
    st.caption("Session-only history; query text is not persisted to disk.")
    for item in st.session_state.history:
        with st.expander(f"{item.get('timestamp', '')} · {item.get('input_kind')} · {item.get('stage') or 'complete'}"):
            st.write(item.get("request"))
            st.code(item.get("sql", ""), language="sql")
            st.write("Equivalence: ", item.get("equivalence"))
            st.write("Execution: ", item.get("execution", {}).get("success"))


import sys
from pathlib import Path

import pandas as pd
import streamlit as st

BASE_DIR = Path(__file__).resolve().parent
PERSON2_DIR = BASE_DIR / "person2"
sys.path.insert(0, str(PERSON2_DIR))

from semantic_analyzer import validate_sql
from execution_engine import execute_sql
from evaluation import analyze_query, compare_queries
from person1.compiler import compile_sql
from person1.nl_to_sql import generate_sql




st.set_page_config(
    page_title="Intelligent SQL Query Compiler",
    page_icon="🔎",
    layout="wide",
)

st.title("Intelligent SQL Query Compiler")
st.caption("Compiler Design | Semantic Analysis | SQL Optimization")

st.info(
    "Current prototype: database validation, safe query execution, "
    "EXPLAIN analysis and performance comparison. "
    "AI-based natural-language SQL generation will be integrated "
    "when Person 1's compiler is ready."
)

with st.sidebar:
    st.header("University Database")
    st.write("1,000 students")
    st.write("10 courses")
    st.write("3,000 enrollments")
    st.caption("SQLite · Read-only query execution")


st.divider()
st.subheader("Person 1: SQL Compiler")

compiler_sql = st.text_area(
    "Enter SQL to compile",
    key="compiler_sql",
    value="SELECT student_id, name FROM students WHERE gpa >= 9.0 AND gpa >= 8.0;",
    height=100,
)

if st.button("Compile SQL"):
    with st.spinner("Analyzing and optimizing SQL..."):
        result = compile_sql(compiler_sql)

    if result["success"]:
        st.success("Compilation completed successfully.")

        st.write("### Lexical Analysis — Tokens")
        st.dataframe(
            pd.DataFrame(result["tokens"]),
            use_container_width=True,
        )

        st.write("### Syntax Analysis — AST")
        st.json(result["ast"])

        st.write("### Rule-Based Optimization")
        st.code(result["optimized_sql"], language="sql")

        st.session_state["original_sql"] = compiler_sql
        st.session_state["optimized_sql"] = result["optimized_sql"]
    else:
        st.error(result["error"])

st.divider()
st.subheader("Natural Language to SQL")
st.caption("Describe what you want in English. This local rule-based generator does not require an API key.")

natural_language = st.text_input(
    "Describe your query",
    placeholder="e.g. Show the top 10 students",
    key="natural_language_input",
)


if st.button("Generate SQL"):
    try:
        generated_sql = generate_sql(natural_language)
        st.session_state.pop("generated_sql", None)

        validation = validate_sql(generated_sql)

        if validation.get("valid"):
            st.session_state["generated_sql"] = generated_sql
            st.success("SQL generated and validated successfully.")
        else:
            st.error(
                "SQL was generated, but validation failed. "
                "Review the error before using this query."
            )
            st.write(validation.get("error", validation))

    except ValueError as exc:
        st.session_state.pop("generated_sql", None)
        st.error(str(exc))




if st.session_state.get("generated_sql"):
    st.write("Generated SQL")
    st.code(st.session_state["generated_sql"], language="sql")

    if st.button("Use Generated SQL in Workspace"):
        st.session_state["sql_input"] = st.session_state["generated_sql"]
        st.rerun()


st.subheader("SQL Query Workspace")

examples = {
    "Select students with GPA above 9": (
        "SELECT student_id, name, gpa FROM students "
        "WHERE gpa >= 9.0 ORDER BY gpa DESC LIMIT 10"
    ),
    "Count students by department": (
        "SELECT department, COUNT(*) AS student_count "
        "FROM students GROUP BY department "
        "ORDER BY student_count DESC"
    ),
    "Join students and courses": (
        "SELECT s.name, c.title, e.grade "
        "FROM students s "
        "JOIN enrollments e ON s.student_id = e.student_id "
        "JOIN courses c ON e.course_id = c.course_id LIMIT 20"
    ),
    "Test invalid column": "SELECT salary FROM students",
}

choice = st.selectbox("Try a sample query", list(examples))

if st.button("Load example"):
    st.session_state["sql_input"] = examples[choice]

sql = st.text_area(
    "SQL",
    key="sql_input",
    height=130,
    placeholder="SELECT name FROM students LIMIT 10",
)

c1, c2, c3 = st.columns(3)

with c1:
    validate_clicked = st.button("Validate SQL", use_container_width=True)

with c2:
    execute_clicked = st.button(
        "Validate & Execute", type="primary", use_container_width=True
    )

with c3:
    explain_clicked = st.button(
        "Explain Plan", use_container_width=True
    )

if validate_clicked:
    result = validate_sql(sql)

    if result["valid"]:
        st.success("Semantic validation passed.")
        st.code(result.get("normalized_sql", sql), language="sql")
    else:
        st.error(result["error"])

if execute_clicked:
    result = execute_sql(sql)

    if result["success"]:
        st.success("Query executed successfully.")

        a, b = st.columns(2)
        a.metric("Rows returned", result["row_count"])
        b.metric("Execution time", f"{result['execution_time_ms']} ms")

        if result["truncated"]:
            st.warning("Results are limited to 500 rows.")

        st.dataframe(
            pd.DataFrame(result["rows"], columns=result["columns"]),
            use_container_width=True,
        )
    else:
        st.error(result["error"])

if explain_clicked:
    result = analyze_query(sql)

    if result["success"]:
        st.success("Execution plan generated.")
        a, b, c = st.columns(3)
        a.metric("Uses index", "Yes" if result["uses_index"] else "No")
        b.metric(
            "Table scan",
            "Yes" if result["has_table_scan"] else "No",
        )
        c.metric(
            "Temporary structure",
            "Yes" if result["uses_temporary_structure"] else "No",
        )
        st.dataframe(pd.DataFrame(result["plan"]), use_container_width=True)
    else:
        st.error(result["error"])

st.divider()
st.subheader("Optimization Evaluation")

original_sql = st.text_area(
    "Original SQL",
    key="original_sql",
    placeholder="Paste original SQL here",
)

optimized_sql = st.text_area(
    "Optimized SQL",
    key="optimized_sql",
    placeholder="Paste optimized SQL here",
)

if st.button("Compare Queries"):
    if not original_sql.strip() or not optimized_sql.strip():
        st.warning("Enter both queries.")
    else:
        with st.spinner("Evaluating both queries..."):
            result = compare_queries(original_sql, optimized_sql, 5)

        if result["success"]:
            st.success("Results are equivalent.")

            a, b, c = st.columns(3)
            a.metric(
                "Original median",
                f"{result['original_benchmark']['median_ms']} ms",
            )
            b.metric(
                "Optimized median",
                f"{result['optimized_benchmark']['median_ms']} ms",
            )

            improvement = result["improvement_percent"]
            c.metric(
                "Measured improvement",
                "N/A" if improvement is None else f"{improvement:.2f}%",
            )

            st.write("Original plan")
            st.dataframe(
                pd.DataFrame(result["original_plan"]["plan"]),
                use_container_width=True,
            )

            st.write("Optimized plan")
            st.dataframe(
                pd.DataFrame(result["optimized_plan"]["plan"]),
                use_container_width=True,
            )
        else:
            st.error(result["error"])

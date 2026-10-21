from pipeline import run_pipeline
from evaluation import benchmark_query


def test_natural_language_pipeline_runs_real_backend():
    result = run_pipeline("Show the top 5 students", "Natural language")
    assert result["success"] is True
    assert result["execution"]["row_count"] == 5
    assert result["validation"]["valid"] is True
    assert "SELECT" in result["sql"]


def test_rewrite_is_only_selected_after_observed_equivalence():
    result = run_pipeline(
        "SELECT student_id, name FROM students WHERE gpa >= 9.0 AND gpa >= 8.0 LIMIT 10"
    )
    assert result["candidate_sql"] != result["sql"]
    assert result["equivalence"] == "verified on full current sample results"
    assert result["executed_sql"] == result["candidate_sql"]
    assert result["comparison"]["results_equivalent"] is True


def test_invalid_query_is_not_executed():
    result = run_pipeline("SELECT salary FROM students")
    assert result["success"] is False
    assert result["stage"] == "semantic validation"
    assert "execution" not in result


def test_multiple_statements_rejected():
    result = run_pipeline("SELECT name FROM students; DELETE FROM students")
    assert result["success"] is False
    assert result["validation"]["valid"] is False


def test_benchmark_refuses_to_measure_more_than_result_cap():
    result = benchmark_query("SELECT student_id FROM students", repetitions=1)
    assert result["success"] is False
    assert "500 rows" in result["error"]


def test_subquery_produces_clean_parse_diagnostic_and_sqlglot_fallback():
    # WHERE x IN (SELECT ...)
    q1 = "SELECT name FROM students WHERE student_id IN (SELECT student_id FROM enrollments);"
    res1 = run_pipeline(q1)
    assert res1["parser_status"] == "hand-written parser error; SQLGlot fallback"
    assert "Syntax error" in res1["person1_parse_error"]
    assert res1["sqlglot_validation"]["valid"] is True

    # WHERE (SELECT 1) = 1
    q2 = "SELECT name FROM students WHERE (SELECT 1) = 1;"
    res2 = run_pipeline(q2)
    assert res2["parser_status"] == "hand-written parser error; SQLGlot fallback"
    assert "Syntax error" in res2["person1_parse_error"]
    assert res2["sqlglot_validation"]["valid"] is True


def test_truncated_layer_a_allows_candidate_selection_if_layer_b_passes():
    # 1,000 students in DB -> exceeds 500-row cap in Layer A
    sql = "SELECT DISTINCT student_id, name FROM students;"
    res = run_pipeline(sql)
    assert res["success"] is True
    assert res["candidate_sql"] == "SELECT student_id, name FROM students;"
    assert res["executed_sql"] == res["candidate_sql"]
    assert res["gate_details"]["verified"] is True
    assert "A: skipped (result exceeds 500-row cap)" in res["gate_details"]["summary"]


def test_truncated_layer_a_rejects_candidate_if_layer_b_finds_counterexample(monkeypatch):
    import pipeline
    # Mock difftest to report a counterexample even though candidate was proposed
    monkeypatch.setattr(
        pipeline,
        "differential_test",
        lambda *args, **kwargs: {
            "equivalent": False,
            "counterexample": {"student_id": 1},
            "message": "Difference observed on random database",
            "num_databases": 50,
            "num_databases_tested": 1,
        }
    )
    sql = "SELECT DISTINCT student_id, name FROM students;"
    res = run_pipeline(sql)
    assert res["success"] is True
    assert res["gate_details"]["verified"] is False
    # Must keep original SQL when Layer B finds a counterexample
    assert res["executed_sql"] == sql



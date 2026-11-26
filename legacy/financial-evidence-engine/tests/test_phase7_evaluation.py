from decimal import Decimal


def test_metric_calculator_scores_exact_and_flawed_predictions():
    from financial_evidence_engine.evaluation import (
        EvaluationRun,
        RetrievedEvidence,
        TaskPrediction,
        build_seed_task_set,
        evaluate_run,
    )

    task = build_seed_task_set().tasks[0]
    exact_prediction = TaskPrediction.from_gold(
        task,
        method="full_evidence_engine",
        latency_ms=Decimal("25"),
        cost_usd=Decimal("0.01"),
    )
    exact_report = evaluate_run(EvaluationRun("full_evidence_engine", (exact_prediction,)), (task,))

    assert exact_report.metrics["evidence_recall_at_k"] == Decimal("1")
    assert exact_report.metrics["citation_exactness"] == Decimal("1")
    assert exact_report.metrics["numeric_correctness"] == Decimal("1")
    assert exact_report.metrics["fiscal_period_correctness"] == Decimal("1")
    assert exact_report.metrics["entity_correctness"] == Decimal("1")
    assert exact_report.metrics["verdict_accuracy"] == Decimal("1")
    assert exact_report.metrics["latency_ms"] == Decimal("25")
    assert exact_report.metrics["cost_usd"] == Decimal("0.01")

    flawed_prediction = TaskPrediction(
        task_id=task.task_id,
        method="bm25_rag",
        predicted_verdict="support",
        retrieved_evidence=(
            RetrievedEvidence(
                evidence_key="wrong:period",
                source_type=task.expected_evidence[0].source_type,
                modality=task.expected_evidence[0].modality,
                company_ticker="MSFT",
                fiscal_period="FY2022",
                metric=task.expected_evidence[0].metric,
                cited=False,
            ),
        ),
        numeric_check_statuses={task.numeric_checks[0].check_id: "fail"},
        latency_ms=Decimal("10"),
        cost_usd=Decimal("0"),
    )
    flawed_report = evaluate_run(EvaluationRun("bm25_rag", (flawed_prediction,)), (task,))

    assert flawed_report.metrics["evidence_recall_at_k"] == Decimal("0")
    assert flawed_report.metrics["citation_exactness"] == Decimal("0")
    assert flawed_report.metrics["numeric_correctness"] == Decimal("0")
    assert flawed_report.metrics["fiscal_period_correctness"] == Decimal("0")
    assert flawed_report.metrics["entity_correctness"] == Decimal("0")


def test_phase7_baselines_show_naive_rag_failures_and_full_engine_gain():
    from financial_evidence_engine.evaluation import build_seed_task_set, run_baseline_evaluations

    reports = run_baseline_evaluations(build_seed_task_set())

    assert set(reports) == {
        "bm25_rag",
        "dense_rag",
        "hybrid_retrieval_reranker",
        "graphrag_only",
        "multimodal_extraction_only",
        "full_evidence_engine",
    }
    assert reports["full_evidence_engine"].metrics["evidence_recall_at_k"] > reports["bm25_rag"].metrics["evidence_recall_at_k"]
    assert reports["full_evidence_engine"].metrics["citation_exactness"] > reports["bm25_rag"].metrics["citation_exactness"]
    assert reports["full_evidence_engine"].metrics["numeric_correctness"] > reports["bm25_rag"].metrics["numeric_correctness"]
    assert reports["full_evidence_engine"].metrics["verdict_accuracy"] > reports["bm25_rag"].metrics["verdict_accuracy"]
    assert reports["bm25_rag"].metrics["unsupported_claim_rate"] > reports["full_evidence_engine"].metrics["unsupported_claim_rate"]


def test_phase7_ablations_isolate_graph_validator_and_chart_value():
    from financial_evidence_engine.evaluation import (
        build_phase7_evaluation_report,
        build_seed_task_set,
        run_baseline_evaluations,
    )

    task_set = build_seed_task_set()
    full_report = run_baseline_evaluations(task_set)["full_evidence_engine"]
    phase7_report = build_phase7_evaluation_report(task_set)
    ablations = phase7_report.ablation_reports

    assert set(ablations) == {
        "without_graph",
        "without_numeric_validator",
        "without_fiscal_period_validator",
        "without_chart_table_extraction",
        "without_contradiction_detector",
        "without_reranker",
    }
    assert full_report.metrics["evidence_recall_at_k"] > ablations["without_graph"].metrics["evidence_recall_at_k"]
    assert full_report.metrics["numeric_correctness"] > ablations["without_numeric_validator"].metrics["numeric_correctness"]
    assert full_report.metrics["fiscal_period_correctness"] > ablations["without_fiscal_period_validator"].metrics["fiscal_period_correctness"]
    assert full_report.metrics["contradiction_detection_accuracy"] > ablations["without_contradiction_detector"].metrics["contradiction_detection_accuracy"]
    assert (
        full_report.family_metrics["chart_table_reconciliation"]["evidence_recall_at_k"]
        > ablations["without_chart_table_extraction"].family_metrics["chart_table_reconciliation"]["evidence_recall_at_k"]
    )


def test_phase7_report_serializes_acceptance_findings():
    from financial_evidence_engine.evaluation import build_phase7_evaluation_report, build_seed_task_set

    report = build_phase7_evaluation_report(build_seed_task_set())
    payload = report.to_dict()

    assert report.acceptance_findings == {
        "validators_matter": True,
        "graph_retrieval_matters": True,
        "naive_rag_fails": True,
        "full_system_not_prompt_only": True,
    }
    assert payload["task_count"] == 60
    assert payload["baseline_reports"]["full_evidence_engine"]["metrics"]["verdict_accuracy"] == "1"
    assert payload["acceptance_findings"]["validators_matter"] is True

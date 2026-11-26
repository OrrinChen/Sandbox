from collections import Counter


def test_seed_due_diligence_task_set_contains_60_high_quality_tasks():
    from financial_evidence_engine.evaluation import build_seed_task_set

    task_set = build_seed_task_set()

    assert len(task_set.tasks) == 60
    assert len({task.task_id for task in task_set.tasks}) == 60
    assert task_set.summary()["task_count"] == 60
    assert task_set.summary()["families"] == {
        "chart_table_reconciliation": 10,
        "cross_company_comparison": 10,
        "guidance_vs_actuals": 10,
        "management_claim_verification": 10,
        "risk_contradiction": 10,
        "single_company_trend": 10,
    }


def test_each_task_is_multihop_multidocument_cited_and_numeric_validator_checkable():
    from financial_evidence_engine.evaluation import build_seed_task_set

    task_set = build_seed_task_set()

    for task in task_set.tasks:
        assert task.is_multi_hop
        assert task.is_multi_document
        assert task.requires_citation
        assert task.numeric_checks
        assert task.expected_evidence
        assert len({requirement.source_type for requirement in task.expected_evidence}) >= 2
        assert len({requirement.modality for requirement in task.expected_evidence}) >= 2
        assert task.allowed_source_types
        assert task.expected_verdict in {"support", "contradict", "insufficient"}
        assert task.known_distractors


def test_task_set_covers_required_task_families_and_verdicts():
    from financial_evidence_engine.evaluation import build_seed_task_set

    task_set = build_seed_task_set()
    families = Counter(task.family for task in task_set.tasks)
    verdicts = Counter(task.expected_verdict for task in task_set.tasks)

    assert set(families) == {
        "single_company_trend",
        "cross_company_comparison",
        "management_claim_verification",
        "risk_contradiction",
        "guidance_vs_actuals",
        "chart_table_reconciliation",
    }
    assert verdicts["support"] > 0
    assert verdicts["contradict"] > 0
    assert verdicts["insufficient"] > 0


def test_task_serialization_preserves_gold_labels_for_evaluation():
    from financial_evidence_engine.evaluation import build_seed_task_set

    task = build_seed_task_set().tasks[0]
    payload = task.to_dict()

    assert payload["task_id"] == task.task_id
    assert payload["claim_text"] == task.claim_text
    assert payload["expected_verdict"] == task.expected_verdict
    assert payload["expected_evidence"][0]["source_type"]
    assert payload["numeric_checks"][0]["validator"] == "numeric_reconciliation"
    assert payload["known_distractors"][0]["reason"]

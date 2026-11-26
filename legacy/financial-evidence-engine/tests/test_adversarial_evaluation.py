from decimal import Decimal


def test_adversarial_generator_builds_100_plus_tasks_with_expected_failure_modes():
    from financial_evidence_engine.evaluation import (
        ADVERSARIAL_FAILURE_MODES,
        AdversarialTaskGenerator,
    )

    task_set = AdversarialTaskGenerator().generate()
    failure_modes = {task.expected_failure_mode for task in task_set.tasks}

    assert len(task_set.tasks) >= 100
    assert failure_modes == set(ADVERSARIAL_FAILURE_MODES)
    assert all(task.expected_failure_mode for task in task_set.tasks)
    assert all(task.failure_reason for task in task_set.tasks)
    assert all(task.required_validators for task in task_set.tasks)
    assert task_set.summary()["failure_mode_count"] == len(ADVERSARIAL_FAILURE_MODES)


def test_failure_mode_taxonomy_maps_every_mode_to_validator_and_description():
    from financial_evidence_engine.evaluation import (
        ADVERSARIAL_FAILURE_MODES,
        FailureModeTaxonomy,
    )

    taxonomy = FailureModeTaxonomy.default()

    for mode in ADVERSARIAL_FAILURE_MODES:
        entry = taxonomy.entry_for(mode)
        assert entry.failure_mode == mode
        assert entry.primary_validator
        assert entry.description
        assert entry.recommended_response


def test_validator_coverage_report_includes_matrix_and_explainable_failures():
    from financial_evidence_engine.evaluation import (
        AdversarialTaskGenerator,
        FailureModeTaxonomy,
        build_validator_coverage_report,
    )

    task_set = AdversarialTaskGenerator().generate()
    report = build_validator_coverage_report(task_set, FailureModeTaxonomy.default())
    payload = report.to_dict()

    assert report.task_count >= 100
    assert report.failure_mode_count == 12
    assert report.explainable_failure_rate == Decimal("1")
    assert report.full_engine_accuracy < Decimal("1")
    assert report.perfect_accuracy_required is False
    assert set(report.validator_coverage_matrix) >= {
        "fiscal_period_validator",
        "entity_validator",
        "segment_validator",
        "currency_validator",
        "unit_scale_validator",
        "citation_validator",
        "unsupported_claim_detector",
        "structured_fact_contradiction_detector",
    }
    assert all(result.failure_reason for result in report.results)
    assert payload["validator_coverage_matrix"]["fiscal_period_validator"]["wrong_fiscal_year"] > 0


def test_adversarial_report_writes_json_and_markdown_artifacts(tmp_path):
    from financial_evidence_engine.evaluation import (
        build_adversarial_evaluation_report,
        write_adversarial_evaluation_artifacts,
    )

    report = build_adversarial_evaluation_report()
    manifest = write_adversarial_evaluation_artifacts(
        report,
        experiments_dir=tmp_path / "experiments",
        reports_dir=tmp_path / "reports",
    )
    markdown = manifest.markdown_artifact.read_text(encoding="utf-8")

    assert manifest.json_artifact.is_file()
    assert manifest.markdown_artifact.is_file()
    assert "Adversarial / Red-Team Evaluation" in markdown
    assert "perfect accuracy is not required" in markdown
    assert "wrong_fiscal_year" in markdown

PYTHON ?= python3
PYTHONPATH_VALUE := src
ARTIFACT_DIR ?= artifacts
SMOKE_DIR ?= $(ARTIFACT_DIR)/eval_runs/smoke
MODEL_STUDY_DIR ?= $(ARTIFACT_DIR)/eval_runs/silent_failure_study
REPORT_DIR ?= $(ARTIFACT_DIR)/reports/smoke
REPLAY_WORKSPACE ?= /tmp/sandboxed-agent-eval-gates-replay
PORTFOLIO_REPORT_DIR ?= reports
PORTFOLIO_EVIDENCE_DIR ?= $(ARTIFACT_DIR)/eval_runs/portfolio_model_matrix
INTEGRATIONS_DIR ?= $(ARTIFACT_DIR)/integrations

.PHONY: test smoke gate model-study report validate-config portfolio-report reproduce-report optional-integrations-smoke ci

test:
	$(PYTHON) -m pytest

smoke:
	PYTHONPATH=$(PYTHONPATH_VALUE) $(PYTHON) -m sandboxed_agent_eval_harness.evaluation.runner \
		--suite smoke \
		--baseline oracle_tool_selection_agent \
		--trials 1 \
		--output-dir $(SMOKE_DIR)

gate: smoke
	PYTHONPATH=$(PYTHONPATH_VALUE) $(PYTHON) -m sandboxed_agent_eval_harness.evaluation.gates \
		--summary $(SMOKE_DIR)/summary.json \
		--threshold-preset strict_smoke \
		--discover-traces \
		--replay-workspace $(REPLAY_WORKSPACE)

model-study:
	PYTHONPATH=$(PYTHONPATH_VALUE) $(PYTHON) -m sandboxed_agent_eval_harness.evaluation.model_study \
		--recorded-output fixtures/model_outputs/silent_failure_study.json \
		--output-dir $(MODEL_STUDY_DIR)

report: smoke
	PYTHONPATH=$(PYTHONPATH_VALUE) $(PYTHON) -m sandboxed_agent_eval_harness.evaluation.report \
		--summary $(SMOKE_DIR)/summary.json \
		--output-dir $(REPORT_DIR)

validate-config:
	PYTHONPATH=$(PYTHONPATH_VALUE) $(PYTHON) -m sandboxed_agent_eval_harness.config.validate

portfolio-report:
	PYTHONPATH=$(PYTHONPATH_VALUE) $(PYTHON) -m sandboxed_agent_eval_harness.evaluation.portfolio \
		--output-dir $(PORTFOLIO_REPORT_DIR) \
		--evidence-dir $(PORTFOLIO_EVIDENCE_DIR)

reproduce-report: validate-config portfolio-report
	@echo "Expected output:"
	@echo "Final-answer-only grading overestimated validated correctness by 56.2 percentage points"
	@echo "180 silent failures"
	@echo "320 recorded offline runs"
	@echo "reports/portfolio_report.md"

optional-integrations-smoke:
	@# Expected output includes mcp_fixture_trace=... from the fixture-backed MCP adapter.
	PYTHONPATH=$(PYTHONPATH_VALUE) $(PYTHON) -m sandboxed_agent_eval_harness.integrations.smoke \
		--output-dir $(INTEGRATIONS_DIR)

ci: test validate-config smoke gate model-study report

PYTHON ?= python3
PYTHONPATH_VALUE := src
ARTIFACT_DIR ?= artifacts
SMOKE_DIR ?= $(ARTIFACT_DIR)/eval_runs/smoke
MODEL_STUDY_DIR ?= $(ARTIFACT_DIR)/eval_runs/silent_failure_study
REPORT_DIR ?= $(ARTIFACT_DIR)/reports/smoke
REPLAY_WORKSPACE ?= /tmp/sandboxed-agent-eval-gates-replay

.PHONY: test smoke gate model-study report ci

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

ci: test smoke gate model-study report

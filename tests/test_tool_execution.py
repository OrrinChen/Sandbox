from sandboxed_agent_eval_harness.agents import OracleToolSelectionAgent
from sandboxed_agent_eval_harness.evaluation.runner import run_evaluation
from sandboxed_agent_eval_harness.tasks import default_task_suite
from sandboxed_agent_eval_harness.tools import FixtureToolExecutor, default_tool_registry
from sandboxed_agent_eval_harness.tracing import load_trace_events


def test_fixture_tool_executor_reads_finance_fixture(tmp_path):
    executor = FixtureToolExecutor(default_tool_registry())
    sandbox = executor.create_sandbox(_task("finance-aapl-revenue-2023"), tmp_path / "workspace")

    result = executor.execute(
        "financial_statement.lookup",
        {"ticker": "AAPL", "fiscal_year": 2023, "statement": "income"},
        sandbox,
    )

    assert result["ticker"] == "AAPL"
    assert result["fiscal_year"] == 2023
    assert result["statement"] == "income"
    assert result["source"] == "aapl-2023-10k-income"
    assert result["values"]["revenue"] == 383285


def test_fixture_tool_executor_writes_csv_output_and_state_diff(tmp_path):
    task = _task("data-sales-region-summary")
    executor = FixtureToolExecutor(default_tool_registry())
    sandbox = executor.create_sandbox(task, tmp_path / "workspace")

    before = sandbox.snapshot()
    read_result = executor.execute("csv.read", {"path": "fixtures/data/regional_sales.csv"}, sandbox)
    group_result = executor.execute(
        "csv.group_metrics",
        {
            "path": "fixtures/data/regional_sales.csv",
            "group_by": "region",
            "metric": "revenue",
            "output_path": "summary_by_region.csv",
        },
        sandbox,
    )
    diff = before.diff(sandbox.snapshot()).to_dict()

    assert read_result == {
        "path": "fixtures/data/regional_sales.csv",
        "columns": ["region", "product", "revenue"],
        "rows": 6,
    }
    assert group_result == {"rows": 3, "output_path": "summary_by_region.csv"}
    assert diff == {"added": ["summary_by_region.csv"], "modified": [], "deleted": []}
    assert sandbox.read_text("summary_by_region.csv") == "region,revenue\nwest,5100\neast,3300\ncentral,2350\n"


def test_fixture_tool_executor_patches_code_and_runs_unit_tests(tmp_path):
    task = _task("coding-discount-total-fix")
    executor = FixtureToolExecutor(default_tool_registry())
    sandbox = executor.create_sandbox(task, tmp_path / "workspace")

    before = sandbox.snapshot()
    patch_result = executor.execute(
        "code.patch",
        {
            "path": "fixtures/code/discount.py",
            "replacements": [
                {
                    "old": "return sum(prices) - discount",
                    "new": "return sum(prices) * (1 - discount)",
                }
            ],
        },
        sandbox,
    )
    unit_result = executor.execute(
        "python.unit_tests",
        {"test_path": "fixtures/code/test_discount.py"},
        sandbox,
    )
    diff = before.diff(sandbox.snapshot()).to_dict()

    assert patch_result == {"path": "fixtures/code/discount.py", "replacements_applied": 1}
    assert unit_result == {"passed": True, "tests_run": 2, "failures": 0}
    assert diff == {"added": [], "modified": ["fixtures/code/discount.py"], "deleted": []}


def test_fixture_tool_executor_solves_newsvendor_and_writes_solution(tmp_path):
    task = _task("optimization-newsvendor-order")
    executor = FixtureToolExecutor(default_tool_registry())
    sandbox = executor.create_sandbox(task, tmp_path / "workspace")

    before = sandbox.snapshot()
    result = executor.execute(
        "optimization.solve_newsvendor",
        {
            "path": "fixtures/optimization/newsvendor.json",
            "output_path": "newsvendor_solution.json",
        },
        sandbox,
    )
    diff = before.diff(sandbox.snapshot()).to_dict()

    assert result == {
        "output_path": "newsvendor_solution.json",
        "order_quantity": 120,
        "service_level": 1.0,
        "expected_cost": 20.0,
        "source": "newsvendor-fixture-v1",
    }
    assert diff == {"added": ["newsvendor_solution.json"], "modified": [], "deleted": []}


def test_evaluation_runner_uses_executable_fixture_tool_results(tmp_path):
    suite = default_task_suite()
    task = _task("data-sales-region-summary")
    summary = run_evaluation(
        suite=suite,
        baselines=[OracleToolSelectionAgent()],
        trials_per_task=1,
        output_dir=tmp_path,
    )

    data_run = next(run for run in summary.runs if run.task_id == task.task_id)
    events = load_trace_events(data_run.trace_path)
    csv_read_result = next(
        event.payload["result"]
        for event in events
        if event.event_type == "tool_result" and event.payload["tool_name"] == "csv.read"
    )
    state_diff = next(event.payload for event in events if event.event_type == "state_diff")

    assert data_run.passed is True
    assert data_run.metrics["tool_execution_mode"] == "fixture_adapter"
    assert data_run.metrics["executed_tool_calls"] == 2
    assert csv_read_result["columns"] == ["region", "product", "revenue"]
    assert csv_read_result["rows"] == 6
    assert state_diff == {"added": ["summary_by_region.csv"], "modified": [], "deleted": []}


def _task(task_id):
    return next(task for task in default_task_suite().tasks if task.task_id == task_id)

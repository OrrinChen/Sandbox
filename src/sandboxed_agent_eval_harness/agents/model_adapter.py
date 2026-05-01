"""Agent baseline wrapper for model adapters."""

from __future__ import annotations

from sandboxed_agent_eval_harness.agents.baselines import AgentBaseline, AgentRunPlan, PlannedToolCall
from sandboxed_agent_eval_harness.models import RecordedModelAdapter
from sandboxed_agent_eval_harness.schemas import TaskSpec


class ModelAdapterAgent(AgentBaseline):
    """Expose recorded model adapter output through the evaluation runner baseline API."""

    def __init__(self, adapter: RecordedModelAdapter) -> None:
        self.adapter = adapter
        self.name = adapter.name
        self.model = adapter.model
        self.prompt_version = adapter.prompt_version

    def run(self, task: TaskSpec, attempt_index: int = 0) -> AgentRunPlan:
        record = self.adapter.plan_for(task.task_id)
        return AgentRunPlan(
            agent_name=self.name,
            final_answer=record["final_answer"],
            final_answer_passed=record["final_answer_passed"],
            tool_calls=[
                PlannedToolCall(
                    tool_name=call["tool_name"],
                    arguments=dict(call["arguments"]),
                    result=dict(call.get("result", {})),
                )
                for call in record["tool_calls"]
            ],
            reported_metrics=dict(record["reported_metrics"]),
            state_diff={"added": [], "modified": [], "deleted": []},
            turns=record["turns"],
            latency_seconds=record["latency_seconds"],
            cost=record["cost"],
            timed_out=record["timed_out"],
        )

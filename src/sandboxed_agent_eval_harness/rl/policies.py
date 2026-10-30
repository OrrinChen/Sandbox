"""CPU policies for baselines and the CI smoke trainer.

The oracle baseline reads hidden expected state, the same way the harness
oracle does. It is an upper bound, not a model. The prompt template and the
mocked categorical policy do not read hidden state.
"""

from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Mapping, Sequence

from sandboxed_agent_eval_harness.agents import OracleToolSelectionAgent
from sandboxed_agent_eval_harness.rl.grpo import categorical_logprob, softmax
from sandboxed_agent_eval_harness.schemas import JsonDict, TaskSpec


@dataclass(frozen=True)
class PolicyDecision:
    action: JsonDict | str
    logprob: float
    behavior_index: int | None = None


class OraclePolicy:
    """Upper bound. Uses the harness oracle, including hidden expected state."""

    name = "oracle"

    def __init__(self, tasks: Sequence[TaskSpec]) -> None:
        self.tasks = {task.task_id: task for task in tasks}
        self.agent = OracleToolSelectionAgent()

    def act(self, observation: Mapping[str, object]) -> PolicyDecision:
        task = self.tasks[str(observation["task_id"])]
        plan = self.agent.run(task)
        calls_done = sum(
            1
            for item in observation.get("history", [])
            if isinstance(item, Mapping) and item.get("type") == "tool_call"
        )
        if calls_done < len(plan.tool_calls):
            call = plan.tool_calls[calls_done]
            action: JsonDict | str = {
                "type": "tool_call",
                "name": call.tool_name,
                "arguments": dict(call.arguments),
            }
        else:
            action = {
                "type": "finish",
                "final_answer": plan.final_answer,
                "reported_metrics": dict(plan.reported_metrics),
            }
        return PolicyDecision(action=action, logprob=0.0)


class PromptTemplatePolicy:
    """Deterministic format scaffold. Not a language-model prompting result."""

    name = "prompt_template"

    def act(self, observation: Mapping[str, object]) -> PolicyDecision:
        del observation
        return PolicyDecision(
            action={
                "type": "finish",
                "final_answer": "Completed the task from the instruction.",
                "reported_metrics": {},
            },
            logprob=0.0,
        )


class MockedCategoricalPolicy:
    """Tiny trainable policy over three scripted behaviors. CPU smoke only."""

    name = "mocked"
    behaviors = ("finish_immediately", "invalid_format", "unknown_tool")

    def __init__(self, seed: int = 0, logits: Sequence[float] | None = None) -> None:
        self.rng = random.Random(seed)
        self.logits = list(logits) if logits is not None else [0.0 for _ in self.behaviors]
        self.reference_logits = list(self.logits)

    def act(self, observation: Mapping[str, object]) -> PolicyDecision:
        turn_index = int(observation.get("turn_index", 0))
        if turn_index == 0 or not hasattr(self, "_index"):
            self._index = self._sample_index()
            self._decision_logprob = categorical_logprob(self.logits, self._index)
        behavior = self.behaviors[self._index]
        return PolicyDecision(
            action=self._action_for(behavior),
            logprob=self._decision_logprob if turn_index == 0 else 0.0,
            behavior_index=self._index,
        )

    def reference_logprob(self, index: int) -> float:
        return categorical_logprob(self.reference_logits, index)

    def update(self, indexes: Sequence[int], advantages: Sequence[float], *, learning_rate: float, beta: float) -> None:
        if len(indexes) != len(advantages) or not indexes:
            raise ValueError("mocked update requires paired indexes and advantages")
        probabilities = softmax(self.logits)
        reference = softmax(self.reference_logits)
        gradient = [0.0 for _ in self.logits]
        for index, advantage in zip(indexes, advantages):
            for logit_index, probability in enumerate(probabilities):
                indicator = 1.0 if logit_index == index else 0.0
                gradient[logit_index] += advantage * (indicator - probability)
        if beta:
            for logit_index, probability in enumerate(probabilities):
                gradient[logit_index] -= beta * (probability - reference[logit_index]) * len(indexes)
        scale = learning_rate / len(indexes)
        self.logits = [logit + scale * component for logit, component in zip(self.logits, gradient)]

    def _sample_index(self) -> int:
        draw = self.rng.random()
        cumulative = 0.0
        for index, probability in enumerate(softmax(self.logits)):
            cumulative += probability
            if draw <= cumulative:
                return index
        return len(self.behaviors) - 1

    @staticmethod
    def _action_for(behavior: str) -> JsonDict | str:
        if behavior == "finish_immediately":
            return {
                "type": "finish",
                "final_answer": "The answer is complete.",
                "reported_metrics": {},
            }
        if behavior == "invalid_format":
            return "this is not an action"
        if behavior == "unknown_tool":
            return {"type": "tool_call", "name": "missing.tool", "arguments": {}}
        raise ValueError(f"unknown mocked behavior: {behavior}")

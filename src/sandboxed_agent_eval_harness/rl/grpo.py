"""GRPO advantage and clipped surrogate used by the mocked and HF trainers.

The objective matches the TRL GRPO trainer: group-relative advantages, a
clipped importance ratio, and a non-negative KL penalty toward a reference
policy. Sequence-level log-probabilities are enough for the mocked policy.
The HF path applies the same surrogate to action-token log-probabilities.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence


@dataclass(frozen=True)
class GRPOLoss:
    total: float
    policy_loss: float
    kl: float

    def to_dict(self) -> dict[str, float]:
        return {"total": self.total, "policy_loss": self.policy_loss, "kl": self.kl}


def group_advantages(rewards: Sequence[float], *, normalization: str = "std", eps: float = 1e-8) -> list[float]:
    if not rewards:
        raise ValueError("GRPO advantages require a non-empty group")
    if normalization not in {"std", "mean"}:
        raise ValueError("advantage normalization must be 'std' or 'mean'")
    mean = sum(rewards) / len(rewards)
    centered = [reward - mean for reward in rewards]
    if normalization == "mean":
        return centered
    variance = sum(value * value for value in centered) / len(rewards)
    std = math.sqrt(variance)
    if std < eps:
        return [0.0 for _ in rewards]
    return [value / (std + eps) for value in centered]


def grpo_loss(
    logprobs: Sequence[float],
    old_logprobs: Sequence[float],
    advantages: Sequence[float],
    *,
    ref_logprobs: Sequence[float] | None = None,
    clip_eps: float = 0.2,
    beta: float = 0.0,
) -> GRPOLoss:
    if not logprobs or not (len(logprobs) == len(old_logprobs) == len(advantages)):
        raise ValueError("logprobs, old_logprobs, and advantages must be the same non-empty length")
    if clip_eps < 0:
        raise ValueError("clip_eps must be non-negative")
    if beta < 0:
        raise ValueError("KL beta must be non-negative")
    if ref_logprobs is not None and len(ref_logprobs) != len(logprobs):
        raise ValueError("ref_logprobs must match the group length")

    surrogate_terms: list[float] = []
    for logprob, old_logprob, advantage in zip(logprobs, old_logprobs, advantages):
        ratio = math.exp(_clip(logprob - old_logprob, -20.0, 20.0))
        clipped_ratio = min(1.0 + clip_eps, max(1.0 - clip_eps, ratio))
        surrogate_terms.append(-min(ratio * advantage, clipped_ratio * advantage))
    policy_loss = sum(surrogate_terms) / len(surrogate_terms)

    kl = 0.0
    if ref_logprobs is not None and beta:
        kl_terms = []
        for logprob, ref_logprob in zip(logprobs, ref_logprobs):
            delta = _clip(ref_logprob - logprob, -20.0, 20.0)
            kl_terms.append(math.exp(delta) - delta - 1.0)
        kl = sum(kl_terms) / len(kl_terms)
    return GRPOLoss(total=policy_loss + beta * kl, policy_loss=policy_loss, kl=kl)


def softmax(logits: Sequence[float]) -> list[float]:
    if not logits:
        raise ValueError("softmax requires at least one logit")
    peak = max(logits)
    shifted = [math.exp(logit - peak) for logit in logits]
    total = sum(shifted)
    return [value / total for value in shifted]


def categorical_logprob(logits: Sequence[float], index: int) -> float:
    probabilities = softmax(logits)
    return math.log(max(probabilities[index], 1e-12))


def scored_token_indices(action_mask: Sequence[int]) -> list[int]:
    """Indexes of action tokens whose next-token log-probability should be trained.

    ``action_mask[i] == 1`` marks an action token at position ``i`` in the full
    token sequence. Position 0 has no conditional log-probability.
    """

    return [index for index, flag in enumerate(action_mask) if flag and index > 0]


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))

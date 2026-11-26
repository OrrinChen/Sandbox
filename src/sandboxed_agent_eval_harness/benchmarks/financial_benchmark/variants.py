"""Retrieval and answer policies for the synthetic financial benchmark."""

from sandboxed_agent_eval_harness.benchmarks.financial_evidence.methods import METHODS


VARIANTS = {method: (method, method) for method in METHODS}
VARIANTS["hybrid_verified"] = ("hybrid", "full_engine")
FINANCIAL_METHODS = tuple(VARIANTS)
SPLIT_METHOD = "hybrid_split_verified"
VARIANTS[SPLIT_METHOD] = ("hybrid_split", "full_engine")

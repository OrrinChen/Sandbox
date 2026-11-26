"""Packaged A1 questions, source chunks, and scoring labels."""

from importlib.resources import files
import json

from sandboxed_agent_eval_harness.schemas import JsonDict


def load_questions() -> JsonDict:
    return _load("a1_questions.json")


def load_full_corpus() -> JsonDict:
    return _load("a1_raw_corpus.json")


def load_labels() -> JsonDict:
    """Read the original task labels for scoring."""
    return _load("a1_labels.json")


def _load(name: str) -> JsonDict:
    return json.loads(files(__package__).joinpath(name).read_text(encoding="utf-8"))

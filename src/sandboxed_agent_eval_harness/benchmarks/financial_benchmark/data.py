"""Load the frozen public corpus and questions from package resources."""

from functools import lru_cache
from hashlib import sha256
from importlib.resources import files
import json


def _resource(name: str):
    return files(__package__).joinpath("data").joinpath(name + ".json")


CROSS_SOURCE_SPLITS = ("cross_source_dev", "cross_source_test")
SPLITS = ("pilot", "dev", "test", "challenge", *CROSS_SOURCE_SPLITS)


def corpus_prefix(split: str) -> str:
    return f"{split}_" if split in ("challenge", *CROSS_SOURCE_SPLITS) else ""


@lru_cache(maxsize=4)
def load_manifest(*, challenge: bool = False, split: str = ""):
    prefix = corpus_prefix("challenge" if challenge else split)
    return json.loads(_resource(prefix + "manifest").read_bytes())


@lru_cache(maxsize=4)
def load_corpus(*, challenge: bool = False, split: str = ""):
    split = "challenge" if challenge else split
    payload = _resource(corpus_prefix(split) + "corpus").read_bytes()
    if sha256(payload).hexdigest() != load_manifest(split=split)["corpus_sha256"]:
        raise ValueError("Financial benchmark corpus does not match its frozen SHA-256")
    return json.loads(payload)


def _read_split_file(name: str):
    payload = _resource(name).read_bytes()
    split = name.rsplit("_", 1)[0]
    expected = load_manifest(split=split).get("split_sha256", {}).get(name + ".json")
    if expected is not None and sha256(payload).hexdigest() != expected:
        raise ValueError(f"Financial benchmark file does not match its frozen SHA-256: {name}")
    return json.loads(payload)


@lru_cache(maxsize=6)
def load_questions(split: str):
    if split not in SPLITS:
        raise ValueError(f"Unknown financial benchmark split: {split}")
    filename = f"{'dev' if split == 'pilot' else split}_questions"
    questions = _read_split_file(filename)
    if split == "pilot":
        pilot_groups = set(load_manifest()["dev_groups"][:4])
        return [row for row in questions if row["company_tickers"][0] in pilot_groups]
    return questions

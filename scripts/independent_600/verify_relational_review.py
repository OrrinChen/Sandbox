"""Recompute the relational curation audit using scikit-learn (curation only)."""

from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path
import re

from sklearn.feature_extraction.text import TfidfVectorizer

from sandboxed_agent_eval_harness.benchmarks.independent import relational


HERE = Path(__file__).resolve().parent
TOKENS = re.compile(r"'(?:[^']|'')*'|[a-z_][a-z_0-9]*|\d+(?:\.\d+)?|<>|<=|>=|[^\s]")
KEYWORDS = set(
    "select from where as and or order by group sum max min avg count rank dense_rank "
    "row_number over partition desc asc limit join left right outer inner cross on using "
    "in not null is coalesce case when then else end with recursive union all intersect "
    "except abs distinct exists having between like substr length round cast integer text "
    "real date lead lag rows preceding following unbounded current window".split()
)
SELECT_SUFFIX = " Submit a SQLite SELECT that produces the requested output using the supplied tables."
CSV_SUFFIX = " Submit a SQLite SELECT that writes the requested CSV report via the CSV export tool."


def sql_shape(sql):
    names = {}
    result = []
    for token in TOKENS.findall(sql.lower()):
        if token[0] == "'" or token[0].isdigit():
            result.append("#")
        elif (token[0].isalpha() or token[0] == "_") and token not in KEYWORDS:
            result.append(names.setdefault(token, str(len(names))))
        else:
            result.append(token)
    return tuple(result)


def verify():
    metadata = json.loads((HERE / "relational_duplicate_review.json").read_bytes())
    bound_files = [
        HERE / "relational_audit.json",
        HERE / "relational_reviewed_pairs.json",
        relational.DATA / "relational_tasks.json",
        relational.DATA / "relational_keys.json",
    ]
    if {f.name: sha256(f.read_bytes()).hexdigest() for f in bound_files} != metadata[
        "bound_files_sha256"
    ]:
        raise ValueError(
            "Source assets or pair dispositions differ from the curation audit"
        )
    reviewed = json.loads((HERE / "relational_reviewed_pairs.json").read_bytes())
    audit = {
        r["task_id"]: r
        for r in json.loads((HERE / "relational_audit.json").read_bytes())
    }
    tasks = relational.index()
    keys = relational.index(True)
    ids = sorted(tasks)
    replacements = set(metadata["accepted_replacements"])
    expected = {(r["a"], r["b"]) for r in reviewed["candidates"]}
    if len(expected) != len(reviewed["candidates"]) or any(
        not r["review"] for r in reviewed["candidates"]
    ):
        raise ValueError("Incomplete pair dispositions")
    if any(
        tuple(sorted((r["a"], r["b"]))) in expected
        for r in metadata["flagged_relations"]
    ):
        raise ValueError("Retained pair marked as equivalent")
    if set(ids) != set(audit) or set(ids) != set(keys):
        raise ValueError("Source, benchmark and key identifiers differ")
    words = []
    groups = []
    shapes = []
    split_membership = defaultdict(set)
    for task_id in ids:
        task = tasks[task_id]
        a = audit[task_id]
        spec = task["instruction"]
        suffix = CSV_SUFFIX if task["domain"] == "file_workflow" else SELECT_SUFFIX
        if not spec.endswith(suffix):
            raise ValueError(f"Unrecognized tool instruction for {task_id}")
        words.append(
            " ".join(
                [
                    a["title"],
                    a["reasoning"],
                    a["incorrect_behavior"],
                    spec[: -len(suffix)],
                ]
            )
        )
        groups.append(task["source_group"])
        split_membership[task["source_group"]].add(task["split"])
        shapes.append(sql_shape(keys[task_id]["reference"]))
    if any(len(splits) != 1 for splits in split_membership.values()):
        raise ValueError("Source group crossed development and test splits")
    vectors = TfidfVectorizer(
        ngram_range=(1, 2), stop_words="english", sublinear_tf=True
    ).fit_transform(words)
    scores = (vectors @ vectors.T).toarray()
    actual = set()
    for i, task_id in enumerate(ids):
        others = sorted(
            (j for j in range(len(ids)) if groups[j] != groups[i]),
            key=lambda j: (-scores[i, j], ids[j]),
        )
        slug = task_id.removeprefix("decision-")
        nearest = set(others[: 3 if slug in replacements else 2])
        for j, other in enumerate(ids):
            if j != i and (
                j in nearest
                or scores[i, j] >= 0.21
                or groups[i] == groups[j]
                or shapes[i] == shapes[j]
            ):
                actual.add(tuple(sorted((slug, other.removeprefix("decision-")))))
    if actual != expected or len(actual) != metadata["final_candidate_pairs"]:
        raise ValueError(
            f"Pair selection diverged: {len(expected - actual)} missing and {len(actual - expected)} extra"
        )
    return {
        "tasks": len(ids),
        "reviewed_final_pairs": len(actual),
        "retained_flagged_pairs": 0,
    }


if __name__ == "__main__":
    print(json.dumps(verify(), sort_keys=True))

"""Show a specific cell-level mismatch after the original workbook scorer rejects a submission."""

import json
from pathlib import Path
import sys
import tempfile

from sandboxed_agent_eval_harness.benchmarks.independent import spreadsheets


def mismatch(task, candidate):
    public = spreadsheets._public()[task]
    if not spreadsheets._candidate_ok(task, candidate):
        return {"stage": "formula_validation", "sheet": public["worksheet"]}
    key = spreadsheets._private()[task]
    with tempfile.TemporaryDirectory() as temporary:
        work = Path(temporary)
        for scenario, (archive, grid) in zip(
            ("public", "held_out"), spreadsheets.SCENARIOS
        ):
            src = work / (scenario + ".xlsx")
            src.write_bytes(
                spreadsheets.render(
                    spreadsheets._input(task, archive),
                    public["worksheet"],
                    candidate["formulas"],
                )
            )
            spreadsheets.recalculate([src], work / "output", 180)
            actual = spreadsheets.sheet_values(
                (work / "output" / src.name).read_bytes(),
                public["worksheet"],
                set(key["addresses"]),
            )
            expected = key[grid]
            for cell in sorted(set(expected) | set(actual), key=spreadsheets._coord):
                a = {cell: actual[cell]} if cell in actual else {}
                e = {cell: expected[cell]} if cell in expected else {}
                if not spreadsheets.equivalent(a, e):
                    return {
                        "stage": "recalculated",
                        "input": scenario,
                        "sheet": public["worksheet"],
                        "cell": cell,
                        "expected": expected.get(cell),
                        "actual": actual.get(cell),
                        "submitted_formula": candidate["formulas"].get(cell),
                    }
    raise ValueError(f"Expected a failed submission when explaining {task}")


if __name__ == "__main__":
    if Path(sys.prefix).resolve() not in Path(spreadsheets.__file__).resolve().parents:
        raise RuntimeError(
            "The source of diagnostic evidence must be the installed scorer"
        )
    cases = json.load(sys.stdin)
    print(
        json.dumps(
            [mismatch(c["task_id"], c["candidate"]) for c in cases], ensure_ascii=False
        )
    )

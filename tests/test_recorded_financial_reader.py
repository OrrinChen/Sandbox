import json
from pathlib import Path
import runpy

import pytest

from sandboxed_agent_eval_harness.benchmarks.financial_benchmark.scoring import score_answer


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "compare_recorded_financial_reader.py"


def test_recorded_reader_maps_citations_without_repairing_answers():
    answer_payload = runpy.run_path(str(SCRIPT))["_answer_payload"]
    label = {"verdict": "answer", "unit": "usd", "answer_value": "5", "evidence_ids": ["fact-a"]}
    hits = [{"evidence_id": "fact-a"}]
    response = {"row": 1, "verdict": "answer", "unit": "usd", "answer_value": "5", "citations": ["A"]}
    references = {"A": "fact-a"}
    assert score_answer(label, answer_payload(response, references), hits, 5).passed
    for changes in ({"citations": ["A", "B"]}, {"citations": ["fact-a"]}, {"answer_value": 5}):
        assert not score_answer(label, answer_payload({**response, **changes}, references), hits, 5).passed


def test_recorded_reader_refuses_changed_model_inputs(tmp_path):
    script = runpy.run_path(str(SCRIPT))
    cases = [({"row": row, "question": "question", "evidence": []}, {"row": row}, {}, None)
             for row in range(1, 81)]
    script["_prepare"](tmp_path, cases)
    for index, batch in enumerate(script["_batches"](cases), 1):
        (tmp_path / f"responses-{index}.json").write_text(json.dumps([{"row": case[0]["row"]} for case in batch]))
    responses, _ = script["_load_responses"](tmp_path, cases)
    assert len(responses) == 80
    (tmp_path / "inputs-2.json").write_text("[]")
    with pytest.raises(ValueError, match="differ from the archived top five"):
        script["_load_responses"](tmp_path, cases)

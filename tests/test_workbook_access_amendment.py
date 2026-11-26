import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import run_workbook_access_amended as amended


def test_amendment_changes_model_allowlist_in_its_private_collector_only():
    new = amended.alternate_host()
    assert new.ask.__globals__["MODELS"] == (amended.ALTERNATE,)
    assert amended.host.ask.__globals__["MODELS"] == (
        amended.ORIGINAL_ASTRA,
        amended.SOL,
    )
    assert new.experiment.__globals__["round_record"].__globals__["ask"] is new.ask


def test_capacity_trigger_is_required_and_source_files_remain_immutable(
    tmp_path, monkeypatch
):
    parent = tmp_path / "formal"
    parent.mkdir()
    monkeypatch.setattr(amended, "PARENT", parent)
    rule = {
        "initial_registration_sha256": amended.PARENT_SHA,
        "eligible_alternate": amended.ALTERNATE,
        "same_budget_and_public_inputs": True,
        "observed_pre_score": {"formal_score_opened": False},
        "registered_at": "2026-11-25T08:37:32+00:00",
    }
    rule_path = tmp_path / "capacity_rule.json"
    rule_path.write_text(json.dumps(rule))
    activation = {
        "original_registration_sha256": amended.PARENT_SHA,
        "capacity_rule_sha256": amended.host.digest(rule_path),
        "active_professional_model": amended.ALTERNATE,
        "frozen_results_opened": False,
        "time": "2026-11-25T08:39:20+00:00",
        "elapsed_seconds": 479,
        "observed": {
            "sol_batches": 50,
            "sol_turns": 150,
            "astra_batches": 0,
            "astra_turns": 0,
        },
    }
    activation_path = tmp_path / "capacity_activation.json"
    activation_path.write_text(json.dumps(activation))
    with pytest.raises(ValueError, match="capacity criterion"):
        amended.capacity_receipts()
    activation["elapsed_seconds"] = 480
    activation_path.write_text(json.dumps(activation))
    assert amended.capacity_receipts()[
        "capacity_activation_sha256"
    ] == amended.host.digest(activation_path)
    existing = tmp_path / "copy.json"
    amended.checked_copy(activation_path, existing, True)
    existing.write_text("{}")
    with pytest.raises(ValueError, match="differs"):
        amended.checked_copy(activation_path, existing, True)
    assert json.loads(activation_path.read_bytes()) == activation


def test_efficient_fallback_checks_intermediate_partial_turn_receipt(
    tmp_path, monkeypatch
):
    import run_workbook_access_efficient as efficient

    runner = efficient.driver().alternate_host()
    assert runner.ask.__globals__["MODELS"] == (efficient.TERRA,)
    assert amended.ALTERNATE == "gpt-6-astra"
    middle = tmp_path / "available"
    monkeypatch.setattr(efficient, "MID", middle)
    monkeypatch.setattr(efficient.host, "STUDY", tmp_path)
    rule = {
        "predecessor_registration_sha256": efficient.MID_SHA,
        "eligible_alternate": efficient.TERRA,
        "score_opened": False,
        "sol_complete_batches": 50,
        "current_professional_batches": 0,
        "registered_at": "2026-11-25T08:47:00+00:00",
    }
    rule_path = tmp_path / "efficient_capacity_rule.json"
    rule_path.write_text(json.dumps(rule))
    activation = {
        "predecessor_registration_sha256": efficient.MID_SHA,
        "capacity_rule_sha256": amended.host.digest(rule_path),
        "active_second_model": efficient.TERRA,
        "frozen_results_opened": False,
        "observed": {
            "sol_batches": 50,
            "professional_batches": 0,
            "professional_turns": 1,
        },
        "elapsed_seconds": 480,
        "time": "2026-11-25T08:48:33+00:00",
    }
    (tmp_path / "efficient_capacity_activation.json").write_text(json.dumps(activation))
    with pytest.raises(ValueError, match="switch is invalid"):
        efficient.capacity()
    partial = (
        middle / "turns" / amended.ALTERNATE / "fixed" / "batch" / "inspect-1.json"
    )
    partial.parent.mkdir(parents=True)
    partial.write_text('{"fixture": true}')
    assert efficient.capacity()["excluded_intermediate_turns_sha256"] == {
        str(partial.relative_to(middle)): amended.host.digest(partial)
    }

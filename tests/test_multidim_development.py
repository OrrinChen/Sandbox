"""Check that paired readers receive only their assigned view of the locked fixture."""
from pathlib import Path

import pytest


def test_stage_isolation_and_freeze(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    import run_multidim_development as runner

    root = tmp_path / "pilot"
    runner.freeze(root)
    private_path = root / "private/labels.json"
    labels = {q["row"]: q for q in runner.read(private_path)}
    assert len(labels) == 32
    first = {}
    for b in runner.BATCHES:
        rows = runner.read(root / "initial" / f"inputs-{b}.json")
        assert len(rows) == len({labels[r["row"]]["pair_id"] for r in rows}) == 8
        assert all(set(r) == {"row", "question", "evidence"} for r in rows)
        for row in rows:
            assert [hit["ref"] for hit in row["evidence"]] == list("ABCDE")
            assert all(set(hit) == {"ref", "text"} for hit in row["evidence"])
            first[row["row"]] = {"row": row["row"], "choice": None, "value": None, "citations": []}
        runner.write_once(root / "initial" / f"responses-{b}.json", [first[r["row"]] for r in rows])
    # The other arms can be prepared even when the private label file is physically unavailable.
    hidden = private_path.rename(tmp_path / "labels.json")
    runner.lock_initial(root)
    assert (root / "initial/prompt.txt").read_bytes() == (root / "retry/prompt.txt").read_bytes()
    for b in runner.BATCHES:
        name = f"inputs-{b}.json"
        assert (root / "initial" / name).read_bytes() == (root / "retry" / name).read_bytes()
        rows = runner.read(root / "initial" / name)
        audits = runner.read(root / "audit" / name)
        assert audits == [dict(r, initial_answer=first[r["row"]]) for r in rows]
    hidden.rename(private_path)
    path = root / "initial/responses-1.json"
    path.write_text(path.read_text() + " ")
    with pytest.raises(ValueError, match="changed after locking"):
        runner.score(root)

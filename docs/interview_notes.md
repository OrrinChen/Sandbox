# Interview Notes

## Positioning

This is an AI infrastructure and LLM eval project, not an agent demo. The problem is that final-answer-only grading can look successful while tool choice, arguments, state mutation, numeric outputs, citations, or constraints are wrong.

## Key Result

Final-answer-only grading overestimated validated correctness by 56.2 percentage points; deterministic validators caught 180 silent failures across 320 recorded offline runs.

The evidence uses 64 fixture-backed benchmark tasks and 5 recorded offline model profiles. It is reproducible without API keys.

## What To Emphasize

- Deterministic validators were chosen before LLM-as-judge to make failures auditable.
- JSONL trace replay is central because unreplayable failures are weak evidence.
- The report separates final-answer pass rate from validator pass rate.
- Root-cause categories expose whether failures came from tools, arguments, state, numbers, citations, constraints, replay divergence, timeout, cost, or final-answer overclaim.
- CI regression gates fail runs on task success drops, pass@k drops, failure taxonomy caps, and replay divergences.

## Resume bullet

Built a deterministic LLM tool-use eval harness exposing 180 silent failures missed by final-answer grading, with typed tool specs, workspace/container-backed evaluation isolation, JSONL trace replay, root-cause failure reports, and CI regression gates over 64 fixture-backed tasks and 320 recorded offline runs.

## Interview Risks And Answers

Question:
Is this a live model benchmark?

Answer:
No. The portfolio evidence is recorded offline and fixture-backed. The project has a credentials-gated live workflow, but the default evidence is reproducible and key-free.

Question:
Is the Docker backend a security sandbox?

Answer:
No. It is evaluation isolation and reproducibility support, not a security product.

Question:
Why not use LLM-as-judge?

Answer:
The project is about silent tool-use failures. Deterministic validators and replayable traces make the failure mode inspectable and reproducible.

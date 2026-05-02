# Limitations

## Evidence Boundary

The main portfolio evidence is recorded offline. It uses controlled model-like profiles over fixture-backed tasks so the results are reproducible without API keys or network calls.

This is not a live-provider benchmark. It should not be described as evidence that a specific public model provider fails at a specific rate.

## Benchmark Boundary

The benchmark has 64 fixture-backed tasks across finance, citation, data analysis, file workflow, coding, and optimization. It is useful for validating the harness and demonstrating failure taxonomy coverage, but it is not a replacement for production traffic or third-party benchmark datasets.

## Sandbox Boundary

The default workspace backend constrains path operations through project APIs and records state diffs. The optional Docker backend adds container command envelopes with network disabled, read-only fixture mounts, writable workspace mounts, and resource limits.

This is evaluation isolation, not a security product.

## Scoring Boundary

Final-answer pass is a deterministic harness proxy. It is used to show the gap between answer-only scoring and validator-backed correctness, not to claim semantic answer quality.

## Live Provider Boundary

The live provider workflow is credentials-gated and fail-closed without `--live`. Default tests, CI, and portfolio report generation do not call external APIs.

Manual live outputs should be reviewed and converted into recorded fixtures before they are used as reproducible evidence.

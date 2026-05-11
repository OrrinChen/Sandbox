# Architecture

The harness is evaluation infrastructure for tool-using agents. It tests whether a run used tools correctly, mutated state correctly, cited evidence correctly, and stayed within constraints.

## Pipeline

```text
typed task schema
-> typed tool registry
-> fixture-backed execution
-> JSONL trace capture
-> deterministic validators
-> trace replay
-> regression gates
-> portfolio report
```

## Components

- `typed task schema`: defines instructions, visible files, available tools, hidden expected state, validators, cost limits, and timeout limits.
- `typed tool registry`: declares tool input/output schemas, permissions, side effects, state mutation contracts, and failure modes.
- `FixtureToolExecutor`: executes local finance, transcript, CSV, coding, and optimization tools without network access.
- `FileSystemSandbox` and backend abstraction: provide workspace-scoped fixture execution and optional Docker evaluation isolation.
- `JSONL trace` capture: records user messages, agent messages, tool calls, tool results, state diffs, validator results, timeouts, and errors.
- `deterministic validators`: check schema, tool sequence, arguments, state, numeric values, citations, constraints, unit tests, policy terms, and cost/latency.
- `TraceReplayExecutor`: replays supported fixture-backed tool calls and detects result or state divergence.
- `regression gates`: enforce success rate, pass@k, failure taxonomy caps, and replay divergence thresholds.
- Optional MCP adapter: maps fixture-backed MCP `tools/list` and `tools/call` JSON-RPC records into typed harness tool descriptors, tool-call traces, tool-result traces, and deterministic replay inputs.

## Evidence Flow

`make portfolio-report` runs the recorded model matrix, writes a portfolio JSON/Markdown report, exports model/failure/domain CSV tables, and generates replayable case studies from trace artifacts.

The system intentionally avoids LLM-as-judge in the default path. Claims are tied to deterministic validators and replayable trace data.

Optional MCP support is an evaluation input layer, not a live agent server. The default smoke path uses local fixtures, does not require credentials, and does not open a network transport.

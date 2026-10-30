# Agentic RL design

The recorded harness study is the evaluation environment. A policy acts by calling fixture tools. The existing deterministic validators are the outcome reward. This document specifies the loop, the reward, the stack, the split, and the GPU command. It does not report a trained-model result. Those cells are **not yet run**.

## Environment

`SandboxToolEnv` follows the Gymnasium `reset` / `step` contract without a Gymnasium dependency, so CI stays free of RL libraries.

- `reset(task_id=...)` returns an observation and an info dict.
- `step(action)` returns `(observation, reward, terminated, truncated, info)`.
- One action is one turn. A tool call executes through `FixtureToolExecutor` in a fresh workspace sandbox and appends the tool result to the history. A finish action ends the episode and runs the validators.
- The horizon is the task's `max_turns`. Hitting it without a finish truncates the episode and scores it as a timeout.
- Actions are either objects (`{"type": "tool_call"|"finish", ...}`) or exactly one tagged block: `<tool_call>{json}</tool_call>` or `<finish>{json}</finish>`. A transcript parser accepts several tool calls followed by one finish, which is the single-completion ablation.

The observation contains the instruction, the available tools' input schemas, visible file names, the turn counter, and the history of tool calls and tool results. It does not contain `hidden_expected_state`, `gold_outputs`, `success_criteria`, `known_failure_traps`, or `failure_taxonomy_traps`. `success_criteria` in the task files includes gold numbers (for example the newsvendor order quantity). Putting that text in the prompt would let a policy copy the answer. `reset` raises if the initial observation contains those oracle fields. Tool results may later contain numbers the tool just returned. That is the task, not a leak.

Termination:

| Event | Flag | Reward |
| --- | --- | --- |
| Parsed `<finish>` or finish object | `terminated` | Outcome reward |
| Turn limit, or `force_terminate` | `truncated` | Outcome reward, with `timed_out` |
| Malformed action | neither, until the turn limit | 0 until the terminal step |

Intermediate steps return reward 0. The return of an episode is the terminal scalar. GRPO therefore assigns one reward to the whole multi-turn trajectory.

## Reward

The outcome bit is the harness pass bit: every validator named by the task passed, tool execution did not fail, and the episode did not time out. Scoring calls the same `_validate_plan` path as the evaluation runner, including the trading validators when the task lists them. The final-answer-only bit is not the outcome. A non-empty answer that fails validators is a silent failure, using the same definition as the recorded study (`final_answer` non-empty and validators failed).

Weights in `configs/agentic_rl.json`:

| Term | Weight | When it applies |
| --- | ---: | --- |
| Outcome | 1.0 | All validators passed and the episode did not time out |
| Silent failure | 0.2 | Non-empty final answer and not passed |
| Format error | 0.05 each | Unparseable action |
| Invalid tool | 0.05 each | Unknown tool, schema failure, or fixture execution error |
| Incomplete | 0.05 | No final answer and not passed |

Invariants, checked by tests:

- A passing episode scores at least 0.05 and at most 1.0, even if it also collected penalties.
- A failing episode scores at most 0. Format compliance alone cannot be a positive reward.
- A success therefore outranks every failure. Penalties only rank failures, and they only shave a success down to the floor.

That last point is the anti-hacking constraint on the scalar. Two further checks run at eval time, because the scalar is still gameable:

- `refusal_hack`: silent-failure count fell, incomplete count rose, and task success did not rise. The policy stopped answering.
- `reward_without_success`: mean reward rose and task success did not. Do not report that as an improvement.

The numbers to publish are held-out task success and silent-failure count. The scalar is a training signal.

KL to the reference policy (beta 0.04 by default) is part of the GRPO loss, not part of the environment reward. A beta of 0 is an ablation, not the default. Group-relative advantages are zero when every sample in the group has the same reward, so a group of identical failures does not move the policy.

## Training stack

**Choice: TRL's GRPO objective, with a multi-turn rollout this repo owns.**

The recommended GPU command is `--backend hf`. It loads `Qwen/Qwen2.5-1.5B-Instruct`, attaches a LoRA adapter (rank 16, alpha 32, attention and MLP projections), samples one action per turn, executes the fixture tool, and applies a clipped GRPO surrogate to the action-token log-probabilities. Tool-result tokens are masked out of the loss. The reference policy is the same model with the adapter disabled. The surrogate is the one TRL's `GRPOTrainer` implements: group-normalized advantage, importance ratio clipped at 0.2, plus the Schulman k3 KL estimator scaled by `kl_beta`.

`--backend trl` is the single-completion ablation. It constructs `trl.GRPOTrainer` with `reward_funcs` set to a function that parses the completion as an action transcript and steps `SandboxToolEnv`. Tool results inside that completion cannot condition later tokens. Use it to see how much of the gain, if any, depends on interactive tool results. Stock `num_generations` is this config's `group_size` (4), and `remove_unused_columns` stays false so the reward can see `task_id`.

verl and OpenRLHF are the wrong default here. Both expect a Ray or vLLM service and a cluster job for what is a 1.5B LoRA run against an in-process fixture executor. They would not score these tasks more directly than a reward function that already calls the harness. TRL's experimental `environment_factory` was also set aside: it requires `transformers>=5.2`, the API is marked experimental, and several harness tool names contain dots, so they are not legal Python tool methods.

CPU CI never imports that stack. `--backend mocked` trains a three-way categorical policy (`finish_immediately`, `invalid_format`, `unknown_tool`) with the same advantage and loss functions. `--dry-run` on `hf`, `trl`, or `sft` prints the command and does not touch the network.

## Baselines

| Baseline | What it is | Status |
| --- | --- | --- |
| Oracle | Existing harness oracle. Reads hidden expected state. Upper bound on the validators, not a model. | CPU, used to test the env |
| Prompt template | Deterministic finish with no tools and no gold fields. Tests the eval script. | CPU smoke only |
| Base model | `Qwen/Qwen2.5-1.5B-Instruct` with a bare instruction prompt (`--prompt-mode bare`) | not yet run |
| Prompting-only | Same checkpoint with the tool-use prompt (`--prompt-mode tool`). No weight update. | not yet run |
| SFT | Oracle action traces on the train families only, then TRL `SFTTrainer` for one epoch | export is implemented; training is not yet run |
| GRPO | Multi-turn `--backend hf` | not yet run |

SFT rows are produced by:

```bash
python -m sandboxed_agent_eval_harness.rl.sft_export --config configs/agentic_rl.json --output artifacts/agentic_rl/sft_train.jsonl
```

The export refuses to be described as training. Held-out task ids are not written. The oracle traces do contain gold answers, because that is the expert policy. They stay on the train side of the family split.

## Ablations

None of these have been run. The config keys already exist.

| Ablation | Values | What it answers |
| --- | --- | --- |
| Reward components | outcome only; outcome + silent penalty; full penalty set | Whether the silent-failure penalty changes success, or only the refusal rate |
| Group size | 2, 4, 8 | Variance of the group baseline versus wall-clock |
| KL beta | 0, 0.01, 0.04, 0.1 | How hard the reference policy holds the format |
| Advantage normalization | `std` (GRPO) and `mean` (Dr. GRPO, no division by group std) | Whether a few large rewards dominate the update |
| Rollout | `--backend hf` versus `--backend trl` | Interactive tool results versus one-shot transcripts |

A first grid, if a GPU is available, is full reward versus outcome-only, group size 4 versus 8, and beta 0 versus 0.04. That is eight runs. Report success and silent failures for each, plus the anti-hack flags. Do not rank runs by the scalar reward alone.

## Train / held-out split

The 64-task benchmark is the pool. Rows that share a family share gold answers; `finance-aapl-revenue-benchmark-01` and `-06` are the same task with a different sentence index. The split unit is the family, not the row.

`task_family` strips the `-benchmark` infix and a trailing `-NN` clone suffix. `random.Random(7)` shuffles the sorted family names and holds out `round(11 * 0.25) = 3` families.

Held out (28 tasks):

- `coding-discount-total-fix` (12)
- `data-inventory-stockout-report` (4)
- `optimization-newsvendor-order` (12)

Train (36 tasks):

- `citation-nvda-datacenter-evidence` (8)
- `data-churn-plan-rate` (4)
- `data-sales-region-summary` (4)
- `file-workflow-churn-output` (2)
- `file-workflow-inventory-output` (2)
- `file-workflow-sales-output` (4)
- `finance-aapl-revenue` (6)
- `finance-msft-cloud-margin` (6)

The initial eight-task suite is not used as held-out data. Those tasks are the templates the benchmark clones were copied from. The trading suite is not mixed in. It is a different domain and would not be a clean held-out slice of the 64-task study.

Changing `seed` or `held_out_fraction` changes the split. The test locks seed 7 to the three families above.

## Compute estimate

This is an order-of-magnitude estimate, not a measurement. No GPU run has been timed.

- Model: Qwen2.5-1.5B-Instruct. LoRA rank 16 on the attention and MLP projections. Trainable parameters are a small slice of the 1.5B weights. Qwen2.5-3B-Instruct is the larger option in the same command, by changing `model_name`. Start with 1.5B.
- One epoch over 36 train tasks, group size 4, up to 4 turns, 256 new tokens per turn. Upper bound on generated tokens: `36 * 4 * 4 * 256 = 147,456`, plus a training forward and backward on the action tokens only. Real episodes are often shorter than 4 turns.
- Memory: 1.5B bf16 weights are about 3 GB. A frozen reference forward, LoRA, and a group of 4 sequences fit on a 24 GB GPU with gradient checkpointing, which the config turns on. 3B is roughly twice the weight memory and is tight at group size 8.
- Wall clock on one 24 GB GPU is in the range of minutes to a few hours for one 1.5B epoch, depending on generation speed. It is not a multi-day cluster job. The eight-run ablation grid scales that by about eight. SFT is one supervised pass over the train traces and is cheaper than GRPO because it does not sample a group.

Do not treat this paragraph as a benchmark.

## Results table

Fill this only from a real `rl.eval` JSON file. Until then every model cell stays `not yet run`. Smoke output is labeled `cpu_smoke_mocked_policy` and does not belong in this table.

| Run | Split | Held-out tasks | Task success | Silent failures | Incomplete | Anti-hack flags | Status |
| --- | --- | ---: | --- | --- | --- | --- | --- |
| Base, bare prompt | seed 7 held-out families | 28 | not yet run | not yet run | not yet run | not yet run | not yet run |
| Prompting-only, tool prompt | seed 7 held-out families | 28 | not yet run | not yet run | not yet run | not yet run | not yet run |
| SFT | seed 7 held-out families | 28 | not yet run | not yet run | not yet run | not yet run | not yet run |
| GRPO, multi-turn | seed 7 held-out families | 28 | not yet run | not yet run | not yet run | not yet run | not yet run |
| GRPO, TRL single completion | seed 7 held-out families | 28 | not yet run | not yet run | not yet run | not yet run | not yet run |

Recorded harness evidence, which this extension does not replace: offline recorded, fixture-backed, no live API by default. Final-answer-only grading overestimated validated correctness by 56.2 percentage points; deterministic validators caught 180 silent failures across 64 tasks and 320 runs.

## Commands

Install on the GPU machine:

```bash
pip install -e ".[agentic-rl]"
```

Multi-turn GRPO:

```bash
python -m sandboxed_agent_eval_harness.rl.train --config configs/agentic_rl.json --backend hf --output-dir artifacts/agentic_rl/qwen25_1p5b_grpo
```

TRL single-completion ablation:

```bash
python -m sandboxed_agent_eval_harness.rl.train --config configs/agentic_rl.json --backend trl --output-dir artifacts/agentic_rl/qwen25_1p5b_grpo_trl
```

SFT, after the export command above:

```bash
python -m sandboxed_agent_eval_harness.rl.train --config configs/agentic_rl.json --backend sft --sft-data artifacts/agentic_rl/sft_train.jsonl --output-dir artifacts/agentic_rl/qwen25_1p5b_sft
```

Held-out eval:

```bash
python -m sandboxed_agent_eval_harness.rl.eval --config configs/agentic_rl.json --split held_out --policy hf --prompt-mode bare --model-name Qwen/Qwen2.5-1.5B-Instruct --output artifacts/agentic_rl/heldout_base.json
python -m sandboxed_agent_eval_harness.rl.eval --config configs/agentic_rl.json --split held_out --policy hf --prompt-mode tool --model-name Qwen/Qwen2.5-1.5B-Instruct --output artifacts/agentic_rl/heldout_prompt.json
python -m sandboxed_agent_eval_harness.rl.eval --config configs/agentic_rl.json --split held_out --policy hf --prompt-mode tool --model-path artifacts/agentic_rl/qwen25_1p5b_sft --output artifacts/agentic_rl/heldout_sft.json
python -m sandboxed_agent_eval_harness.rl.eval --config configs/agentic_rl.json --split held_out --policy hf --prompt-mode tool --model-path artifacts/agentic_rl/qwen25_1p5b_grpo --output artifacts/agentic_rl/heldout_grpo.json
```

CPU smoke, which CI already runs:

```bash
make rl-smoke
```

## What is verified without a GPU

- The environment executes fixture tools. The harness oracle scores 1.0 on the finance task and on the coding task, including the state diff.
- A non-empty wrong answer with no tool call is a silent failure and scores below 0.
- Initial observations for all 64 benchmark tasks hide oracle fields.
- GRPO advantages are group-centered, the clipped surrogate matches a hand-computed example, and the k3 KL is 0 when the policy matches the reference.
- The mocked trainer runs two steps and writes a smoke report whose model status is `not yet run`.

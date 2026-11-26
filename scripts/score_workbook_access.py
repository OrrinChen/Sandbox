"""Score sealed workbook inspections and reproduce failures with the archived offline wheel."""

import argparse
from collections import Counter
import csv
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from run_independent_comparison import digest, expand, load, predictions, seal, suite
from smoke_independent_wheel import OFFLINE_PIP, network_barrier

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / "scripts/independent_600/comparison"
DEFAULT_ROOT = ROOT / "scripts/workbook_access/paired"
WHEELS = ROOT / "artifacts/independent-600-wheel"
ARMS = ("fixed", "browse")


def expanded(submission):
    try:
        return expand(submission)
    except (ValueError, TypeError, KeyError, IndexError, AttributeError):
        return {}


def read_archive(tasks):
    score_path = OLD / "score.json"
    cert = load(OLD / "installed_regrade.json")
    original = load(score_path)
    if (
        cert["score_sha256"] != digest(score_path)
        or cert["release_sha256"] != suite.verify_release()
        or original["prediction_lock_sha256"] != digest(OLD / "prediction_lock.json")
        or predictions(OLD) != load(OLD / "prediction_lock.json")
    ):
        raise ValueError(
            "Frozen historical challenge or its installed-wheel verification differs"
        )
    previous = {}
    candidates = {}
    for arm in ("direct", "self_check"):
        rows = {
            r["task"]: r
            for r in original["rows"]
            if r["arm"] == arm and r["task"].startswith("sheet-")
        }
        raw = {}
        for path in sorted((OLD / "recordings" / arm).glob("spreadsheets-*.json")):
            for task, sub in load(path)["submissions"].items():
                if task in raw:
                    raise ValueError(f"Repeated historical task {task}")
                raw[task] = expanded(sub)
        if set(raw) != set(tasks) or set(rows) != set(tasks):
            raise ValueError("Historical tasks differ from the new frozen roster")
        for task, candidate in raw.items():
            if rows[task]["candidate_sha256"] != suite.fingerprint(candidate):
                raise ValueError(f"Historical candidate changed: {task}")
        previous[arm] = {t: r["passed"] for t, r in rows.items()}
        candidates["old/" + arm] = raw
    return previous, candidates


def example_plan(records, verdicts, old):
    """Choose one old shared miss rescued only by browsing, and one still missed."""
    selected = []
    for name, needs_gain in (("browse_only_gain", True), ("persistent_failure", False)):
        eligible = []
        for r in records:
            t, m = r["task_id"], r["model"]
            if (
                r["arm"] == "browse"
                and not old["direct"][t]
                and not old["self_check"][t]
                and not verdicts[m + "/fixed"][t]
                and verdicts[m + "/browse"][t] == needs_gain
            ):
                eligible.append(r)
        if not eligible:
            continue
        best = min(
            eligible,
            key=lambda r: (not bool(r["novel_cells"]), r["task_id"], r["model"]),
        )
        chosen = best["model"]
        selected.append(
            {
                "outcome": name,
                "task_id": best["task_id"],
                "model": chosen,
                "failed_arm": "fixed" if needs_gain else "browse",
                "browse_reads": [x["request"] for x in best["trace"]],
                "new_cells_returned": best["novel_cells"],
            }
        )
    return selected


def offline_verdicts(candidates, wheel_path, old_results, records=()):
    """Pin and install the original distribution, then re-execute every rejected new artifact."""
    original = load(OLD.parent / "wheel_verification.json")
    if digest(wheel_path) != original["wheel_sha256"]:
        raise ValueError("The wheel bytes differ from the original verified study")
    with tempfile.TemporaryDirectory(prefix="workbook-access-grade-") as temp:
        work = Path(temp)
        deny = network_barrier()
        env = {
            k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "PYTHONHOME"}
        }
        env.update(PIP_DISABLE_PIP_VERSION_CHECK="1", PIP_NO_INDEX="1")

        def execute(command, payload=None):
            return subprocess.run(
                [*deny, *map(str, command)],
                cwd=work,
                env=env,
                check=True,
                input=payload,
                text=True,
                stdout=subprocess.PIPE,
            ).stdout

        launcher = shutil.which("python3.11") or sys.executable
        execute([launcher, "-m", "venv", work / "venv"])
        py = work / "venv/bin/python"
        execute([py, "-m", "pip", "install", *OFFLINE_PIP, wheel_path.resolve()])
        grade_cmd = [
            py,
            "-I",
            ROOT / "scripts/verify_independent_recordings.py",
            "--partition",
            "calc-sql",
        ]

        def grade(items):
            checked = json.loads(execute(grade_cmd, json.dumps(items)))
            if (
                checked["release"] != original["release_sha256"]
                or set(checked["rows"]) != set(items)
                or any(
                    set(v) != set(items[k])
                    or any(type(x) is not bool for x in v.values())
                    for k, v in checked["rows"].items()
                )
            ):
                raise ValueError(
                    "Installed-wheel check omitted submissions or returned an unexpected release"
                )
            return checked["rows"]

        verdicts = grade(candidates)
        for arm, historical in old_results.items():
            if verdicts.pop("old/" + arm) != historical:
                raise ValueError(
                    f"Fresh offline regrade changed historical {arm} scores"
                )
        failed = {
            k: {t: candidates[k][t] for t, passed in v.items() if not passed}
            for k, v in verdicts.items()
        }
        rerun = grade(failed)
        if any(passed for group in rerun.values() for passed in group.values()):
            raise ValueError("Failed candidate changed verdict during replay")
        examples = example_plan(records, verdicts, old_results)
        if examples:
            examine = [
                {
                    "task_id": x["task_id"],
                    "candidate": candidates[x["model"] + "/" + x["failed_arm"]][
                        x["task_id"]
                    ],
                }
                for x in examples
            ]
            details = json.loads(
                execute(
                    [py, "-I", ROOT / "scripts/workbook_access_diagnostics.py"],
                    json.dumps(examine),
                )
            )
            for example, detail in zip(examples, details):
                example["difference"] = detail
                if detail["stage"] == "recalculated":
                    task = example["task_id"]
                    for arm in ARMS:
                        example[arm + "_formula_at_cell"] = (
                            candidates[example["model"] + "/" + arm][task]
                            .get("formulas", {})
                            .get(detail["cell"])
                        )
    return verdicts, {
        "examples": examples,
        "wheel_sha256": original["wheel_sha256"],
        "release_sha256": original["release_sha256"],
        "historical_score_sha256": digest(OLD / "score.json"),
        "historical_verdicts_reproduced": sum(map(len, old_results.values())),
        "new_verdicts": sum(map(len, verdicts.values())),
        "failed_submissions_replayed": sum(map(len, failed.values())),
        "failed_candidate_sha256": {
            k: {t: suite.fingerprint(c) for t, c in items.items()}
            for k, items in failed.items()
        },
        "network_barrier": deny,
    }


def pair(first, second):
    if set(first) != set(second):
        raise ValueError("Unpaired workbook results")
    outcomes = {"both_pass": [], "gained": [], "lost": [], "both_fail": []}
    names = {
        (True, True): "both_pass",
        (False, True): "gained",
        (True, False): "lost",
        (False, False): "both_fail",
    }
    for task in sorted(first):
        outcomes[names[first[task], second[task]]].append(task)
    return {name: {"count": len(ids), "tasks": ids} for name, ids in outcomes.items()}


def summarize(records, models, tasks, old, verdicts, omitted):
    reg_tasks = set(tasks)
    if len(models) != 2 or len(set(models)) != 2 or len(reg_tasks) != len(tasks):
        raise ValueError("Expected unique tasks and two distinct models")
    expected = {(t, m, a) for t in tasks for m in models for a in ARMS}
    indexed = {(r["task_id"], r["model"], r["arm"]): r for r in records}
    if len(records) != len(indexed) or set(indexed) != expected:
        raise ValueError(
            "Expected one sealed answer per registered model, access condition and task"
        )
    prior_failed = sorted(
        t for t in tasks if not old["direct"][t] and not old["self_check"][t]
    )
    batch_for = {t: indexed[t, models[0], "fixed"]["batch"] for t in tasks}
    if any(r["batch"] != batch_for[r["task_id"]] for r in records):
        raise ValueError("Paired batch membership changed")
    truncated_batches = {batch_for[t] for t in tasks if omitted[t]}
    complete_batches = set(batch_for.values()) - truncated_batches
    complete_batch_tasks = [t for t in tasks if batch_for[t] in complete_batches]
    usage = {}
    model_pairs = {}
    comparisons = {}
    rows = []
    for model in models:
        vf, vb = (verdicts[model + "/" + a] for a in ARMS)

        def paired_subset(subset):
            return pair({t: vf[t] for t in subset}, {t: vb[t] for t in subset})

        novel_ids = {t for t in tasks if indexed[t, model, "browse"]["novel_cells"]}
        subsets = {
            "all": tasks,
            "old_both_failed": prior_failed,
            "initially_truncated": [t for t in tasks if omitted[t]],
            "initially_complete": [t for t in tasks if not omitted[t]],
            "all_tasks_in_batch_initially_complete": complete_batch_tasks,
            "old_failures_with_truncated_input": [
                t for t in prior_failed if omitted[t]
            ],
            "old_failures_with_complete_input": [
                t for t in prior_failed if not omitted[t]
            ],
            "all_with_new_cells_returned": novel_ids,
            "old_failures_with_new_cells_returned": novel_ids.intersection(
                prior_failed
            ),
        }
        model_pairs[model] = {k: paired_subset(v) for k, v in subsets.items()}
        model_pairs[model].update(
            archived_direct_to_fixed=pair(old["direct"], vf),
            archived_self_check_to_fixed=pair(old["self_check"], vf),
            archived_direct_to_browse=pair(old["direct"], vb),
            archived_self_check_to_browse=pair(old["self_check"], vb),
        )
        for arm in ARMS:
            batches = {}
            calls = novel = tasks_novel = invalid = 0
            for task in tasks:
                row = indexed[task, model, arm]
                signature = (row["model_calls"], row["usage"])
                if batches.setdefault(row["batch"], signature) != signature:
                    raise ValueError("Batch usage differs between members")
                calls += row["calls"]
                n = len({tuple(address) for address in row["novel_cells"]})
                if arm == "fixed" and n:
                    raise ValueError("A fixed observation revealed a new cell")
                if n > omitted[task]:
                    raise ValueError(
                        "Returned cells exceed the original workbook coverage gap"
                    )
                novel += n
                tasks_novel += bool(n)
                invalid += sum(
                    event["result"].get("ok") is False for event in row["trace"]
                )
            tokens = Counter()
            for _, u in batches.values():
                tokens.update(u)
            usage[model + "/" + arm] = {
                "passes": sum(verdicts[model + "/" + arm].values()),
                "batches": len(batches),
                "model_calls": sum(c for c, _ in batches.values()),
                "read_requests": calls,
                "read_errors": invalid,
                "tasks_with_new_cells": tasks_novel,
                "new_task_cell_pairs": novel,
                "tokens": dict(tokens),
            }
        for task in sorted(tasks):
            trace = indexed[task, model, "browse"]
            fixed = indexed[task, model, "fixed"]
            rows.append(
                {
                    "task_id": task,
                    "model": model,
                    "old_direct": int(old["direct"][task]),
                    "old_self_check": int(old["self_check"][task]),
                    "old_both_failed": int(task in prior_failed),
                    "fixed": int(vf[task]),
                    "browse": int(vb[task]),
                    "outcome": {
                        (1, 1): "both_pass",
                        (0, 1): "gained",
                        (1, 0): "lost",
                        (0, 0): "both_fail",
                    }[vf[task], vb[task]],
                    "fixed_read_requests": fixed["calls"],
                    "browse_read_requests": trace["calls"],
                    "initially_omitted_nonempty_cells": omitted[task],
                    "any_workbook_in_batch_truncated": int(
                        batch_for[task] in truncated_batches
                    ),
                    "new_nonempty_cells": len(trace["novel_cells"]),
                    "browse_recording": f"../recordings/{model}/browse/{trace['batch']}.json",
                    "fixed_recording": f"../recordings/{model}/fixed/{fixed['batch']}.json",
                }
            )
    for arm in ARMS:
        comparisons[arm] = pair(
            verdicts[models[0] + "/" + arm], verdicts[models[1] + "/" + arm]
        )
    return {
        "task_count": len(tasks),
        "all_complete_batches": sorted(complete_batches),
        "untruncated_tasks_with_truncated_batch_peer": sorted(
            t for t in tasks if not omitted[t] and batch_for[t] in truncated_batches
        ),
        "models": models,
        "archived_passes": {arm: sum(v.values()) for arm, v in old.items()},
        "archived_both_failed": prior_failed,
        "tasks_with_initially_omitted_cells": sorted(t for t in tasks if omitted[t]),
        "old_failures_with_initially_omitted_cells": sorted(
            t for t in prior_failed if omitted[t]
        ),
        "by_model": model_pairs,
        "second_model_vs_first": comparisons,
        "old_shared_failures_across_browse_models": pair(
            {t: verdicts[models[0] + "/browse"][t] for t in prior_failed},
            {t: verdicts[models[1] + "/browse"][t] for t in prior_failed},
        ),
        "usage": usage,
    }, rows


def render(summary, replay):
    models = summary["models"]
    usage = summary["usage"]
    s = [
        "# 工作簿只读查表对照",
        "",
        f"两种模型分别完成同一批 {summary['task_count']} 道冻结工作簿题。每题在公开工作簿和隐藏变体上都得到预期目标值才通过。",
        f"旧记录直接作答通过 {summary['archived_passes']['direct']} 道，自查通过 {summary['archived_passes']['self_check']} 道。旧记录两种作答都失败的有 {len(summary['archived_both_failed'])} 道。",
        "",
        "| 模型 | 固定摘录通过 | 可查全表通过 | 查表独有通过 | 固定摘录独有通过 | 两组都失败 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    if summary.get("efficient_tier"):
        s[2:2] = [
            "两种专业档模型未能完成登记所要求的持续调用。研究在开分前按补充登记改用效率档 gpt-6.1-terra，与 gpt-6.2-sol 的原封存答卷配对。两组的任务、只读权限与预算一致。[补充登记](../registration.json)",
            "",
        ]
    elif "parent_registration_sha256" in summary:
        s[2:2] = [
            "原定的 gpt-6.2-astra 无法完成这批实验。研究在开分前按补充登记改用 gpt-6-astra，并保留了 gpt-6.2-sol 的原始提交。[补充登记](../registration.json)",
            "",
        ]
    for m in models:
        r = summary["by_model"][m]["all"]
        s.append(
            f"| {m} | {usage[m + '/fixed']['passes']} | {usage[m + '/browse']['passes']} | {r['gained']['count']} | {r['lost']['count']} | {r['both_fail']['count']} |"
        )
    s += [
        "",
        "## 以前两种作答都失败的题",
        "",
        "| 模型 | 两组均通过 | 仅查全表通过 | 仅固定摘录通过 | 两组仍失败 |",
        "|---|---:|---:|---:|---:|",
    ]
    for m in models:
        r = summary["by_model"][m]["old_both_failed"]
        s.append(
            f"| {m} | {r['both_pass']['count']} | {r['gained']['count']} | {r['lost']['count']} | {r['both_fail']['count']} |"
        )
    combined = summary["old_shared_failures_across_browse_models"]
    s += [
        "",
        f"可查全表时，旧共同错题中两模型都通过 {combined['both_pass']['count']} 道，只有 {models[0]} 通过 {combined['lost']['count']} 道，只有 {models[1]} 通过 {combined['gained']['count']} 道，两模型都仍失败 {combined['both_fail']['count']} 道。",
    ]
    for m in models:
        r = summary["by_model"][m]["old_both_failed"]
        for key, label in (("gained", "仅查全表通过"), ("both_fail", "两组仍失败")):
            ids = "、".join(t.removeprefix("sheet-") for t in r[key]["tasks"]) or "无"
            s += ["", f"{m} 在这批旧错题中，{label}的工作簿编号为 {ids}。"]
    s += [
        "",
        f"初始摘录在 {len(summary['tasks_with_initially_omitted_cells'])} 道题上省略了非空单元格，其中 {len(summary['old_failures_with_initially_omitted_cells'])} 道来自旧的共同失败集合。未被截掉非空单元格的工作表上，重新查找、分轮思考和独立作答仍可能产生不同结果。",
        "",
        "| 模型 | 初始摘录或实际读数 | 两组均通过 | 仅查全表通过 | 仅固定摘录通过 | 两组均失败 |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for model in models:
        for subset, label in (
            ("initially_complete", "摘录包含所有非空单元格"),
            ("initially_truncated", "摘录缺少非空单元格"),
            ("all_tasks_in_batch_initially_complete", "同批所有题的初始摘录都完整"),
            ("old_failures_with_new_cells_returned", "旧共同错题中实际查到新增单元格"),
        ):
            cut = summary["by_model"][model][subset]
            s.append(
                f"| {model} | {label} | {cut['both_pass']['count']} | {cut['gained']['count']} | {cut['lost']['count']} | {cut['both_fail']['count']} |"
            )
    s += [
        "",
        f"有 {len(summary['untruncated_tasks_with_truncated_batch_peer'])} 道自身摘录完整的题与缺少非空单元格的工作簿同批作答，模型能看到同批其他题的查表结果。表中另列 {len(summary['all_complete_batches'])} 个整批摘录完整的批次，供观察两次独立作答的差异。工具也会返回匹配数和截断状态，即使未返回新坐标，回答仍可能获得这些范围信息。",
        "",
        "## 实际预算消耗",
        "",
        "| 模型 | 条件 | 模型调用 | 查表请求 | 有新增单元格的题 | 新增非空单元格 | 输入 tokens | 输出 tokens |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for m in models:
        for a, name in (("fixed", "固定摘录"), ("browse", "可查全表")):
            u = usage[m + "/" + a]
            s.append(
                f"| {m} | {name} | {u['model_calls']} | {u['read_requests']} | {u['tasks_with_new_cells']} | {u['new_task_cell_pairs']} | {u['tokens'].get('input_tokens', 0):,} | {u['tokens'].get('output_tokens', 0):,} |"
            )
    s += [
        "",
        "同一批最多四题。每组有两轮模型选取范围或搜索词，再提交一次公式。固定组只能从初始摘录中检索，可查全表组还能检索原始公开工作簿。新增单元格按题、表页、坐标去重，只计超出初始摘录而真的返回的非空单元格。各批次的 token 只计一次。一次独立作答的变化也可能来自模型波动，单题上查到新单元格只能说明模型看到了这项信息。",
        "",
        f"先封存新答卷，再用原 wheel 在隔网进程内执行公式。重新评分复现了旧档 {replay['historical_verdicts_reproduced']} 个判定。本轮 {replay['new_verdicts']} 个判定中的 {replay['failed_submissions_replayed']} 次失败全部逐个复算一致。",
        "",
        "[逐题配对及查询记录路径](per_workbook_pairs.csv) · [所有分歧、修对和持续失败的题号](paired_summary.json) · [失败回放](failure_replay.json)",
    ]
    if replay["examples"]:
        s += ["", "## 实际执行出的差异", ""]
        for x in replay["examples"]:
            d = x["difference"]
            tag = "仅查全表通过" if x["outcome"] == "browse_only_gain" else "两组仍失败"
            if d["stage"] == "recalculated":
                loc = "公开输入" if d["input"] == "public" else "隐藏变体"

                def show(v):
                    if v is None:
                        return "空白"
                    value = "`" + str(v[1]).replace("`", "'")[:100] + "`"
                    kind = {
                        "n": "数值",
                        "s": "文本",
                        "b": "逻辑值",
                        "e": "表格错误",
                    }.get(v[0], v[0])
                    return f"{kind} {value}"

                arm = "固定摘录" if x["failed_arm"] == "fixed" else "可查全表"
                detail = f"{arm}提交在{loc}重算后，{d['sheet']}!{d['cell']} 的预期是 {show(d['expected'])}，实际是 {show(d['actual'])}。"
            else:
                detail = "该提交的公式或编辑位置未通过输入检查。"
            s.append(
                f"- {x['model']} 的 {x['task_id']} {tag}。{detail}可查全表时读取了 {len(x['new_cells_returned'])} 个初始摘录以外的非空单元格。"
            )
        s += ["", "[案例查询、两种公式和评分差异](failure_replay.json)"]
    return "\n".join(s) + "\n"


def save_text(path, text):
    if path.exists():
        if path.read_text(encoding="utf-8") != text:
            raise ValueError(f"Existing study output differs: {path}")
        return
    with tempfile.NamedTemporaryFile(
        dir=path.parent, mode="w", encoding="utf-8", delete=False
    ) as stream:
        stream.write(text)
    os.replace(stream.name, path)


def score(root, wheel_path):
    reg = load(root / "registration.json")
    if reg.get("efficient_tier"):
        from run_workbook_access_efficient import verified_records
    elif "parent_registration_sha256" in reg:
        from run_workbook_access_amended import verified_records
    else:
        from run_workbook_access import verified_records

    records = verified_records(root)
    tasks, models = reg["tasks"], reg["models"]
    old, candidates = read_archive(tasks)
    for rec in records:
        group = rec["model"] + "/" + rec["arm"]
        table = candidates.setdefault(group, {})
        if rec["task_id"] in table:
            raise ValueError("Duplicate recorded answer")
        table[rec["task_id"]] = expanded(rec["submission"])
    values, replay = offline_verdicts(candidates, wheel_path, old, records)
    replay["prediction_lock_sha256"] = digest(root / "prediction_lock.json")
    output = root / "results"
    output.mkdir(parents=True, exist_ok=True)
    omitted = {}
    for batch in sorted((OLD / "inputs").glob("spreadsheets-*.json")):
        for item in load(batch):
            omitted[item["task_id"]] = sum(
                sheet["nonempty_count"] - len(sheet["cells"])
                for sheet in item["observation"].values()
            )
    summary, rows = summarize(records, models, tasks, old, values, omitted)
    summary["prediction_lock_sha256"] = replay["prediction_lock_sha256"]
    if reg.get("efficient_tier"):
        summary["efficient_tier"] = reg["efficient_tier"]
    if "parent_registration_sha256" in reg:
        summary["parent_registration_sha256"] = reg["parent_registration_sha256"]
    seal(output / "failure_replay.json", replay)
    seal(output / "paired_summary.json", summary)
    csv_text = io.StringIO(newline="")
    w = csv.DictWriter(csv_text, fieldnames=rows[0].keys(), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    save_text(output / "per_workbook_pairs.csv", csv_text.getvalue())
    save_text(output / "summary_zh.md", render(summary, replay))
    print(
        json.dumps(
            {
                m: {a: summary["usage"][m + "/" + a]["passes"] for a in ARMS}
                for m in models
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument(
        "--wheel",
        type=Path,
        default=WHEELS / "sandboxed_agent_eval_harness-0.1.0-py3-none-any.whl",
    )
    args = parser.parse_args()
    score(args.root, args.wheel)

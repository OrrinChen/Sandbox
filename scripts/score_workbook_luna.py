"""Grade the locked Luna addition and compare it with the original workbook runs."""

import argparse
from collections import Counter
import csv
import io
import json
import os
from pathlib import Path

import run_workbook_access_luna as luna
import score_workbook_access as prior


def cross_model_outcomes(rows, parents, model):
    by_model = {
        m: {r["task_id"]: r for r in rows if r["model"] == m} for m in [*parents, model]
    }
    tasks = set(by_model[model])
    if len(rows) != len(tasks) * len(by_model) or any(
        set(v) != tasks for v in by_model.values()
    ):
        raise ValueError("All three models must have one pair for every workbook")
    old_misses = {t for t in tasks if by_model[model][t]["old_both_failed"]}
    parent_misses = {
        t for t in old_misses if all(not by_model[p][t]["browse"] for p in parents)
    }
    browse = {t: bool(by_model[model][t]["browse"]) for t in tasks}
    fixed = {t: bool(by_model[model][t]["fixed"]) for t in tasks}
    subsets = {
        "archived_common_misses": old_misses,
        "old_misses_unsolved_by_prior_browse_models": parent_misses,
    }
    return {
        "luna_fixed_to_browse": {
            k: prior.pair({t: fixed[t] for t in subset}, {t: browse[t] for t in subset})
            for k, subset in subsets.items()
        },
        "remaining_after_all_three_browse": sorted(
            t for t in parent_misses if not browse[t]
        ),
        "previously_unsolved_now_passed_by_luna_browse": sorted(
            t for t in parent_misses if browse[t]
        ),
        "old_misses_solved_by_luna_browse": sorted(t for t in old_misses if browse[t]),
        "all_three_failed_browse_across_full_roster": sorted(
            t for t in tasks if all(not p[t]["browse"] for p in by_model.values())
        ),
    }


def archived_verdicts(rows, models, tasks):
    values = {m + "/" + a: {} for m in models for a in prior.ARMS}
    for r in rows:
        for a in prior.ARMS:
            table = values[r["model"] + "/" + a]
            task = r["task_id"]
            if task in table or r[a] not in ("0", "1"):
                raise ValueError("Duplicate or invalid historical workbook verdict")
            table[task] = r[a] == "1"
    if any(set(v) != set(tasks) for v in values.values()):
        raise ValueError("Historical workbook verdicts do not match the locked roster")
    return values


def collection_summary(slots, groups, luna_rows):
    stages = ("inspect-1", "inspect-2", "submit")
    expected = {(a, b, t) for a in prior.ARMS for b in groups for t in stages}
    slots_by_key = {(e["arm"], e["batch"], e["stage"]): e for e in slots}
    if set(slots_by_key) != expected or len(slots) != len(expected):
        raise ValueError("Fresh campaign must account for every registered model turn")
    usage = {}
    task_batch = {task: b for b, tasks in groups.items() for task in tasks}
    clean = set(groups)
    for arm in prior.ARMS:
        arm_slots = [e for e in slots if e["arm"] == arm]
        statuses = Counter(e["status"] for e in arm_slots)
        clean_arm = {
            b
            for b in groups
            if all(slots_by_key[arm, b, t]["status"] == "accepted" for t in stages)
        }
        clean &= clean_arm
        usage[arm] = {
            "slots": len(arm_slots),
            "statuses": dict(sorted(statuses.items())),
            "accepted_turns_with_progress_messages": sum(
                e["status"] == "accepted" and (e["message_count"] or 0) > 1
                for e in arm_slots
            ),
            "slots_with_unknown_usage": sum(e["usage"] is None for e in arm_slots),
            "fully_accepted_batches": sorted(clean_arm),
        }
    rows = [r for r in luna_rows if task_batch[r["task_id"]] in clean]
    return {
        "by_arm": usage,
        "all_turns_accepted_in_both_arms": prior.pair(
            {r["task_id"]: bool(r["fixed"]) for r in rows},
            {r["task_id"]: bool(r["browse"]) for r in rows},
        ),
    }


def sensitivity(rows, groups, accounting, records, root):
    arms = accounting["by_arm"]
    clean_batches = set(arms["fixed"]["fully_accepted_batches"]) & set(
        arms["browse"]["fully_accepted_batches"]
    )
    clean = {t for b in clean_batches for t in groups[b]}
    models = list(dict.fromkeys(r["model"] for r in rows))
    accepted_subset = [r for r in rows if r["task_id"] in clean]
    split = cross_model_outcomes(
        accepted_subset, [m for m in models if m != luna.MODEL], luna.MODEL
    )
    incomplete = {}
    for r in records:
        if r["submission_status"] != "present":
            incomplete.setdefault(r["arm"], set()).add(r["task_id"])
    gained = [r for r in rows if r["model"] == luna.MODEL and r["outcome"] == "gained"]
    previous_fixed_missing = [
        r for r in gained if r["task_id"] in incomplete.get("fixed", set())
    ]
    rejected = []
    for slot in prior.load(root / "collection_accounting.json")["slots"]:
        if slot["status"] != "accepted":
            path = (
                root
                / "turns"
                / luna.MODEL
                / slot["arm"]
                / slot["batch"]
                / (slot["stage"] + ".json")
            )
            events = prior.load(path)["cli_events"]
            rejected.append(
                {
                    "arm": slot["arm"],
                    "batch": slot["batch"],
                    "stage": slot["stage"],
                    "status": slot["status"],
                    "task_ids": groups[slot["batch"]],
                    "out_of_protocol_item_types": sorted(
                        {
                            e["item"]
                            for a in events
                            for e in a["external_tool_events"]
                            if e.get("item")
                        }
                    ),
                }
            )
    return {
        "matched_complete_tasks": sorted(clean),
        "same_task_passes": {
            m: {
                a: sum(r[a] for r in accepted_subset if r["model"] == m)
                for a in prior.ARMS
            }
            for m in models
        },
        "old_unsolved_among_complete_tasks": split["luna_fixed_to_browse"][
            "old_misses_unsolved_by_prior_browse_models"
        ],
        "new_rescues_on_complete_tasks": split[
            "previously_unsolved_now_passed_by_luna_browse"
        ],
        "still_unsolved_on_complete_tasks": split["remaining_after_all_three_browse"],
        "nonaccepted_slots": rejected,
        "missing_task_answer": {
            a: sorted(incomplete.get(a, set())) for a in prior.ARMS
        },
        "browse_gains_with_missing_fixed_answer": [
            r["task_id"] for r in previous_fixed_missing
        ],
        "browse_gains_with_missing_fixed_answer_and_new_cells": [
            r["task_id"] for r in previous_fixed_missing if r["new_nonempty_cells"]
        ],
    }


def score(root, wheel):
    from run_workbook_access_luna_complete import verified_records

    records = verified_records(root)
    accounting = prior.load(root / "collection_accounting.json")
    reg = prior.load(root / "registration.json")
    parent = luna.PARENT
    parent_records = luna.paired.verified_records(parent)
    parent_summary = prior.load(parent / "results/paired_summary.json")
    if parent_summary["prediction_lock_sha256"] != reg["parent_prediction_lock_sha256"]:
        raise ValueError("Prior report refers to a different prediction lock")
    parents = parent_summary["models"]
    tasks = reg["tasks"]
    with (parent / "results/per_workbook_pairs.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        prior_verdicts = archived_verdicts(csv.DictReader(stream), parents, tasks)
    old, candidates = prior.read_archive(tasks)
    for record in [*parent_records, *records]:
        key = record["model"] + "/" + record["arm"]
        group = key if record["model"] == luna.MODEL else "old/" + key
        table = candidates.setdefault(group, {})
        if record["task_id"] in table:
            raise ValueError("Duplicate workbook submission")
        table[record["task_id"]] = prior.expanded(record["submission"])

    values, replay = prior.offline_verdicts(
        candidates, wheel, {**old, **prior_verdicts}, records
    )
    replay["prediction_lock_sha256"] = prior.digest(root / "prediction_lock.json")
    replay["parent_prediction_lock_sha256"] = reg["parent_prediction_lock_sha256"]
    values.update(prior_verdicts)
    omitted = {
        item["task_id"]: sum(
            s["nonempty_count"] - len(s["cells"]) for s in item["observation"].values()
        )
        for group in reg["groups"]
        for item in prior.load(root / "inputs" / (group + ".json"))
    }
    output = root / "results"
    rows, comparisons = [], {}
    for index, other in enumerate(parents):
        subset = [r for r in parent_records if r["model"] == other] + records
        report, pair_rows = prior.summarize(
            subset, [other, luna.MODEL], tasks, old, values, omitted
        )
        if report["by_model"][other] != parent_summary["by_model"][other] or any(
            report["usage"][other + "/" + a] != parent_summary["usage"][other + "/" + a]
            for a in prior.ARMS
        ):
            raise ValueError(
                f"Reproduction differs from the previous report for {other}"
            )
        comparisons[other] = report["second_model_vs_first"]
        for r in pair_rows:
            if r["model"] == other:
                for a in prior.ARMS:
                    key = a + "_recording"
                    r[key] = os.path.relpath(parent / "results" / r[key], output)
            elif index:
                continue
            rows.append(r)
    rows.sort(key=lambda r: (r["task_id"], [*parents, luna.MODEL].index(r["model"])))
    summary = {
        "models": [*parents, luna.MODEL],
        "task_count": len(tasks),
        "prediction_lock_sha256": replay["prediction_lock_sha256"],
        "parent_prediction_lock_sha256": replay["parent_prediction_lock_sha256"],
        "collection_accounting_sha256": prior.digest(
            root / "collection_accounting.json"
        ),
        "fresh_collection": collection_summary(
            accounting["slots"],
            reg["groups"],
            [r for r in rows if r["model"] == luna.MODEL],
        ),
        "prior_result_files_sha256": {
            p.name: prior.digest(p)
            for p in sorted((parent / "results").iterdir())
            if p.is_file()
        },
        "archived_passes": report["archived_passes"],
        "by_model": {
            **parent_summary["by_model"],
            luna.MODEL: report["by_model"][luna.MODEL],
        },
        "usage": {**parent_summary["usage"], **report["usage"]},
        "luna_answer_format": {
            a: {
                "submission_status": dict(
                    Counter(r["submission_status"] for r in records if r["arm"] == a)
                ),
                "empty_task_answers": sum(
                    r["submission"] == "" for r in records if r["arm"] == a
                ),
                "inspection_plan_status": dict(
                    Counter(
                        status
                        for r in records
                        if r["arm"] == a
                        for status in r["plan_status"]
                    )
                ),
            }
            for a in prior.ARMS
        },
        "luna_vs_each_prior_model": comparisons,
        **cross_model_outcomes(rows, parents, luna.MODEL),
    }
    summary["sensitivity"] = sensitivity(
        rows, reg["groups"], summary["fresh_collection"], records, root
    )
    output.mkdir(parents=True, exist_ok=True)
    prior.seal(output / "failure_replay.json", replay)
    prior.seal(output / "paired_summary.json", summary)
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    prior.save_text(output / "per_workbook_pairs.csv", buf.getvalue())
    prior.save_text(output / "summary_zh.md", render(summary, replay))
    print(
        json.dumps(
            {
                m: {a: summary["usage"][m + "/" + a]["passes"] for a in prior.ARMS}
                for m in summary["models"]
            }
        )
    )


def ids(items):
    return "、".join(t.removeprefix("sheet-") for t in items) or "无"


def render(s, replay):
    model = luna.MODEL
    u = s["usage"]
    rows = [
        "# Luna 工作簿对照",
        "",
        f"三个模型分别作答相同的 {s['task_count']} 道冻结题。Luna 使用相同的初始摘录、25 个四题批次、两轮只读工具和每题四次查询上限。每个条件各独立作答一次。提交的公式在公开和隐藏两种输入上都算对才通过。",
        "",
        "| 模型 | 固定摘录通过 | 全表通过 | 仅全表通过 | 仅固定摘录通过 | 全表答对原共同错题 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for m in s["models"]:
        p = s["by_model"][m]["all"]
        old = s["by_model"][m]["old_both_failed"]
        rows.append(
            f"| {m} | {u[m + '/fixed']['passes']} | {u[m + '/browse']['passes']} | {p['gained']['count']} | {p['lost']['count']} | {old['both_pass']['count'] + old['gained']['count']} |"
        )
    rows.extend(
        [
            "",
            "在相同访问条件下按题号比较，Luna 与前两种模型的分歧如下。",
            "",
            "| 对照模型 | 条件 | 仅 Luna 通过 | 仅对照模型通过 | 两者通过 | 两者失败 |",
            "|---|---|---:|---:|---:|---:|",
        ]
    )
    for other, views in s["luna_vs_each_prior_model"].items():
        for arm, label in (("fixed", "固定摘录"), ("browse", "全表")):
            result = views[arm]
            rows.append(
                f"| {other} | {label} | {result['gained']['count']} | {result['lost']['count']} | {result['both_pass']['count']} | {result['both_fail']['count']} |"
            )
    p = s["by_model"][model]
    old = p["old_both_failed"]
    remain = s["remaining_after_all_three_browse"]
    rescued = s["previously_unsolved_now_passed_by_luna_browse"]
    newer = p["all_with_new_cells_returned"]["gained"]
    previous = s["luna_fixed_to_browse"]["old_misses_unsolved_by_prior_browse_models"]
    old_n = sum(v["count"] for v in old.values())
    rows.extend(
        [
            "",
            "## 旧错题逐题变化",
            "",
            f"历史直接作答通过 {s['archived_passes']['direct']} 道，自查通过 {s['archived_passes']['self_check']} 道。两次均失败的 {old_n} 道中，Luna 查全表时答对 {len(s['old_misses_solved_by_luna_browse'])} 道，编号为 {ids(s['old_misses_solved_by_luna_browse'])}。其中固定摘录也答对 {old['both_pass']['count']} 道，仅查全表答对 {old['gained']['count']} 道。",
            "",
            f"Sol 和 Terra 查全表后仍未解出的 {len(remain) + len(rescued)} 道旧错题中，Luna 查全表答对 {len(rescued)} 道（{ids(rescued)}），其中固定摘录也答对 {previous['both_pass']['count']} 道。三者查全表后仍失败的 {len(remain)} 道为 {ids(remain)}。",
            "",
            "## Luna 的查表记录",
            "",
            f"Luna 在固定摘录和全表条件下分别发出 {u[model + '/fixed']['read_requests']}、{u[model + '/browse']['read_requests']} 次查询，各用 {u[model + '/browse']['model_calls']} 次模型调用。全表条件在 {u[model + '/browse']['tasks_with_new_cells']} 道题中返回了摘录外的非空单元格，按题和坐标去重共 {u[model + '/browse']['new_task_cell_pairs']} 个。",
            "",
            f"Luna 仅查全表通过的 {p['all']['gained']['count']} 道中，有 {newer['count']} 道实际返回了新增非空单元格（{ids(newer['tasks'])}）。旧共同错题中的相应题数为 {p['old_failures_with_new_cells_returned']['gained']['count']}。整批摘录完整的题中，Luna 仍有 {p['all_tasks_in_batch_initially_complete']['gained']['count']} 道仅全表通过、{p['all_tasks_in_batch_initially_complete']['lost']['count']} 道仅固定摘录通过。每个条件只跑一次，单题变化也可能来自独立重答、同批其他题的查询或工具返回的范围信息。",
            "",
            "## 逐项回放",
            "",
            f"原 wheel 在禁止联网的进程中重现 {replay['historical_verdicts_reproduced']} 个既有判定，并评定 Luna 的 {replay['new_verdicts']} 个判定。Luna 的 {replay['failed_submissions_replayed']} 次失败全部复算一致。",
        ]
    )
    rows += [
        "",
        "首次 Luna 采集在一轮有多条消息时中断，整次尝试在评分前排除。表中 Luna 成绩来自重新登记的完整独立批次。新采集器保存每轮所有消息，以 CLI 返回的最终消息解释工具请求或公式。[重新登记](../registration.json)",
        "",
        "| 条件 | 登记调用 | CLI 最终消息被接收 | 带前置消息的接收轮次 | 协议拒绝 | 其他未取得回复的轮次 | 用量缺失的轮次 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for arm, label in (("fixed", "固定摘录"), ("browse", "全表")):
        q = s["fresh_collection"]["by_arm"][arm]
        statuses = q["statuses"]
        good = statuses.get("accepted", 0)
        rejects = statuses.get("protocol_rejected", 0)
        rows.append(
            f"| {label} | {q['slots']} | {good} | {q['accepted_turns_with_progress_messages']} | {rejects} | {q['slots'] - good - rejects} | {q['slots_with_unknown_usage']} |"
        )
    clean = s["fresh_collection"]["all_turns_accepted_in_both_arms"]
    rows.extend(
        [
            "",
            f"两种访问条件下所有轮次均通过采集器检查的题共 {sum(v['count'] for v in clean.values())} 道。该子集的固定摘录通过 {clean['both_pass']['count'] + clean['lost']['count']} 道，全表通过 {clean['both_pass']['count'] + clean['gained']['count']} 道。[逐轮采集记录](../collection_accounting.json)",
        ]
    )
    sensitivity_result = s["sensitivity"]
    missing = sensitivity_result["missing_task_answer"]
    gains = sensitivity_result["browse_gains_with_missing_fixed_answer"]
    extra = sensitivity_result["browse_gains_with_missing_fixed_answer_and_new_cells"]
    rows.extend(
        [
            "",
            f"采集器只检查每轮最终消息。分到每题后，固定摘录有 {len(missing['fixed'])} 题缺少可解析的提交，全表有 {len(missing['browse'])} 题。Luna 仅全表通过的题中，有 {len(gains)} 道对应固定组缺失答案（{ids(gains)}），其中 {len(extra)} 道读到了新增非空单元格（{ids(extra)}）。所有缺失答案按原规则计分。",
            "",
            f"下表按同一组 {len(sensitivity_result['matched_complete_tasks'])} 道题比较三个模型，只保留 Luna 两种条件下所有轮次均通过采集器检查的批次。",
            "",
            "| 模型 | 固定摘录通过 | 全表通过 |",
            "|---|---:|---:|",
        ]
    )
    for m, counts in sensitivity_result["same_task_passes"].items():
        rows.append(f"| {m} | {counts['fixed']} | {counts['browse']} |")
    full_21_n = len(rescued) + len(remain)
    sensitive_21 = sensitivity_result["old_unsolved_among_complete_tasks"]
    sensitive_n = sum(v["count"] for v in sensitive_21.values())
    clean_rescued = sensitivity_result["new_rescues_on_complete_tasks"]
    rows.extend(
        [
            "",
            f"Sol 与 Terra 查全表仍失败的 {full_21_n} 道旧错题中，{sensitive_n} 道属于完整批次，Luna 查全表通过 {len(clean_rescued)} 道（{ids(clean_rescued)}）。被排除批次中，Luna 在上述旧错题上通过 {len(rescued) - len(clean_rescued)} 道。",
        ]
    )
    for rejected in sensitivity_result["nonaccepted_slots"]:
        items = "、".join(rejected["out_of_protocol_item_types"]) or "未记录"
        rows.extend(
            [
                "",
                f"- {rejected['batch']} 的 {rejected['arm']} / {rejected['stage']} 状态为 {rejected['status']}，超出工具协议的事件类型为 `{items}`。主表保留该批次的四道题（{ids(rejected['task_ids'])}）。",
            ]
        )
    for x in replay["examples"]:
        outcome = "仅全表通过" if x["outcome"] == "browse_only_gain" else "两组仍然失败"
        location = "固定摘录" if x["failed_arm"] == "fixed" else "全表"
        d = x["difference"]
        detail = "公式或编辑位置未通过输入检查"
        if d["stage"] == "recalculated":
            observed = "公开输入" if d["input"] == "public" else "隐藏变体"

            def value(cell):
                return repr(cell[1]) if cell else "空白"

            detail = f"{observed}上 {d['sheet']}!{d['cell']} 预期为 {value(d['expected'])}，实际为 {value(d['actual'])}"
        rows.extend(
            [
                "",
                f"- {x['task_id']} {outcome}。评分器重算{location}提交时，{detail}。全表组查到了 {len(x['new_cells_returned'])} 个摘录外的非空单元格。",
            ]
        )
    rows.extend(
        [
            "",
            "[逐题配对及原始工具记录](per_workbook_pairs.csv) · [全部配对题号](paired_summary.json) · [失败回放](failure_replay.json) · [Luna 登记](../registration.json)",
        ]
    )
    return "\n".join(rows) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=luna.DEFAULT_ROOT.with_name("luna_complete")
    )
    parser.add_argument(
        "--wheel",
        type=Path,
        default=prior.WHEELS / "sandboxed_agent_eval_harness-0.1.0-py3-none-any.whl",
    )
    args = parser.parse_args()
    score(args.root, args.wheel)

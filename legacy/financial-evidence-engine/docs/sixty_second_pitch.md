# 60-Second Pitch

## English

I built this because ordinary RAG can retrieve plausible but unsafe evidence in financial due diligence.
The system verifies claims instead of only answering questions.
It decomposes claims, retrieves evidence, validates fiscal period, entity, metric, and citation support, reconciles numbers, detects unsupported or contradictory claims, and generates auditable memos.
I benchmarked BM25, dense-proxy, hybrid, graph, and validator-augmented retrieval on local due-diligence and adversarial tasks, then packaged the results into a PDF report, CLI, demo UI, and reproducible traces.

## 中文

这个项目的出发点是：普通 RAG 在金融尽调里最大的问题不是完全找不到文本，而是会找到看起来相关、但不能真正支持 claim 的证据。
所以我把问题从问答改成 claim verification。
系统会拆 claim、检索证据、验证 fiscal period、entity、metric 和 citation support，做数字 reconciliation，识别 unsupported 或 contradictory claim，并生成可审计 memo。
我还用 BM25、dense-proxy、hybrid、graph 和 validator-augmented retrieval 做了本地 due-diligence / adversarial evaluation，并把结果包装成 PDF report、CLI、demo UI 和 reproducible traces。

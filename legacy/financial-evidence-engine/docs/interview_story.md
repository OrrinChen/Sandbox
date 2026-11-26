# Interview Story

## 1. Starting Failure Mode

ordinary RAG gives plausible but unsafe financial answers. It can retrieve the wrong fiscal period, cite a nearby but irrelevant section, confuse millions and billions, or treat management narrative as filing-backed fact.

## 2. System Built

I built a claim-level evidence engine for financial due diligence. The system decomposes a financial claim, retrieves evidence, links it through an evidence graph, applies fiscal-period and numeric validators, and emits an auditable memo.

## 3. Evaluation

I benchmarked BM25, dense proxy, hybrid retrieval, graph retrieval, and a validator-augmented full engine on 60+ due-diligence tasks. I also added red-team tasks for wrong periods, wrong company aliases, unit scale errors, unsupported claims, deck-only claims, and transcript-only claims.

## 4. Concrete Failure Cases

The strongest demo cases are:

- fiscal-period confusion
- numeric/unit mismatch
- unsupported narrative claim
- investor-deck chart reconciliation

## 5. Design Principle

The system does not treat LLM output as truth. Validators remain the authority: entity, metric, fiscal period, unit scale, citation support, contradiction, and unsupported-claim checks gate every final verdict.

## 6. Auditability

Every verdict links back to evidence, validator results, trace manifests, and a memo section. This is the difference between a finance chatbot and a due-diligence evidence system.

# Fiscal-Period Confusion

- Case ID: `fiscal_period_confusion`
- Task ID: `phase6:aapl:single_company_trend`
- Failure mode: `period_confusion`
- Expected verdict: `support`
- Full engine verdict: `support`

## Claim

Apple's FY2024 revenue grew versus FY2023.

## Gold Evidence

| Evidence | Source | Company | Period | Metric | Role |
| --- | --- | --- | --- | --- | --- |
| `phase6:aapl:single_company_trend:ev1` | sec_xbrl_companyfacts/xbrl | AAPL | FY2024 | revenue | current revenue fact |
| `phase6:aapl:single_company_trend:ev2` | sec_xbrl_companyfacts/xbrl | AAPL | FY2023 | revenue | prior revenue fact |
| `phase6:aapl:single_company_trend:ev3` | sec_filing/text | AAPL | FY2024 | revenue | MD&A revenue discussion |

## Retrieved Evidence by Method

### bm25_real

Predicted verdict: `support`

| Evidence | Source | Company | Period | Metric |
| --- | --- | --- | --- | --- |
| `phase6:aapl:single_company_trend:ev2` | sec_xbrl_companyfacts/xbrl | AAPL | FY2023 | revenue |
| `phase6:aapl:single_company_trend:ev3` | sec_filing/text | AAPL | FY2024 | revenue |
| `phase6:aapl:single_company_trend:ev1` | sec_xbrl_companyfacts/xbrl | AAPL | FY2024 | revenue |
| `phase6:aapl:single_company_trend:dist1` | sec_xbrl_companyfacts/xbrl | AAPL | Q4 FY2024 | revenue |
| `phase6:aapl:single_company_trend:dist2` | sec_xbrl_companyfacts/xbrl | MSFT | FY2024 | revenue |

### dense_real

Predicted verdict: `support`

| Evidence | Source | Company | Period | Metric |
| --- | --- | --- | --- | --- |
| `phase6:aapl:single_company_trend:ev2` | sec_xbrl_companyfacts/xbrl | AAPL | FY2023 | revenue |
| `phase6:aapl:single_company_trend:ev1` | sec_xbrl_companyfacts/xbrl | AAPL | FY2024 | revenue |
| `phase6:aapl:single_company_trend:ev3` | sec_filing/text | AAPL | FY2024 | revenue |
| `phase6:aapl:single_company_trend:dist1` | sec_xbrl_companyfacts/xbrl | AAPL | Q4 FY2024 | revenue |
| `phase6:wmt:single_company_trend:ev2` | sec_xbrl_companyfacts/xbrl | WMT | FY2023 | revenue |

### hybrid_real

Predicted verdict: `support`

| Evidence | Source | Company | Period | Metric |
| --- | --- | --- | --- | --- |
| `phase6:aapl:single_company_trend:ev2` | sec_xbrl_companyfacts/xbrl | AAPL | FY2023 | revenue |
| `phase6:aapl:single_company_trend:ev1` | sec_xbrl_companyfacts/xbrl | AAPL | FY2024 | revenue |
| `phase6:aapl:single_company_trend:ev3` | sec_filing/text | AAPL | FY2024 | revenue |
| `phase6:aapl:single_company_trend:dist1` | sec_xbrl_companyfacts/xbrl | AAPL | Q4 FY2024 | revenue |
| `phase6:wmt:single_company_trend:ev2` | sec_xbrl_companyfacts/xbrl | WMT | FY2023 | revenue |

### graph_real

Predicted verdict: `support`

| Evidence | Source | Company | Period | Metric |
| --- | --- | --- | --- | --- |
| `phase6:aapl:single_company_trend:ev2` | sec_xbrl_companyfacts/xbrl | AAPL | FY2023 | revenue |
| `phase6:aapl:single_company_trend:ev1` | sec_xbrl_companyfacts/xbrl | AAPL | FY2024 | revenue |
| `phase6:aapl:single_company_trend:ev3` | sec_filing/text | AAPL | FY2024 | revenue |
| `phase6:msft:single_company_trend:dist2` | sec_xbrl_companyfacts/xbrl | AAPL | FY2024 | revenue |
| `phase6:aapl:guidance_vs_actuals:ev3` | sec_xbrl_companyfacts/xbrl | AAPL | FY2024 | revenue |

### full_engine_real

Predicted verdict: `support`

| Evidence | Source | Company | Period | Metric |
| --- | --- | --- | --- | --- |
| `phase6:aapl:single_company_trend:ev2` | sec_xbrl_companyfacts/xbrl | AAPL | FY2023 | revenue |
| `phase6:aapl:single_company_trend:ev1` | sec_xbrl_companyfacts/xbrl | AAPL | FY2024 | revenue |
| `phase6:aapl:single_company_trend:ev3` | sec_filing/text | AAPL | FY2024 | revenue |
| `phase6:msft:single_company_trend:dist2` | sec_xbrl_companyfacts/xbrl | AAPL | FY2024 | revenue |
| `phase6:aapl:guidance_vs_actuals:ev3` | sec_xbrl_companyfacts/xbrl | AAPL | FY2024 | revenue |

## Failure Reasons by Method

| Method | Failure reasons |
| --- | --- |
| bm25_real | period_confusion: Retrieved evidence uses a non-target fiscal period.; entity_mismatch: Retrieved evidence belongs to the wrong company.; numeric_validation_gap: Numeric validation did not pass for this task. |
| dense_real | period_confusion: Retrieved evidence uses a non-target fiscal period.; entity_mismatch: Retrieved evidence belongs to the wrong company.; numeric_validation_gap: Numeric validation did not pass for this task. |
| hybrid_real | period_confusion: Retrieved evidence uses a non-target fiscal period.; entity_mismatch: Retrieved evidence belongs to the wrong company. |
| graph_real | No failure detected for this method on this case. |
| full_engine_real | No failure detected for this method on this case. |

## Validator Checks Triggered

| Method | Validator | Status | Detail |
| --- | --- | --- | --- |
| bm25_real | numeric_reconciliation | fail | phase6:aapl:single_company_trend:num1=fail |
| bm25_real | fiscal_period_validator | fail | Checks whether retrieved evidence periods match the target fiscal period. |
| bm25_real | entity_validator | fail | Checks whether retrieved evidence belongs to the target company universe. |
| bm25_real | citation_validator | pass | Checks whether retrieved evidence covers all expected evidence roles. |
| bm25_real | unsupported_claim_detector | skip | Checks whether an insufficient claim was over-supported. |
| bm25_real | contradiction_detector | skip | Checks whether contradiction-labeled tasks receive a contradiction verdict. |
| dense_real | numeric_reconciliation | fail | phase6:aapl:single_company_trend:num1=fail |
| dense_real | fiscal_period_validator | fail | Checks whether retrieved evidence periods match the target fiscal period. |
| dense_real | entity_validator | fail | Checks whether retrieved evidence belongs to the target company universe. |
| dense_real | citation_validator | pass | Checks whether retrieved evidence covers all expected evidence roles. |
| dense_real | unsupported_claim_detector | skip | Checks whether an insufficient claim was over-supported. |
| dense_real | contradiction_detector | skip | Checks whether contradiction-labeled tasks receive a contradiction verdict. |
| hybrid_real | numeric_reconciliation | pass | phase6:aapl:single_company_trend:num1=pass |
| hybrid_real | fiscal_period_validator | fail | Checks whether retrieved evidence periods match the target fiscal period. |
| hybrid_real | entity_validator | fail | Checks whether retrieved evidence belongs to the target company universe. |
| hybrid_real | citation_validator | pass | Checks whether retrieved evidence covers all expected evidence roles. |
| hybrid_real | unsupported_claim_detector | skip | Checks whether an insufficient claim was over-supported. |
| hybrid_real | contradiction_detector | skip | Checks whether contradiction-labeled tasks receive a contradiction verdict. |
| graph_real | numeric_reconciliation | pass | phase6:aapl:single_company_trend:num1=pass |
| graph_real | fiscal_period_validator | pass | Checks whether retrieved evidence periods match the target fiscal period. |
| graph_real | entity_validator | pass | Checks whether retrieved evidence belongs to the target company universe. |
| graph_real | citation_validator | pass | Checks whether retrieved evidence covers all expected evidence roles. |
| graph_real | unsupported_claim_detector | skip | Checks whether an insufficient claim was over-supported. |
| graph_real | contradiction_detector | skip | Checks whether contradiction-labeled tasks receive a contradiction verdict. |
| full_engine_real | numeric_reconciliation | pass | phase6:aapl:single_company_trend:num1=pass |
| full_engine_real | fiscal_period_validator | pass | Checks whether retrieved evidence periods match the target fiscal period. |
| full_engine_real | entity_validator | pass | Checks whether retrieved evidence belongs to the target company universe. |
| full_engine_real | citation_validator | pass | Checks whether retrieved evidence covers all expected evidence roles. |
| full_engine_real | unsupported_claim_detector | skip | Checks whether an insufficient claim was over-supported. |
| full_engine_real | contradiction_detector | skip | Checks whether contradiction-labeled tasks receive a contradiction verdict. |

## Memo Snippet

Full engine verdict: support. Expected verdict: support. The memo cites 5 retrieved evidence units and separates retrieval output from validator judgment. Limitation: No validator failure was detected for the full-engine method on this case.

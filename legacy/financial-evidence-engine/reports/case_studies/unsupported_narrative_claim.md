# Unsupported Narrative Claim

- Case ID: `unsupported_narrative_claim`
- Task ID: `phase6:aapl:management_claim_verification`
- Failure mode: `unsupported_claim`
- Expected verdict: `insufficient`
- Full engine verdict: `insufficient`

## Claim

Apple's FY2024 margin expansion was driven by durable operating leverage.

## Gold Evidence

| Evidence | Source | Company | Period | Metric | Role |
| --- | --- | --- | --- | --- | --- |
| `phase6:aapl:management_claim_verification:ev1` | transcript/transcript | AAPL | FY2024 | operating_margin | management operating leverage statement |
| `phase6:aapl:management_claim_verification:ev2` | sec_xbrl_companyfacts/xbrl | AAPL | FY2024 | operating_margin | current margin numerator and denominator |
| `phase6:aapl:management_claim_verification:ev3` | sec_filing/text | AAPL | FY2024 | operating_expense | cost structure disclosure |

## Retrieved Evidence by Method

### bm25_real

Predicted verdict: `support`

| Evidence | Source | Company | Period | Metric |
| --- | --- | --- | --- | --- |
| `phase6:aapl:management_claim_verification:ev1` | transcript/transcript | AAPL | FY2024 | operating_margin |
| `phase6:aapl:management_claim_verification:ev3` | sec_filing/text | AAPL | FY2024 | operating_expense |
| `phase6:aapl:management_claim_verification:ev2` | sec_xbrl_companyfacts/xbrl | AAPL | FY2024 | operating_margin |
| `phase6:aapl:management_claim_verification:dist1` | transcript/transcript | AAPL | FY2024 | operating_margin |
| `phase6:aapl:management_claim_verification:dist2` | transcript/transcript | AAPL | FY2024 | one_time_charge |

### dense_real

Predicted verdict: `support`

| Evidence | Source | Company | Period | Metric |
| --- | --- | --- | --- | --- |
| `phase6:aapl:management_claim_verification:ev1` | transcript/transcript | AAPL | FY2024 | operating_margin |
| `phase6:aapl:management_claim_verification:dist1` | transcript/transcript | AAPL | FY2024 | operating_margin |
| `phase6:aapl:management_claim_verification:ev2` | sec_xbrl_companyfacts/xbrl | AAPL | FY2024 | operating_margin |
| `phase6:aapl:management_claim_verification:ev3` | sec_filing/text | AAPL | FY2024 | operating_expense |
| `phase6:wmt:management_claim_verification:ev1` | transcript/transcript | WMT | FY2024 | operating_margin |

### hybrid_real

Predicted verdict: `support`

| Evidence | Source | Company | Period | Metric |
| --- | --- | --- | --- | --- |
| `phase6:aapl:management_claim_verification:ev1` | transcript/transcript | AAPL | FY2024 | operating_margin |
| `phase6:aapl:management_claim_verification:ev3` | sec_filing/text | AAPL | FY2024 | operating_expense |
| `phase6:aapl:management_claim_verification:ev2` | sec_xbrl_companyfacts/xbrl | AAPL | FY2024 | operating_margin |
| `phase6:aapl:management_claim_verification:dist1` | transcript/transcript | AAPL | FY2024 | operating_margin |
| `phase6:aapl:management_claim_verification:dist2` | transcript/transcript | AAPL | FY2024 | one_time_charge |

### graph_real

Predicted verdict: `support`

| Evidence | Source | Company | Period | Metric |
| --- | --- | --- | --- | --- |
| `phase6:aapl:management_claim_verification:ev1` | transcript/transcript | AAPL | FY2024 | operating_margin |
| `phase6:aapl:management_claim_verification:ev3` | sec_filing/text | AAPL | FY2024 | operating_expense |
| `phase6:aapl:management_claim_verification:ev2` | sec_xbrl_companyfacts/xbrl | AAPL | FY2024 | operating_margin |
| `phase6:aapl:management_claim_verification:dist1` | transcript/transcript | AAPL | FY2024 | operating_margin |
| `phase6:aapl:management_claim_verification:dist2` | transcript/transcript | AAPL | FY2024 | one_time_charge |

### full_engine_real

Predicted verdict: `insufficient`

| Evidence | Source | Company | Period | Metric |
| --- | --- | --- | --- | --- |
| `phase6:aapl:management_claim_verification:ev1` | transcript/transcript | AAPL | FY2024 | operating_margin |
| `phase6:aapl:management_claim_verification:ev3` | sec_filing/text | AAPL | FY2024 | operating_expense |
| `phase6:aapl:management_claim_verification:ev2` | sec_xbrl_companyfacts/xbrl | AAPL | FY2024 | operating_margin |
| `phase6:aapl:management_claim_verification:dist1` | transcript/transcript | AAPL | FY2024 | operating_margin |
| `phase6:aapl:management_claim_verification:dist2` | transcript/transcript | AAPL | FY2024 | one_time_charge |

## Failure Reasons by Method

| Method | Failure reasons |
| --- | --- |
| bm25_real | numeric_validation_gap: Numeric validation did not pass for this task.; unsupported_claim: The method over-supported an insufficient claim. |
| dense_real | entity_mismatch: Retrieved evidence belongs to the wrong company.; numeric_validation_gap: Numeric validation did not pass for this task.; unsupported_claim: The method over-supported an insufficient claim. |
| hybrid_real | unsupported_claim: The method over-supported an insufficient claim. |
| graph_real | numeric_validation_gap: Numeric validation did not pass for this task.; unsupported_claim: The method over-supported an insufficient claim. |
| full_engine_real | No failure detected for this method on this case. |

## Validator Checks Triggered

| Method | Validator | Status | Detail |
| --- | --- | --- | --- |
| bm25_real | numeric_reconciliation | fail | phase6:aapl:management_claim_verification:num1=fail, phase6:aapl:management_claim_verification:num2=fail |
| bm25_real | fiscal_period_validator | pass | Checks whether retrieved evidence periods match the target fiscal period. |
| bm25_real | entity_validator | pass | Checks whether retrieved evidence belongs to the target company universe. |
| bm25_real | citation_validator | pass | Checks whether retrieved evidence covers all expected evidence roles. |
| bm25_real | unsupported_claim_detector | fail | Checks whether an insufficient claim was over-supported. |
| bm25_real | contradiction_detector | skip | Checks whether contradiction-labeled tasks receive a contradiction verdict. |
| dense_real | numeric_reconciliation | fail | phase6:aapl:management_claim_verification:num1=fail, phase6:aapl:management_claim_verification:num2=fail |
| dense_real | fiscal_period_validator | pass | Checks whether retrieved evidence periods match the target fiscal period. |
| dense_real | entity_validator | fail | Checks whether retrieved evidence belongs to the target company universe. |
| dense_real | citation_validator | pass | Checks whether retrieved evidence covers all expected evidence roles. |
| dense_real | unsupported_claim_detector | fail | Checks whether an insufficient claim was over-supported. |
| dense_real | contradiction_detector | skip | Checks whether contradiction-labeled tasks receive a contradiction verdict. |
| hybrid_real | numeric_reconciliation | pass | phase6:aapl:management_claim_verification:num1=pass, phase6:aapl:management_claim_verification:num2=pass |
| hybrid_real | fiscal_period_validator | pass | Checks whether retrieved evidence periods match the target fiscal period. |
| hybrid_real | entity_validator | pass | Checks whether retrieved evidence belongs to the target company universe. |
| hybrid_real | citation_validator | pass | Checks whether retrieved evidence covers all expected evidence roles. |
| hybrid_real | unsupported_claim_detector | fail | Checks whether an insufficient claim was over-supported. |
| hybrid_real | contradiction_detector | skip | Checks whether contradiction-labeled tasks receive a contradiction verdict. |
| graph_real | numeric_reconciliation | fail | phase6:aapl:management_claim_verification:num1=fail, phase6:aapl:management_claim_verification:num2=fail |
| graph_real | fiscal_period_validator | pass | Checks whether retrieved evidence periods match the target fiscal period. |
| graph_real | entity_validator | pass | Checks whether retrieved evidence belongs to the target company universe. |
| graph_real | citation_validator | pass | Checks whether retrieved evidence covers all expected evidence roles. |
| graph_real | unsupported_claim_detector | fail | Checks whether an insufficient claim was over-supported. |
| graph_real | contradiction_detector | skip | Checks whether contradiction-labeled tasks receive a contradiction verdict. |
| full_engine_real | numeric_reconciliation | pass | phase6:aapl:management_claim_verification:num1=pass, phase6:aapl:management_claim_verification:num2=pass |
| full_engine_real | fiscal_period_validator | pass | Checks whether retrieved evidence periods match the target fiscal period. |
| full_engine_real | entity_validator | pass | Checks whether retrieved evidence belongs to the target company universe. |
| full_engine_real | citation_validator | pass | Checks whether retrieved evidence covers all expected evidence roles. |
| full_engine_real | unsupported_claim_detector | pass | Checks whether an insufficient claim was over-supported. |
| full_engine_real | contradiction_detector | skip | Checks whether contradiction-labeled tasks receive a contradiction verdict. |

## Memo Snippet

Full engine verdict: insufficient. Expected verdict: insufficient. The memo cites 5 retrieved evidence units and separates retrieval output from validator judgment. Limitation: No validator failure was detected for the full-engine method on this case.

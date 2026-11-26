# Adversarial / Red-Team Evaluation

The full engine is reliability-oriented: perfect accuracy is not required, but every adversarial failure must have an explainable failure reason and validator owner.

- Tasks: `120`
- Failure modes: `12`
- Full-engine detection accuracy: `0.75`
- Explainable failure rate: `1`

## Failure Mode Counts

| Failure mode | Count |
| --- | ---: |
| `claim_with_no_evidence` | 10 |
| `deck_only_claim` | 10 |
| `irrelevant_citation_section` | 10 |
| `stale_filing` | 10 |
| `structured_fact_contradiction` | 10 |
| `transcript_only_claim` | 10 |
| `wrong_company_alias` | 10 |
| `wrong_currency` | 10 |
| `wrong_fiscal_year` | 10 |
| `wrong_quarter` | 10 |
| `wrong_segment` | 10 |
| `wrong_unit_scale` | 10 |

## Validator Coverage Matrix

| Validator | Covered failure modes | Total tasks |
| --- | --- | ---: |
| `citation_validator` | `irrelevant_citation_section` | 10 |
| `currency_validator` | `wrong_currency` | 10 |
| `deck_gap_validator` | `deck_only_claim` | 10 |
| `entity_validator` | `wrong_company_alias` | 10 |
| `fiscal_period_validator` | `wrong_fiscal_year`, `wrong_quarter` | 20 |
| `segment_validator` | `wrong_segment` | 10 |
| `stale_filing_validator` | `stale_filing` | 10 |
| `structured_fact_contradiction_detector` | `structured_fact_contradiction` | 10 |
| `transcript_source_validator` | `transcript_only_claim` | 10 |
| `unit_scale_validator` | `wrong_unit_scale` | 10 |
| `unsupported_claim_detector` | `claim_with_no_evidence` | 10 |

## Example Explainable Failures

| Task | Mode | Detected | Reason |
| --- | --- | --- | --- |
| `phase15:aapl:wrong_fiscal_year` | `wrong_fiscal_year` | `True` | Apple task should trigger wrong_fiscal_year because the cited evidence violates the validator-owned constraint. |
| `phase15:aapl:wrong_quarter` | `wrong_quarter` | `True` | Apple task should trigger wrong_quarter because the cited evidence violates the validator-owned constraint. |
| `phase15:aapl:wrong_company_alias` | `wrong_company_alias` | `True` | Apple task should trigger wrong_company_alias because the cited evidence violates the validator-owned constraint. |
| `phase15:aapl:wrong_segment` | `wrong_segment` | `False` | Missed wrong_segment; validator owner remains segment_validator. |
| `phase15:aapl:wrong_currency` | `wrong_currency` | `True` | Apple task should trigger wrong_currency because the cited evidence violates the validator-owned constraint. |
| `phase15:aapl:wrong_unit_scale` | `wrong_unit_scale` | `True` | Apple task should trigger wrong_unit_scale because the cited evidence violates the validator-owned constraint. |
| `phase15:aapl:stale_filing` | `stale_filing` | `True` | Apple task should trigger stale_filing because the cited evidence violates the validator-owned constraint. |
| `phase15:aapl:irrelevant_citation_section` | `irrelevant_citation_section` | `True` | Apple task should trigger irrelevant_citation_section because the cited evidence violates the validator-owned constraint. |
| `phase15:aapl:claim_with_no_evidence` | `claim_with_no_evidence` | `True` | Apple task should trigger claim_with_no_evidence because the cited evidence violates the validator-owned constraint. |
| `phase15:aapl:structured_fact_contradiction` | `structured_fact_contradiction` | `True` | Apple task should trigger structured_fact_contradiction because the cited evidence violates the validator-owned constraint. |
| `phase15:aapl:deck_only_claim` | `deck_only_claim` | `False` | Missed deck_only_claim; validator owner remains deck_gap_validator. |
| `phase15:aapl:transcript_only_claim` | `transcript_only_claim` | `False` | Missed transcript_only_claim; validator owner remains transcript_source_validator. |

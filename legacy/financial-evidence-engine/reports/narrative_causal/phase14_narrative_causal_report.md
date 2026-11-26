# Narrative and Causal Claim Verification

This report shows why ordinary RAG overclaims causal narratives: it treats numeric support or management language as enough to support causal wording.

- Tasks: `10`
- Ordinary RAG overclaim cases: `8`
- Ordinary RAG overclaim rate: `0.8`

## Partial Verdict Counts

| Verdict | Count |
| --- | ---: |
| `contradict_narrative` | 1 |
| `contradict_numeric` | 1 |
| `insufficient_causal_support` | 5 |
| `support_narrative` | 2 |
| `support_numeric_only` | 1 |

## Overclaim Examples

| Task | Ordinary RAG | Validator-gated | Failure reason |
| --- | --- | --- | --- |
| `phase14:nvda:data_center_driver` | `support_narrative` | `insufficient_causal_support` | numeric or narrative evidence exists, but causal attribution is not directly supported |
| `phase14:aapl:services_margin` | `support_narrative` | `insufficient_causal_support` | numeric or narrative evidence exists, but causal attribution is not directly supported |
| `phase14:amzn:aws_offset` | `support_narrative` | `support_numeric_only` | ordinary RAG overstates the level of support |
| `phase14:jpm:rate_benefit` | `support_narrative` | `insufficient_causal_support` | numeric or narrative evidence exists, but causal attribution is not directly supported |
| `phase14:tsla:margin_improvement` | `support_narrative` | `contradict_numeric` | ordinary RAG accepts narrative language despite a numeric contradiction |
| `phase14:meta:risk_reduced` | `support_narrative` | `contradict_narrative` | ordinary RAG accepts optimistic language despite contradictory filed narrative evidence |
| `phase14:wmt:deck_margin` | `support_narrative` | `insufficient_causal_support` | numeric or narrative evidence exists, but causal attribution is not directly supported |
| `phase14:googl:guidance_ai` | `support_narrative` | `insufficient_causal_support` | numeric or narrative evidence exists, but causal attribution is not directly supported |

## Memo Separation

# Narrative and Causal Claim Verification Memo

## Evidence-supported numeric trend
- NVIDIA FY2024 total revenue grew.
- Data center revenue accounted for the dominant growth contribution.
- Microsoft cloud revenue grew in FY2024.
- Cloud growth exceeded the reported drag from weaker segments.
- Apple FY2024 operating margin improved.
- Services revenue mix increased.
- AWS revenue grew in FY2024.
- Retail margin pressure remained visible.
- JPMorgan FY2024 net income was strong.
- Net interest income increased.
- Reported FY2024 revenue is inside the cited range.
- Management guidance range is contemporaneous with the period.
- Deck margin chart shows margin progress.
- Filing operating margin reconciles to the deck direction.
- Cloud guidance improved in management commentary.
- Cloud revenue grew in FY2024.

## Inference
- Data center contribution is a supported inference from segment share evidence.
- Cloud offset is supported by segment contribution and management discussion.
- Services mix is a plausible inference, but not a fully supported causal conclusion.
- AWS growth and retail pressure are both supported numeric facts.
- Net interest income contribution is supported as a component of earnings strength.
- The guidance narrative is supported because actuals reconcile to the cited range.
- Deck chart and filing metric support margin progress.
- Cloud guidance and cloud revenue growth are supported.

## Unsupported causal attribution
- Demand was the primary causal driver, but no direct demand evidence is present.
- Services mix causality is not directly supported against the one-time cost-cut alternative.
- Primary-cause wording is unsupported without a driver attribution bridge.
- Automation-driven causality is unsupported by the extracted deck evidence.
- AI demand as the cause of guidance improvement remains insufficiently supported.

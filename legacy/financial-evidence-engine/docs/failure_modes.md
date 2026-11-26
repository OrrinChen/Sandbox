# Failure Modes

## Retrieval Failures

- fiscal-period confusion: evidence from FY2023 or Q4 is used for an FY2024 annual claim.
- entity mismatch: evidence belongs to a similarly named company or peer.
- citation mismatch: cited evidence does not cover the actual claim.
- unsupported narrative: a causal or management claim is treated as filing-backed fact.

## Numeric Failures

- numeric/unit mismatch: millions, billions, and raw dollars are compared without normalization.
- wrong currency: USD and non-USD evidence are mixed.
- structured fact contradiction: narrative text conflicts with XBRL or filing facts.

## Multimodal Failures

- chart gap: text-only retrieval cannot verify a chart value.
- deck-only claim: investor-deck narrative lacks filing or XBRL support.
- transcript-only claim: management commentary is used as authoritative fact without support.

## Response Strategy

The full engine should not pretend every case is solved. It should return support, contradict, or insufficient with a validator-owned failure reason and traceable evidence.

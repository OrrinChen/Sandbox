"""Claim-to-evidence linking models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class ClaimLink:
    """Explicit claim links to evidence units for early graph construction."""

    claim_id: str
    text: str
    supporting_evidence_ids: Tuple[str, ...] = ()
    contradicting_evidence_ids: Tuple[str, ...] = ()

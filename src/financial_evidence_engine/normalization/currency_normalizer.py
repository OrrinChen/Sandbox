"""Currency normalization helpers."""

from __future__ import annotations

import re
from typing import Optional


class CurrencyNormalizer:
    """Recognize common currency labels in financial units."""

    _code_pattern = re.compile(r"\b(USD|EUR|GBP|JPY|CNY)\b", re.IGNORECASE)

    def normalize(self, raw_unit: str) -> Optional[str]:
        unit = raw_unit.strip()
        if not unit:
            return None

        code_match = self._code_pattern.search(unit)
        if code_match:
            return code_match.group(1).upper()

        lowered = unit.lower()
        if "$" in unit or "us dollars" in lowered or "u.s. dollars" in lowered or "dollars" in lowered:
            return "USD"
        if "euros" in lowered:
            return "EUR"
        if "pounds" in lowered:
            return "GBP"
        if "yen" in lowered:
            return "JPY"
        if "yuan" in lowered or "renminbi" in lowered:
            return "CNY"
        return None

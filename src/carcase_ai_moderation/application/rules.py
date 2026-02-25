from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RuleBasedBlocker:
    url_pattern: re.Pattern[str] = re.compile(r"(https?://|t\\.me/|telegram\\.me/)", re.IGNORECASE)
    long_number_pattern: re.Pattern[str] = re.compile(r"\\b\\d{10,}\\b")

    def categories_for_text(self, text_norm: str) -> set[str]:
        categories: set[str] = set()

        if self.url_pattern.search(text_norm):
            categories.add("spam_ads_scam")

        if self.long_number_pattern.search(text_norm):
            categories.add("pii_doxxing")

        return categories

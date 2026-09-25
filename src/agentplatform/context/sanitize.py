from __future__ import annotations

import re

_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_ACCT = re.compile(r"\b(?:acct|account)(?:\s*(?:no\.?|number|#))?\s*[:#]?\s*(\d{4,})(\d{4})\b", re.I)
_HIDDEN = re.compile(r"[\u200b-\u200f\u2060\ufeff]")


def redact_pii(text: str) -> str:
    text = _HIDDEN.sub("", text)
    text = _SSN.sub("***-**-****", text)
    return _ACCT.sub(lambda m: f"account ****{m.group(2)}", text)


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)

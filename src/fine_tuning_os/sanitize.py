# SPDX-License-Identifier: Apache-2.0
# src/fine_tuning_os/sanitize.py
"""Zero-Data text/log sanitization filters.

Every external string (remote logs, debug samples) MUST pass through
sanitize_text before being returned to Claude. Order matters: credential
URLs are masked whole before their host/email parts can match.
"""

from __future__ import annotations

import re

_URL_CRED_RE = re.compile(r"\b\w+://[^\s:/@]+:[^\s:/@]+@\S+")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
# No trailing \b: it would never match after '=' padding (= is non-word),
# leaving the "==" tail of a base64 blob unmasked. The {0,2} stays greedy.
_BASE64_RE = re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}")

_MASKS: tuple[tuple[re.Pattern[str], str], ...] = (
    (_URL_CRED_RE, "[REDACTED:URL_CRED]"),
    (_EMAIL_RE, "[REDACTED:EMAIL]"),
    (_IPV4_RE, "[REDACTED:IP]"),
    (_BASE64_RE, "[REDACTED:BLOB]"),
)


def sanitize_text(text: str) -> tuple[str, int]:
    """Return (masked_text, number_of_substitutions)."""
    out = text
    count = 0
    for pattern, mask in _MASKS:
        out, n = pattern.subn(mask, out)
        count += n
    return out, count

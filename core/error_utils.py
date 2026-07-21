"""Sanitize exception text before it's logged or returned to a client.

Wrapped google-genai exceptions can embed the API key that triggered them
(e.g. in a request URL's ?key=... query string). safe_error() strips known
key-shaped substrings so a stray print(...) or an error field sent back to
the browser can't leak a live Gemini key.
"""

import re

_KEY_RE = re.compile(
    r"AIza[0-9A-Za-z_\-]{35}"
    r"|([?&]key=)[^&\s\"']+"
    r"|(api[_-]?key[\"']?\s*[:=]\s*[\"']?)[\w\-]{8,}",
    re.IGNORECASE,
)


def safe_error(exc: Exception) -> str:
    def _redact(m: "re.Match") -> str:
        prefix = next((g for g in m.groups() if g), "")
        return f"{prefix}[REDACTED]"

    return _KEY_RE.sub(_redact, str(exc))

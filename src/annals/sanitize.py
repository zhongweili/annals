"""Best-effort credential scrubbing for structured config files.

Transcript bodies are NOT sanitized — they routinely contain secrets in
shell output, and pretending otherwise would be a false security boundary.
This module is for settings.json-shaped documents: keep the keys so the
archive still shows what was configured, replace only the secret values.

Key names are not a sufficient signal. A real OTEL header once carried a
Bearer token under a key that matched neither 'token' nor 'key'.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

VALUE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)(bearer\s+)([A-Za-z0-9_\-.]{16,})"), r"\1<REDACTED>"),
    (
        re.compile(r"(?i)(authorization\s*=\s*bearer\s+)([A-Za-z0-9_\-.]{16,})"),
        r"\1<REDACTED>",
    ),
    (re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{20,})"), "<REDACTED>"),
    (re.compile(r"\b(sk-[A-Za-z0-9\-]{20,})"), "<REDACTED>"),
    (re.compile(r"\b(dapi[a-f0-9]{20,})"), "<REDACTED>"),
    (re.compile(r"\b((?:AKIA|ASIA)[0-9A-Z]{16})\b"), "<REDACTED>"),
    (re.compile(r"\b(xox[baprs]-[0-9A-Za-z\-]{10,})"), "<REDACTED>"),
    (re.compile(r"\b(AIza[0-9A-Za-z_\-]{35})\b"), "<REDACTED>"),
]

KEY_PATTERN = re.compile(r"(?i)(token|secret|password|api[_-]?key|credential)")

PLACEHOLDER = "<REDACTED>"


def scrub(obj: Any, hits: list[str] | None = None) -> Any:
    """Return a copy of *obj* with secret-shaped values replaced."""
    if hits is None:
        hits = []
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            if KEY_PATTERN.search(k) and isinstance(v, str) and len(v) > 8:
                out[k] = PLACEHOLDER
                hits.append(k)
            else:
                out[k] = scrub(v, hits)
        return out
    if isinstance(obj, list):
        return [scrub(x, hits) for x in obj]
    if isinstance(obj, str):
        s = obj
        for pat, repl in VALUE_PATTERNS:
            new = pat.sub(repl, s)
            if new != s:
                hits.append("(value match)")
            s = new
        return s
    return obj


def dump_sanitized(data: Any) -> str:
    clean = scrub(data)
    return json.dumps(clean, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def write_if_changed(src: Path, dst: Path) -> tuple[bool, int]:
    """Sanitize JSON at *src* into *dst*. Returns (wrote, hit_count)."""
    if not src.is_file():
        return False, 0
    hits: list[str] = []
    body = json.dumps(
        scrub(json.loads(src.read_text()), hits),
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
    ) + "\n"
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.is_file() and dst.read_text() == body:
        return False, len(hits)
    dst.write_text(body)
    return True, len(hits)

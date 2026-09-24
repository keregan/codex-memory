from __future__ import annotations

import re
import unicodedata


RESERVED_NAMES = {
    "aux", "con", "nul", "prn",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


def safe_project_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().lower()
    normalized = re.sub(r"[\s-]+", "_", normalized)
    normalized = re.sub(r"[^\w.]", "", normalized, flags=re.UNICODE)
    normalized = normalized.strip("._")
    if not normalized:
        raise ValueError(f"Invalid empty project name derived from: {value!r}")
    if normalized.casefold() in RESERVED_NAMES:
        normalized = f"project_{normalized}"
    normalized = normalized[:80].rstrip(". ")
    if not normalized:
        raise ValueError(f"Invalid project name derived from: {value!r}")
    return normalized

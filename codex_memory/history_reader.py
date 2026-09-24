from __future__ import annotations

import re
from pathlib import Path

from .models import Message


ROLE_RE = re.compile(
    r"^(?:\[?)(user|assistant|system|пользователь|ассистент|codex)(?:\]?)\s*[:：-]\s*",
    re.IGNORECASE,
)
DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?)\s*")


def read_history(path: Path) -> list[Message]:
    if not path.is_file():
        raise FileNotFoundError(f"History file not found: {path}")

    return parse_history(_read_text(path))


def parse_history(raw: str) -> list[Message]:
    blocks = [block.strip() for block in re.split(r"\r?\n\s*\r?\n", raw) if block.strip()]
    if not blocks and raw.strip():
        blocks = [raw.strip()]

    messages = []
    for number, block in enumerate(blocks, start=1):
        date = None
        date_match = DATE_RE.match(block)
        if date_match:
            date = date_match.group(1)
            block = block[date_match.end() :].lstrip(" -:|")

        role = None
        role_match = ROLE_RE.match(block)
        if role_match:
            role = _normalize_role(role_match.group(1))
            block = block[role_match.end() :]

        messages.append(Message(number=number, text=block.strip(), role=role, date=date))
    return messages


def _read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Unable to determine text encoding for {path}")


def _normalize_role(role: str) -> str:
    value = role.casefold()
    if value in {"user", "пользователь"}:
        return "user"
    if value in {"assistant", "ассистент", "codex"}:
        return "assistant"
    return "system"

from __future__ import annotations

from .models import Message


DEFAULT_CHUNK_CHARS = 50_000
MIN_CHUNK_CHARS = 1_000


def chunk_messages(messages: list[Message], max_chars: int = DEFAULT_CHUNK_CHARS) -> list[list[Message]]:
    """Split messages into ordered, non-overlapping chunks with a soft character limit."""
    if max_chars < MIN_CHUNK_CHARS:
        raise ValueError(f"Chunk size must be at least {MIN_CHUNK_CHARS} characters")
    if not messages:
        return []

    expanded: list[Message] = []
    text_limit = max_chars - 128
    for message in messages:
        if _message_size(message) <= max_chars:
            expanded.append(message)
            continue
        for part in _split_text(message.text, text_limit):
            expanded.append(Message(
                number=message.number,
                text=part,
                role=message.role,
                date=message.date,
            ))

    chunks: list[list[Message]] = []
    current: list[Message] = []
    current_size = 0
    for message in expanded:
        size = _message_size(message)
        if current and current_size + size > max_chars:
            chunks.append(current)
            current = []
            current_size = 0
        current.append(message)
        current_size += size
    if current:
        chunks.append(current)
    return chunks


def _message_size(message: Message) -> int:
    return len(message.text) + len(message.role or "") + len(message.date or "") + 64


def _split_text(text: str, limit: int) -> list[str]:
    remaining = text.strip()
    parts = []
    while len(remaining) > limit:
        boundary = max(remaining.rfind("\n", 0, limit), remaining.rfind(" ", 0, limit))
        if boundary < limit // 2:
            boundary = limit
        part = remaining[:boundary].strip()
        if part:
            parts.append(part)
        remaining = remaining[boundary:].strip()
    if remaining:
        parts.append(remaining)
    return parts

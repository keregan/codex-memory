from __future__ import annotations

from datetime import datetime, timezone
import json
import re
from pathlib import Path
from typing import Any

from .models import Message


ROLE_RE = re.compile(
    r"^(?:\[?)(user|assistant|system|пользователь|ассистент|codex)(?:\]?)\s*[:：-]\s*",
    re.IGNORECASE,
)
DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?)\s*")
MARKDOWN_ROLE_RE = re.compile(
    r"(?im)^(?:#{1,6}\s*(user|assistant|system|пользователь|ассистент|codex)\s*:?[ \t]*"
    r"|\*\*(user|assistant|system|пользователь|ассистент|codex)\s*:\*\*[ \t]*)$"
)
JSON_SUFFIXES = {".json"}
JSON_LINES_SUFFIXES = {".jsonl", ".ndjson"}
MARKDOWN_SUFFIXES = {".md", ".markdown"}
MAX_STRUCTURED_DEPTH = 64


def read_history(path: Path) -> list[Message]:
    """Read, but never modify, a supported history export."""
    if not path.is_file():
        raise FileNotFoundError(f"History file not found: {path}")

    raw = _read_text(path)
    suffix = path.suffix.casefold()
    if suffix in JSON_SUFFIXES:
        return _parse_json_document(raw, source=str(path), strict=True)
    if suffix in JSON_LINES_SUFFIXES:
        return _parse_json_lines(raw, source=str(path), strict=True)
    if suffix in MARKDOWN_SUFFIXES:
        return _parse_markdown(raw) or _parse_plain_history(raw)
    return parse_history(raw)


def parse_history(raw: str) -> list[Message]:
    """Auto-detect structured clipboard/text content, then fall back to plain text."""
    stripped = raw.lstrip()
    if stripped.startswith(("{", "[")):
        messages = _parse_json_document(raw, source="input", strict=False)
        if messages:
            return messages

    messages = _parse_json_lines(raw, source="input", strict=False)
    if messages:
        return messages

    messages = _parse_markdown(raw)
    return messages or _parse_plain_history(raw)


def _parse_plain_history(raw: str) -> list[Message]:
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


def _parse_markdown(raw: str) -> list[Message]:
    markers = list(MARKDOWN_ROLE_RE.finditer(raw))
    if not markers:
        return []

    messages = []
    for index, marker in enumerate(markers):
        end = markers[index + 1].start() if index + 1 < len(markers) else len(raw)
        text = raw[marker.end() : end].strip()
        if not text:
            continue
        role = marker.group(1) or marker.group(2)
        messages.append(
            Message(number=len(messages) + 1, text=text, role=_normalize_role(role), date=None)
        )
    return messages


def _parse_json_document(raw: str, *, source: str, strict: bool) -> list[Message]:
    try:
        data = json.loads(raw)
    except RecursionError as exc:
        if strict:
            raise ValueError(f"JSON history file is nested too deeply: {source}") from exc
        return []
    except json.JSONDecodeError as exc:
        if strict:
            raise ValueError(f"Invalid JSON history file {source}: {exc.msg}") from exc
        return []

    messages = _messages_from_structured(data)
    if strict and not messages:
        raise ValueError(f"JSON history file contains no supported messages: {source}")
    return messages


def _parse_json_lines(raw: str, *, source: str, strict: bool) -> list[Message]:
    records: list[Any] = []
    for line_number, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            continue
        if not strict and not line.lstrip().startswith(("{", "[")):
            return []
        try:
            records.append(json.loads(line))
        except RecursionError as exc:
            if strict:
                raise ValueError(
                    f"JSONL history file {source} is nested too deeply at line {line_number}"
                ) from exc
            return []
        except json.JSONDecodeError as exc:
            if strict:
                raise ValueError(
                    f"Invalid JSONL history file {source} at line {line_number}: {exc.msg}"
                ) from exc
            return []

    messages = _messages_from_structured(records)
    if strict and not messages:
        raise ValueError(f"JSONL history file contains no supported messages: {source}")
    return messages


def _messages_from_structured(data: Any) -> list[Message]:
    records = _collect_message_records(data)
    messages = []
    for record in records:
        message = _message_from_record(record, len(messages) + 1)
        if message is not None:
            messages.append(message)
    return messages


def _collect_message_records(data: Any, depth: int = 0) -> list[dict[str, Any]]:
    if depth > MAX_STRUCTURED_DEPTH:
        raise ValueError("Structured history is nested too deeply")
    if isinstance(data, list):
        records: list[dict[str, Any]] = []
        for item in data:
            records.extend(_collect_message_records(item, depth + 1))
        return records
    if not isinstance(data, dict):
        return []

    mapping = data.get("mapping")
    if isinstance(mapping, dict):
        return _records_from_mapping(mapping, data.get("current_node"))

    for key in (
        "messages", "chat_messages", "conversation", "conversations", "items", "data",
    ):
        value = data.get(key)
        if isinstance(value, (list, dict)):
            records = _collect_message_records(value, depth + 1)
            if records:
                return records

    nested = data.get("message")
    if isinstance(nested, dict):
        return [nested]
    if _looks_like_message(data):
        return [data]
    return []


def _records_from_mapping(mapping: dict[str, Any], current_node: Any) -> list[dict[str, Any]]:
    if isinstance(current_node, str) and current_node in mapping:
        chain: list[dict[str, Any]] = []
        node_id: str | None = current_node
        visited: set[str] = set()
        while node_id and node_id not in visited:
            visited.add(node_id)
            node = mapping.get(node_id)
            if not isinstance(node, dict):
                break
            message = node.get("message")
            if isinstance(message, dict):
                chain.append(message)
            parent = node.get("parent")
            node_id = parent if isinstance(parent, str) else None
        chain.reverse()
        return chain

    ordered: list[tuple[float, int, dict[str, Any]]] = []
    for index, node in enumerate(mapping.values()):
        if not isinstance(node, dict) or not isinstance(node.get("message"), dict):
            continue
        message = node["message"]
        created = _numeric_timestamp(message.get("create_time"))
        ordered.append((created if created is not None else float("inf"), index, message))
    ordered.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in ordered]


def _looks_like_message(value: dict[str, Any]) -> bool:
    has_content = any(key in value for key in ("content", "text", "parts"))
    has_role = any(key in value for key in ("role", "sender")) or isinstance(
        value.get("author"), dict
    )
    return has_content and has_role


def _message_from_record(record: dict[str, Any], number: int) -> Message | None:
    author = record.get("author")
    raw_role = record.get("role", record.get("sender"))
    if raw_role is None and isinstance(author, dict):
        raw_role = author.get("role")
    role = _normalize_structured_role(raw_role)
    text = _content_text(record.get("content"))
    if not text:
        text = _content_text(record.get("text"))
    if not text:
        text = _content_text(record.get("parts"))
    if not text:
        return None
    raw_date = record.get(
        "date", record.get("timestamp", record.get("create_time", record.get("created_at")))
    )
    return Message(number=number, text=text, role=role, date=_format_date(raw_date))


def _content_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts = [_content_text(item) for item in value]
        return "\n\n".join(part for part in parts if part)
    if isinstance(value, dict):
        for key in ("parts", "text", "content"):
            if key in value:
                return _content_text(value[key])
    return ""


def _numeric_timestamp(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _format_date(value: Any) -> str | None:
    timestamp = _numeric_timestamp(value)
    if timestamp is not None:
        try:
            return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Unable to determine text encoding for {path}")


def _normalize_structured_role(role: Any) -> str | None:
    if not isinstance(role, str):
        return None
    value = role.casefold().strip()
    if value in {"user", "пользователь", "human"}:
        return "user"
    if value in {"assistant", "ассистент", "codex", "model", "bot"}:
        return "assistant"
    if value in {"system", "developer", "tool"}:
        return "system"
    return None


def _normalize_role(role: str) -> str:
    return _normalize_structured_role(role) or "system"

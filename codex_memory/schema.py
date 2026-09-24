from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import CONFIDENCE_LEVELS, SCHEMA_VERSION, TASK_STATUSES, empty_memory


FACT_LIST_FIELDS = (
    "technologies", "architecture", "components", "implemented", "constraints", "open_questions",
)
TASK_LIST_FIELDS = ("current_tasks", "todo_tasks", "completed_tasks", "ideas", "known_bugs")
AGENT_FIELDS = ("structure", "commands", "conventions", "rules", "do_not_change")


def schema_path() -> Path:
    return Path(__file__).with_name("schemas") / "memory.schema.json"


def load_json_schema() -> dict[str, Any]:
    data = json.loads(schema_path().read_text(encoding="utf-8"))
    if data.get("properties", {}).get("schema_version", {}).get("const") != SCHEMA_VERSION:
        raise ValueError("Bundled JSON Schema version does not match the application schema version")
    return data


def validate_memory_document(data: Any) -> dict[str, Any]:
    """Validate the runtime invariants represented by the bundled JSON Schema."""
    if not isinstance(data, dict):
        raise ValueError("Memory document must be a JSON object")
    expected_keys = set(empty_memory("project"))
    missing = expected_keys - set(data)
    extra = set(data) - expected_keys
    if missing:
        raise ValueError(f"Memory document is missing fields: {', '.join(sorted(missing))}")
    if extra:
        raise ValueError(f"Memory document has unknown fields: {', '.join(sorted(extra))}")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"Expected memory schema version {SCHEMA_VERSION}")

    for field in ("project", "display_name", "summary", "purpose", "created_at", "last_updated"):
        if not isinstance(data[field], str):
            raise ValueError(f"Memory field '{field}' must be a string")
    if not data["project"]:
        raise ValueError("Memory project must not be empty")
    if not isinstance(data["aliases"], list) or not all(isinstance(item, str) for item in data["aliases"]):
        raise ValueError("Memory aliases must be a list of strings")

    for field in FACT_LIST_FIELDS:
        _validate_items(data[field], field, "text")
    for field in TASK_LIST_FIELDS:
        _validate_items(data[field], field, "title", task=True)
    _validate_items(data["decisions"], "decisions", "title", decision=True)

    instructions = data["agent_instructions"]
    if not isinstance(instructions, dict) or set(instructions) != set(AGENT_FIELDS):
        raise ValueError("Memory agent_instructions has an invalid shape")
    for field in AGENT_FIELDS:
        _validate_items(instructions[field], f"agent_instructions.{field}", "text")

    if not isinstance(data["update_history"], list):
        raise ValueError("Memory update_history must be a list")
    for event in data["update_history"]:
        if not isinstance(event, dict) or set(event) != {"date", "source", "mode"}:
            raise ValueError("Memory update_history entry has an invalid shape")
        if not all(isinstance(event[key], str) for key in event):
            raise ValueError("Memory update_history values must be strings")
        if event["mode"] not in {"create", "update"}:
            raise ValueError("Memory update_history mode must be create or update")
    return data


def _validate_items(
    value: Any,
    field: str,
    text_key: str,
    *,
    task: bool = False,
    decision: bool = False,
) -> None:
    if not isinstance(value, list):
        raise ValueError(f"Memory field '{field}' must be a list")
    for item in value:
        if isinstance(item, str):
            if not item.strip():
                raise ValueError(f"Memory field '{field}' contains an empty string")
            continue
        if not isinstance(item, dict) or not isinstance(item.get(text_key), str) or not item[text_key].strip():
            raise ValueError(f"Memory field '{field}' contains an invalid item")
        allowed_keys = {text_key, "confidence", "source_blocks"}
        if task:
            allowed_keys.add("status")
        if decision:
            allowed_keys.update({"reason", "date", "previous", "status"})
        unknown_keys = set(item) - allowed_keys
        if unknown_keys:
            raise ValueError(
                f"Memory field '{field}' contains unknown item fields: {', '.join(sorted(unknown_keys))}"
            )
        confidence = item.get("confidence")
        if confidence is not None and confidence not in CONFIDENCE_LEVELS:
            raise ValueError(f"Memory field '{field}' contains invalid confidence")
        blocks = item.get("source_blocks")
        if blocks is not None and (
            not isinstance(blocks, list)
            or not all(isinstance(number, int) and not isinstance(number, bool) and number > 0 for number in blocks)
            or len(set(blocks)) != len(blocks)
        ):
            raise ValueError(f"Memory field '{field}' contains invalid source_blocks")
        if task and item.get("status") is not None and item["status"] not in TASK_STATUSES:
            raise ValueError(f"Memory field '{field}' contains invalid task status")
        if decision:
            for optional_text in ("reason", "date", "previous"):
                if item.get(optional_text) is not None and not isinstance(item[optional_text], str):
                    raise ValueError(f"Memory decisions contain invalid {optional_text}")
            if item.get("status") is not None and item["status"] not in {"active", "superseded"}:
                raise ValueError("Memory decisions contain invalid status")

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
FACT_STATUSES = {"active", "superseded", "disputed"}


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
    seen_ids = set()
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get(text_key), str) or not item[text_key].strip():
            raise ValueError(f"Memory field '{field}' contains an invalid item")
        allowed_keys = {"id", text_key, "status", "confidence", "source_blocks", "evidence"}
        if decision:
            allowed_keys.update({"reason", "date", "previous"})
        unknown_keys = set(item) - allowed_keys
        if unknown_keys:
            raise ValueError(
                f"Memory field '{field}' contains unknown item fields: {', '.join(sorted(unknown_keys))}"
            )
        required_keys = allowed_keys
        missing_keys = required_keys - set(item)
        if missing_keys:
            raise ValueError(
                f"Memory field '{field}' item is missing fields: {', '.join(sorted(missing_keys))}"
            )
        item_id = item["id"]
        if not isinstance(item_id, str) or len(item_id) != 20 or any(
            character not in "0123456789abcdef" for character in item_id
        ):
            raise ValueError(f"Memory field '{field}' contains invalid item id")
        if item_id in seen_ids:
            raise ValueError(f"Memory field '{field}' contains duplicate item id")
        seen_ids.add(item_id)
        confidence = item["confidence"]
        if confidence not in CONFIDENCE_LEVELS:
            raise ValueError(f"Memory field '{field}' contains invalid confidence")
        if not _valid_source_blocks(item["source_blocks"]):
            raise ValueError(f"Memory field '{field}' contains invalid source_blocks")
        evidence = item["evidence"]
        if not isinstance(evidence, list):
            raise ValueError(f"Memory field '{field}' contains invalid evidence")
        for entry in evidence:
            if not isinstance(entry, dict) or set(entry) != {"source", "source_blocks", "observed_at"}:
                raise ValueError(f"Memory field '{field}' contains invalid evidence")
            if not isinstance(entry["source"], str) or not entry["source"]:
                raise ValueError(f"Memory field '{field}' evidence has invalid source")
            if not isinstance(entry["observed_at"], str) or not entry["observed_at"]:
                raise ValueError(f"Memory field '{field}' evidence has invalid observed_at")
            if not _valid_source_blocks(entry["source_blocks"]):
                raise ValueError(f"Memory field '{field}' evidence has invalid source_blocks")
        if task and item["status"] not in TASK_STATUSES:
            raise ValueError(f"Memory field '{field}' contains invalid task status")
        if decision:
            for required_text in ("reason", "date", "previous"):
                if not isinstance(item[required_text], str):
                    raise ValueError(f"Memory decisions contain invalid {required_text}")
            if item["status"] not in {"active", "superseded"}:
                raise ValueError("Memory decisions contain invalid status")
        elif not task and item["status"] not in FACT_STATUSES:
            raise ValueError(f"Memory field '{field}' contains invalid fact status")


def _valid_source_blocks(value: Any) -> bool:
    return (
        isinstance(value, list)
        and all(isinstance(number, int) and not isinstance(number, bool) and number > 0 for number in value)
        and len(set(value)) == len(value)
    )

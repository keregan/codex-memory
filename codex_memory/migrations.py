from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from .models import CONFIDENCE_LEVELS, SCHEMA_VERSION, TASK_STATUSES, empty_memory, stable_item_id
from .schema import validate_memory_document


Migration = Callable[[dict[str, Any]], dict[str, Any]]


def migrate_memory_document(data: Any) -> tuple[dict[str, Any], bool]:
    if not isinstance(data, dict):
        raise ValueError("Existing memory must be a JSON object")
    version = data.get("schema_version")
    if not isinstance(version, int) or isinstance(version, bool):
        raise ValueError("Existing memory has no valid integer schema_version")
    if version > SCHEMA_VERSION:
        raise ValueError(
            f"Memory schema version {version} is newer than supported version {SCHEMA_VERSION}"
        )

    migrated = deepcopy(data)
    changed = False
    while version < SCHEMA_VERSION:
        migration = MIGRATIONS.get(version)
        if migration is None:
            raise ValueError(f"No migration available from memory schema version {version}")
        migrated = migration(migrated)
        new_version = migrated.get("schema_version")
        if not isinstance(new_version, int) or new_version <= version:
            raise ValueError(f"Migration from schema version {version} did not advance the version")
        version = new_version
        changed = True
    return validate_memory_document(migrated), changed


def _migrate_v1_to_v2(data: dict[str, Any]) -> dict[str, Any]:
    project = str(data.get("project") or "").strip()
    display_name = str(data.get("display_name") or project.replace("_", " ").title())
    defaults = empty_memory(project, display_name)
    migrated = deepcopy(data)
    for key, value in defaults.items():
        migrated.setdefault(key, deepcopy(value))

    history = migrated.get("update_history")
    created_at = ""
    if isinstance(history, list):
        for event in history:
            if isinstance(event, dict) and isinstance(event.get("date"), str) and event["date"]:
                created_at = event["date"]
                break
    if not created_at and isinstance(migrated.get("last_updated"), str):
        created_at = migrated["last_updated"]
    migrated["created_at"] = created_at
    migrated["schema_version"] = 2
    return migrated


FACT_FIELDS = (
    "technologies", "architecture", "components", "implemented", "constraints", "open_questions",
)
TASK_FIELDS = {
    "current_tasks": "current",
    "todo_tasks": "todo",
    "completed_tasks": "completed",
    "ideas": "idea",
    "known_bugs": "bug",
}
AGENT_FIELDS = ("structure", "commands", "conventions", "rules", "do_not_change")


def _migrate_v2_to_v3(data: dict[str, Any]) -> dict[str, Any]:
    migrated = deepcopy(data)
    for field in FACT_FIELDS:
        migrated[field] = [
            _migrate_fact(item, field) for item in migrated.get(field, [])
        ]
    for field, default_status in TASK_FIELDS.items():
        migrated[field] = [
            _migrate_task(item, "tasks", default_status) for item in migrated.get(field, [])
        ]
    migrated["decisions"] = [
        _migrate_decision(item) for item in migrated.get("decisions", [])
    ]
    instructions = migrated.get("agent_instructions", {})
    for field in AGENT_FIELDS:
        values = instructions.get(field, []) if isinstance(instructions, dict) else []
        instructions[field] = [
            _migrate_fact(item, f"agent_instructions.{field}") for item in values
        ]
    migrated["agent_instructions"] = instructions
    migrated["schema_version"] = 3
    return migrated


def _base_item(item: Any, kind: str, text_key: str) -> dict[str, Any]:
    raw = item if isinstance(item, dict) else {text_key: str(item)}
    text = str(raw.get(text_key) or raw.get("text") or raw.get("title") or "").strip()
    confidence = str(raw.get("confidence", "MEDIUM")).upper()
    if confidence not in CONFIDENCE_LEVELS:
        confidence = "MEDIUM"
    blocks = raw.get("source_blocks", [])
    if not isinstance(blocks, list):
        blocks = []
    return {
        "id": stable_item_id(kind, text),
        text_key: text,
        "confidence": confidence,
        "source_blocks": blocks,
        "evidence": [],
    }


def _migrate_fact(item: Any, kind: str) -> dict[str, Any]:
    migrated = _base_item(item, kind, "text")
    raw_status = item.get("status") if isinstance(item, dict) else None
    migrated["status"] = raw_status if raw_status in {"active", "superseded", "disputed"} else "active"
    return migrated


def _migrate_task(item: Any, kind: str, default_status: str) -> dict[str, Any]:
    migrated = _base_item(item, kind, "title")
    raw_status = item.get("status") if isinstance(item, dict) else None
    migrated["status"] = raw_status if raw_status in TASK_STATUSES else default_status
    return migrated


def _migrate_decision(item: Any) -> dict[str, Any]:
    migrated = _base_item(item, "decisions", "title")
    raw = item if isinstance(item, dict) else {}
    migrated.update({
        "reason": str(raw.get("reason", "")),
        "date": str(raw.get("date", "")),
        "previous": str(raw.get("previous", "")),
        "status": raw.get("status") if raw.get("status") in {"active", "superseded"} else "active",
    })
    return migrated


MIGRATIONS: dict[int, Migration] = {
    1: _migrate_v1_to_v2,
    2: _migrate_v2_to_v3,
}

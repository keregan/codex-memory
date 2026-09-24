from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from .models import SCHEMA_VERSION, empty_memory
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


MIGRATIONS: dict[int, Migration] = {
    1: _migrate_v1_to_v2,
}

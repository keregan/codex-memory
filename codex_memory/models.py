from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


SCHEMA_VERSION = 1
CONFIDENCE_LEVELS = {"HIGH", "MEDIUM", "LOW"}
TASK_STATUSES = {"current", "todo", "idea", "bug", "completed"}


@dataclass
class Message:
    number: int
    text: str
    role: str | None = None
    date: str | None = None


@dataclass
class ProjectCandidate:
    name: str
    display_name: str
    aliases: list[str] = field(default_factory=list)
    message_numbers: list[int] = field(default_factory=list)
    confidence: str = "MEDIUM"


def empty_memory(project: str, display_name: str | None = None) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "project": project,
        "display_name": display_name or project.replace("_", " ").title(),
        "aliases": [],
        "summary": "",
        "purpose": "",
        "technologies": [],
        "architecture": [],
        "components": [],
        "implemented": [],
        "constraints": [],
        "current_tasks": [],
        "todo_tasks": [],
        "completed_tasks": [],
        "ideas": [],
        "known_bugs": [],
        "decisions": [],
        "open_questions": [],
        "agent_instructions": {
            "structure": [],
            "commands": [],
            "conventions": [],
            "rules": [],
            "do_not_change": [],
        },
        "update_history": [],
        "last_updated": "",
    }


def utc_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def message_to_dict(message: Message) -> dict[str, Any]:
    return asdict(message)


def validate_extraction(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("Analyzer response must be a JSON object")

    list_fields = (
        "technologies",
        "architecture",
        "components",
        "implemented",
        "constraints",
        "decisions",
        "tasks",
        "open_questions",
    )
    result: dict[str, Any] = {
        "summary": str(data.get("summary", "")).strip(),
        "purpose": str(data.get("purpose", "")).strip(),
    }
    for key in list_fields:
        value = data.get(key, [])
        if not isinstance(value, list):
            raise ValueError(f"Analyzer field '{key}' must be a list")
        result[key] = value

    for key in ("technologies", "architecture", "components", "implemented", "constraints", "open_questions"):
        result[key] = _clean_fact_list(result[key])
    result["decisions"] = _clean_decisions(result["decisions"])

    instructions = data.get("agent_instructions", {})
    if not isinstance(instructions, dict):
        raise ValueError("Analyzer field 'agent_instructions' must be an object")
    result["agent_instructions"] = {
        key: _clean_fact_list(value) if isinstance(value, list) else []
        for key, value in {
            "structure": instructions.get("structure", []),
            "commands": instructions.get("commands", []),
            "conventions": instructions.get("conventions", []),
            "rules": instructions.get("rules", []),
            "do_not_change": instructions.get("do_not_change", []),
        }.items()
    }

    cleaned_tasks = []
    for task in result["tasks"]:
        if not isinstance(task, dict) or not str(task.get("title", "")).strip():
            continue
        status = str(task.get("status", "todo")).lower()
        if status not in TASK_STATUSES:
            status = "todo"
        cleaned = {
            "title": str(task["title"]).strip(),
            "status": status,
            "confidence": _clean_confidence(task.get("confidence")),
            "source_blocks": _clean_source_blocks(task.get("source_blocks")),
        }
        cleaned_tasks.append(cleaned)
    result["tasks"] = cleaned_tasks
    return result


def _clean_fact_list(items: list[Any]) -> list[Any]:
    cleaned: list[Any] = []
    for item in items:
        if isinstance(item, str) and item.strip():
            cleaned.append(item.strip())
        elif isinstance(item, dict):
            text = str(item.get("text") or item.get("title") or "").strip()
            if text:
                cleaned.append({
                    "text": text,
                    "confidence": _clean_confidence(item.get("confidence")),
                    "source_blocks": _clean_source_blocks(item.get("source_blocks")),
                })
    return cleaned


def _clean_decisions(items: list[Any]) -> list[dict[str, Any]]:
    cleaned = []
    for item in items:
        if isinstance(item, str):
            item = {"title": item}
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("text") or "").strip()
        if not title:
            continue
        decision = {
            "title": title,
            "reason": str(item.get("reason", "")).strip(),
            "date": str(item.get("date", "")).strip(),
            "previous": str(item.get("previous", "")).strip(),
            "confidence": _clean_confidence(item.get("confidence")),
            "source_blocks": _clean_source_blocks(item.get("source_blocks")),
        }
        cleaned.append(decision)
    return cleaned


def _clean_confidence(value: Any) -> str:
    confidence = str(value or "MEDIUM").upper()
    return confidence if confidence in CONFIDENCE_LEVELS else "MEDIUM"


def _clean_source_blocks(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if isinstance(item, bool):
            continue
        try:
            number = int(item)
        except (TypeError, ValueError):
            continue
        if number > 0 and number not in result:
            result.append(number)
    return result

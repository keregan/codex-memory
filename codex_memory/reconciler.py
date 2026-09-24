from __future__ import annotations

import re
from copy import deepcopy
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from .models import empty_memory, utc_now


FACT_FIELDS = ("technologies", "architecture", "components", "implemented", "constraints", "open_questions")
TASK_FIELD_BY_STATUS = {
    "current": "current_tasks",
    "todo": "todo_tasks",
    "completed": "completed_tasks",
    "idea": "ideas",
    "bug": "known_bugs",
}


def reconcile(
    existing: dict[str, Any] | None,
    extraction: dict[str, Any],
    project: str,
    display_name: str,
    source: Path,
) -> dict[str, Any]:
    memory = deepcopy(existing) if existing else empty_memory(project, display_name)
    memory["project"] = project
    memory["display_name"] = display_name

    for scalar in ("summary", "purpose"):
        new_value = str(extraction.get(scalar, "")).strip()
        old_value = str(memory.get(scalar, "")).strip()
        if new_value and (not new_value.startswith("[NEEDS_REVIEW]") or not old_value):
            memory[scalar] = new_value

    for field in FACT_FIELDS:
        memory[field] = _merge_items(memory.get(field, []), extraction.get(field, []))

    memory["decisions"] = _merge_decisions(memory.get("decisions", []), extraction.get("decisions", []))
    _apply_tasks(memory, extraction.get("tasks", []))

    old_instructions = memory.setdefault("agent_instructions", {})
    new_instructions = extraction.get("agent_instructions", {})
    for field in ("structure", "commands", "conventions", "rules", "do_not_change"):
        old_instructions[field] = _merge_items(old_instructions.get(field, []), new_instructions.get(field, []))

    _apply_explicit_technology_changes(memory, extraction.get("decisions", []))
    now = utc_now()
    if not memory.get("created_at"):
        memory["created_at"] = now
    memory["last_updated"] = now
    memory.setdefault("update_history", []).append({
        "date": now,
        "source": source.name,
        "mode": "update" if existing else "create",
    })
    return memory


def _merge_items(old: list[Any], new: list[Any]) -> list[Any]:
    result = deepcopy(old) if isinstance(old, list) else []
    known = {_normalize(_item_text(item)) for item in result}
    for item in new if isinstance(new, list) else []:
        text = _item_text(item)
        key = _normalize(text)
        if text and key not in known:
            result.append(deepcopy(item))
            known.add(key)
    return result


def _merge_decisions(old: list[Any], new: list[Any]) -> list[Any]:
    result = deepcopy(old) if isinstance(old, list) else []
    for raw in new if isinstance(new, list) else []:
        decision = deepcopy(raw) if isinstance(raw, dict) else {"title": str(raw)}
        title = _item_text(decision)
        if not title:
            continue
        duplicate = next((item for item in result if _similar(_item_text(item), title)), None)
        if duplicate is not None:
            if isinstance(duplicate, dict) and isinstance(decision, dict):
                for key, value in decision.items():
                    if value not in (None, "", []):
                        duplicate[key] = value
            continue

        previous = str(decision.get("previous", "")).strip() if isinstance(decision, dict) else ""
        if previous:
            for item in result:
                if isinstance(item, dict) and _similar(_item_text(item), previous):
                    item["status"] = "superseded"
        if isinstance(decision, dict):
            decision.setdefault("status", "active")
        result.append(decision)
    return result


def _apply_tasks(memory: dict[str, Any], tasks: list[Any]) -> None:
    for field in TASK_FIELD_BY_STATUS.values():
        if not isinstance(memory.get(field), list):
            memory[field] = []

    for raw in tasks if isinstance(tasks, list) else []:
        task = deepcopy(raw) if isinstance(raw, dict) else {"title": str(raw), "status": "todo"}
        title = _item_text(task)
        status = str(task.get("status", "todo")) if isinstance(task, dict) else "todo"
        destination = TASK_FIELD_BY_STATUS.get(status, "todo_tasks")
        if not title:
            continue

        for field in TASK_FIELD_BY_STATUS.values():
            if field == destination:
                continue
            memory[field] = [item for item in memory[field] if not _similar(_item_text(item), title)]

        existing = next((item for item in memory[destination] if _similar(_item_text(item), title)), None)
        if existing is None:
            memory[destination].append(task)
        elif isinstance(existing, dict) and isinstance(task, dict):
            existing.update({key: value for key, value in task.items() if value not in (None, "", [])})


def _apply_explicit_technology_changes(memory: dict[str, Any], decisions: list[Any]) -> None:
    technologies = memory.get("technologies", [])
    for decision in decisions if isinstance(decisions, list) else []:
        text = _item_text(decision)
        previous = str(decision.get("previous", "")) if isinstance(decision, dict) else ""
        matches = re.search(r"(?:с|from)\s+([\w.+#-]+)\s+(?:на|to)\s+([\w.+#-]+)", text, re.IGNORECASE)
        old_name = previous or (matches.group(1) if matches else "")
        new_name = matches.group(2) if matches else ""
        if old_name and new_name:
            technologies = [item for item in technologies if _normalize(_item_text(item)) != _normalize(old_name)]
            technologies = _merge_items(technologies, [{
                "text": new_name,
                "confidence": "HIGH",
                "source_blocks": decision.get("source_blocks", []) if isinstance(decision, dict) else [],
            }])
    memory["technologies"] = technologies


def _item_text(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        return str(item.get("text") or item.get("title") or "").strip()
    return ""


def _normalize(value: str) -> str:
    value = value.casefold().replace("ё", "е")
    value = re.sub(r"\b(готово|сделано|реализовано|добавить|добавлены|надо|нужно|todo|done|completed)\b", " ", value)
    return " ".join(re.findall(r"[\w+#.]+", value))


def _similar(left: str, right: str) -> bool:
    a, b = _normalize(left), _normalize(right)
    if not a or not b:
        return False
    if a == b:
        return True
    tokens_a, tokens_b = set(a.split()), set(b.split())
    overlap = len(tokens_a & tokens_b) / max(1, min(len(tokens_a), len(tokens_b)))
    return overlap >= 0.75 or SequenceMatcher(None, a, b).ratio() >= 0.72

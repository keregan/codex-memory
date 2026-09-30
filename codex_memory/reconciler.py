from __future__ import annotations

import re
from copy import deepcopy
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from .models import CONFIDENCE_LEVELS, TASK_STATUSES, empty_memory, stable_item_id, utc_now


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
    now = utc_now()
    source_name = source.name or "unknown"

    for scalar in ("summary", "purpose"):
        new_value = str(extraction.get(scalar, "")).strip()
        old_value = str(memory.get(scalar, "")).strip()
        if new_value and (not new_value.startswith("[NEEDS_REVIEW]") or not old_value):
            memory[scalar] = new_value

    for field in FACT_FIELDS:
        memory[field] = _merge_items(
            memory.get(field, []), extraction.get(field, []), field, source_name, now,
        )

    new_decisions = [
        _canonical_decision(item, source_name, now)
        for item in extraction.get("decisions", [])
        if _item_text(item)
    ]
    memory["decisions"] = _merge_decisions(memory.get("decisions", []), new_decisions)
    _apply_tasks(memory, extraction.get("tasks", []), source_name, now)

    old_instructions = memory.setdefault("agent_instructions", {})
    new_instructions = extraction.get("agent_instructions", {})
    for field in ("structure", "commands", "conventions", "rules", "do_not_change"):
        kind = f"agent_instructions.{field}"
        old_instructions[field] = _merge_items(
            old_instructions.get(field, []), new_instructions.get(field, []), kind, source_name, now,
        )

    _apply_explicit_technology_changes(memory, new_decisions, source_name, now)
    if not memory.get("created_at"):
        memory["created_at"] = now
    memory["last_updated"] = now
    memory.setdefault("update_history", []).append({
        "date": now,
        "source": source.name,
        "mode": "update" if existing else "create",
    })
    return memory


def _merge_items(
    old: list[Any],
    new: list[Any],
    kind: str,
    source: str,
    observed_at: str,
) -> list[Any]:
    result = deepcopy(old) if isinstance(old, list) else []
    known = {_normalize(_item_text(item)): item for item in result}
    for raw in new if isinstance(new, list) else []:
        item = _canonical_fact(raw, kind, source, observed_at)
        text = _item_text(item)
        key = _normalize(text)
        if not text:
            continue
        duplicate = known.get(key)
        if duplicate is None:
            result.append(item)
            known[key] = item
        elif isinstance(duplicate, dict):
            _merge_metadata(duplicate, item)
    return result


def _merge_decisions(old: list[Any], new: list[Any]) -> list[Any]:
    result = deepcopy(old) if isinstance(old, list) else []
    for raw in new if isinstance(new, list) else []:
        decision = deepcopy(raw)
        title = _item_text(decision)
        if not title:
            continue
        duplicate = next((item for item in result if _similar(_item_text(item), title)), None)
        if duplicate is not None:
            if isinstance(duplicate, dict) and isinstance(decision, dict):
                _merge_metadata(duplicate, decision)
                for key in ("reason", "date", "previous"):
                    value = decision.get(key)
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


def _apply_tasks(
    memory: dict[str, Any],
    tasks: list[Any],
    source: str,
    observed_at: str,
) -> None:
    for field in TASK_FIELD_BY_STATUS.values():
        if not isinstance(memory.get(field), list):
            memory[field] = []

    for raw in tasks if isinstance(tasks, list) else []:
        task = _canonical_task(raw, source, observed_at)
        title = _item_text(task)
        status = task["status"]
        destination = TASK_FIELD_BY_STATUS.get(status, "todo_tasks")
        if not title:
            continue

        matched = None
        for field in TASK_FIELD_BY_STATUS.values():
            kept = []
            for item in memory[field]:
                if _similar(_item_text(item), title):
                    if matched is None and isinstance(item, dict):
                        matched = item
                else:
                    kept.append(item)
            memory[field] = kept

        if matched is not None:
            _merge_metadata(matched, task)
            matched["title"] = task["title"]
            matched["status"] = status
            task = matched
        memory[destination].append(task)


def _apply_explicit_technology_changes(
    memory: dict[str, Any],
    decisions: list[Any],
    source: str,
    observed_at: str,
) -> None:
    technologies = memory.get("technologies", [])
    for decision in decisions if isinstance(decisions, list) else []:
        text = _item_text(decision)
        previous = str(decision.get("previous", "")) if isinstance(decision, dict) else ""
        matches = re.search(r"(?:с|from)\s+([\w.+#-]+)\s+(?:на|to)\s+([\w.+#-]+)", text, re.IGNORECASE)
        old_name = previous or (matches.group(1) if matches else "")
        new_name = matches.group(2) if matches else ""
        if old_name and new_name:
            for item in technologies:
                if isinstance(item, dict) and _normalize(_item_text(item)) == _normalize(old_name):
                    item["status"] = "superseded"
            technologies = _merge_items(technologies, [{
                "text": new_name,
                "confidence": "HIGH",
                "source_blocks": decision.get("source_blocks", []) if isinstance(decision, dict) else [],
            }], "technologies", source, observed_at)
    memory["technologies"] = technologies


def _canonical_fact(raw: Any, kind: str, source: str, observed_at: str) -> dict[str, Any]:
    item = raw if isinstance(raw, dict) else {"text": str(raw)}
    text = str(item.get("text") or item.get("title") or "").strip()
    blocks = _clean_blocks(item.get("source_blocks"))
    status = item.get("status")
    return {
        "id": stable_item_id(kind, text),
        "text": text,
        "status": status if status in {"active", "superseded", "disputed"} else "active",
        "confidence": _confidence(item.get("confidence")),
        "source_blocks": blocks,
        "evidence": [_evidence(source, blocks, observed_at)],
    }


def _canonical_task(raw: Any, source: str, observed_at: str) -> dict[str, Any]:
    item = raw if isinstance(raw, dict) else {"title": str(raw)}
    title = str(item.get("title") or item.get("text") or "").strip()
    blocks = _clean_blocks(item.get("source_blocks"))
    status = str(item.get("status", "todo")).lower()
    if status not in TASK_STATUSES:
        status = "todo"
    return {
        "id": stable_item_id("tasks", title),
        "title": title,
        "status": status,
        "confidence": _confidence(item.get("confidence")),
        "source_blocks": blocks,
        "evidence": [_evidence(source, blocks, observed_at)],
    }


def _canonical_decision(raw: Any, source: str, observed_at: str) -> dict[str, Any]:
    item = raw if isinstance(raw, dict) else {"title": str(raw)}
    title = str(item.get("title") or item.get("text") or "").strip()
    blocks = _clean_blocks(item.get("source_blocks"))
    status = item.get("status")
    return {
        "id": stable_item_id("decisions", title),
        "title": title,
        "reason": str(item.get("reason", "")).strip(),
        "date": str(item.get("date", "")).strip(),
        "previous": str(item.get("previous", "")).strip(),
        "status": status if status in {"active", "superseded"} else "active",
        "confidence": _confidence(item.get("confidence")),
        "source_blocks": blocks,
        "evidence": [_evidence(source, blocks, observed_at)],
    }


def _evidence(source: str, blocks: list[int], observed_at: str) -> dict[str, Any]:
    return {"source": source, "source_blocks": blocks, "observed_at": observed_at}


def _merge_metadata(existing: dict[str, Any], new: dict[str, Any]) -> None:
    existing["source_blocks"] = sorted(set([
        *existing.get("source_blocks", []), *new.get("source_blocks", []),
    ]))
    evidence = existing.setdefault("evidence", [])
    for entry in new.get("evidence", []):
        if entry not in evidence:
            evidence.append(deepcopy(entry))
    if _confidence_rank(new.get("confidence")) > _confidence_rank(existing.get("confidence")):
        existing["confidence"] = new["confidence"]


def _confidence(value: Any) -> str:
    confidence = str(value or "MEDIUM").upper()
    return confidence if confidence in CONFIDENCE_LEVELS else "MEDIUM"


def _confidence_rank(value: Any) -> int:
    return {"LOW": 0, "MEDIUM": 1, "HIGH": 2}.get(str(value), 1)


def _clean_blocks(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    return sorted(set(
        item for item in value
        if isinstance(item, int) and not isinstance(item, bool) and item > 0
    ))


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

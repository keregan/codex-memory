from __future__ import annotations

from typing import Any


def render_all(memory: dict[str, Any]) -> dict[str, str]:
    return {
        "PROJECT_CONTEXT.md": _render_context(memory),
        "DECISIONS.md": _render_decisions(memory),
        "TASKS.md": _render_tasks(memory),
        "AGENTS.md": _render_agents(memory),
    }


def _render_context(memory: dict[str, Any]) -> str:
    title = memory.get("display_name") or memory.get("project")
    parts = [f"# {title}\n"]
    parts.append(_scalar_section("Краткое описание", memory.get("summary")))
    parts.append(_scalar_section("Назначение", memory.get("purpose")))
    parts.append(_list_section("Технологии", memory.get("technologies", [])))
    parts.append(_list_section("Архитектура", memory.get("architecture", [])))
    parts.append(_list_section("Важные компоненты", memory.get("components", [])))
    parts.append(_list_section("Реализовано", memory.get("implemented", [])))
    parts.append(_list_section("Ограничения и проблемы", memory.get("constraints", [])))
    parts.append(_list_section("Открытые вопросы", memory.get("open_questions", [])))
    parts.append(f"## Обновление\n\nПоследнее обновление: {memory.get('last_updated', 'неизвестно')}\n")
    return "\n".join(parts).rstrip() + "\n"


def _render_decisions(memory: dict[str, Any]) -> str:
    lines = ["# Решения", ""]
    decisions = memory.get("decisions", [])
    if not decisions:
        return "# Решения\n\nПока нет зафиксированных решений.\n"
    for item in decisions:
        if isinstance(item, dict):
            title = _text(item)
            date = item.get("date") or "Дата не указана"
            status = item.get("status", "active")
            lines.extend([f"## {date} — {title}", ""])
            if item.get("reason"):
                lines.append(f"Причина: {item['reason']}")
            if item.get("previous"):
                lines.append(f"Предыдущее решение: {item['previous']}")
            if status == "superseded":
                lines.append("Статус: заменено более поздним решением")
            meta = _metadata(item)
            if meta:
                lines.append(meta)
            lines.append("")
        else:
            lines.extend([f"- {item}", ""])
    return "\n".join(lines).rstrip() + "\n"


def _render_tasks(memory: dict[str, Any]) -> str:
    sections = (
        ("Сейчас в работе", "current_tasks"),
        ("Осталось сделать", "todo_tasks"),
        ("Известные баги", "known_bugs"),
        ("Идеи на потом", "ideas"),
        ("Выполнено", "completed_tasks"),
    )
    parts = ["# Задачи\n"]
    for title, key in sections:
        parts.append(_list_section(title, memory.get(key, [])))
    return "\n".join(parts).rstrip() + "\n"


def _render_agents(memory: dict[str, Any]) -> str:
    instructions = memory.get("agent_instructions", {})
    parts = ["# Инструкции для AI coding-агента\n"]
    parts.append(_list_section("Структура проекта", instructions.get("structure", [])))
    parts.append(_list_section("Команды", instructions.get("commands", [])))
    parts.append(_list_section("Соглашения", instructions.get("conventions", [])))
    parts.append(_list_section("Архитектурные правила", instructions.get("rules", [])))
    parts.append(_list_section("Не менять без необходимости", instructions.get("do_not_change", [])))
    return "\n".join(parts).rstrip() + "\n"


def _scalar_section(title: str, value: Any) -> str:
    text = str(value or "").strip() or "[NEEDS_REVIEW] Информация пока не определена."
    return f"## {title}\n\n{text}\n"


def _list_section(title: str, items: list[Any]) -> str:
    lines = [f"## {title}", ""]
    if not items:
        lines.append("Пока нет данных.")
    else:
        for item in items:
            text = _text(item)
            metadata = _metadata(item) if isinstance(item, dict) else ""
            suffix = f" — {metadata}" if metadata else ""
            lines.append(f"- {text}{suffix}")
    lines.append("")
    return "\n".join(lines)


def _text(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("text") or item.get("title") or "[NEEDS_REVIEW]")
    return str(item)


def _metadata(item: dict[str, Any]) -> str:
    details = []
    status = item.get("status")
    if status in {"superseded", "disputed"}:
        details.append(f"status: {status}")
    confidence = item.get("confidence")
    if confidence in {"LOW", "MEDIUM"}:
        details.append(f"confidence: {confidence}")
    blocks = item.get("source_blocks")
    if blocks:
        details.append("источник: блоки " + ", ".join(str(value) for value in blocks))
    return "; ".join(details)

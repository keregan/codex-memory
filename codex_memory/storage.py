from __future__ import annotations

import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

from .migrations import migrate_memory_document
from .schema import validate_memory_document


def project_directory(memory_root: Path, project: str) -> Path:
    root = memory_root.resolve()
    target = (root / project).resolve()
    if root != target and root not in target.parents:
        raise ValueError(f"Project path escapes memory directory: {project}")
    return target


def load_memory(project_dir: Path, expected_project: str | None = None) -> dict[str, Any] | None:
    path = project_dir / "memory.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read existing memory file {path}: {exc}") from exc
    data, _ = migrate_memory_document(data)
    if expected_project is not None and data.get("project") != expected_project:
        raise ValueError(
            f"Memory project mismatch in {path}: expected {expected_project!r}, got {data.get('project')!r}"
        )
    if not isinstance(data.get("agent_instructions", {}), dict):
        raise ValueError(f"Invalid agent_instructions object in {path}")
    return data


def write_project(project_dir: Path, memory: dict[str, Any], markdown_files: dict[str, str]) -> None:
    validate_memory_document(memory)
    project_dir.parent.mkdir(parents=True, exist_ok=True)
    files = {"memory.json": json.dumps(memory, ensure_ascii=False, indent=2) + "\n", **markdown_files}
    staging = project_dir.parent / f".{project_dir.name}.staging-{uuid.uuid4().hex}"
    staging.mkdir()
    try:
        if project_dir.exists():
            if not project_dir.is_dir():
                raise ValueError(f"Project memory path is not a directory: {project_dir}")
            shutil.copytree(project_dir, staging, dirs_exist_ok=True, symlinks=True)
        for name, content in files.items():
            if Path(name).name != name:
                raise ValueError(f"Invalid output filename: {name}")
            _write_complete(staging / name, content)
        _replace_directory(project_dir, staging)
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def _write_complete(path: Path, content: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())


def _replace_directory(project_dir: Path, staging: Path) -> None:
    if not project_dir.exists():
        os.replace(staging, project_dir)
        return

    backup = project_dir.parent / f".{project_dir.name}.backup-{uuid.uuid4().hex}"
    os.replace(project_dir, backup)
    try:
        os.replace(staging, project_dir)
    except BaseException:
        os.replace(backup, project_dir)
        raise
    else:
        shutil.rmtree(backup)

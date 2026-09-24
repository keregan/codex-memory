from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .models import SCHEMA_VERSION


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
    if not isinstance(data, dict):
        raise ValueError(f"Existing memory must be a JSON object: {path}")
    version = data.get("schema_version")
    if version != SCHEMA_VERSION:
        raise ValueError(f"Unsupported memory schema version {version!r}; expected {SCHEMA_VERSION}")
    if expected_project is not None and data.get("project") != expected_project:
        raise ValueError(
            f"Memory project mismatch in {path}: expected {expected_project!r}, got {data.get('project')!r}"
        )
    if not isinstance(data.get("agent_instructions", {}), dict):
        raise ValueError(f"Invalid agent_instructions object in {path}")
    return data


def write_project(project_dir: Path, memory: dict[str, Any], markdown_files: dict[str, str]) -> None:
    project_dir.mkdir(parents=True, exist_ok=True)
    files = {"memory.json": json.dumps(memory, ensure_ascii=False, indent=2) + "\n", **markdown_files}
    temporary_files: list[tuple[Path, Path]] = []
    try:
        for name, content in files.items():
            if Path(name).name != name:
                raise ValueError(f"Invalid output filename: {name}")
            path = project_dir / name
            temporary_files.append((path, _write_temporary(path, content)))
        for path, temporary in temporary_files:
            os.replace(temporary, path)
    finally:
        for _, temporary in temporary_files:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


def _write_temporary(path: Path, content: str) -> Path:
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        return Path(temp_name)
    except BaseException:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise

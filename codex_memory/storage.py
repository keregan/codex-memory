from __future__ import annotations

import json
import os
import shutil
import stat
from contextlib import contextmanager
from pathlib import Path
from typing import Any, BinaryIO, Iterator

from .migrations import migrate_memory_document
from .schema import validate_memory_document


_NO_PRECONDITION = object()


def project_directory(memory_root: Path, project: str) -> Path:
    root = memory_root.resolve()
    target = (root / project).resolve()
    if root != target and root not in target.parents:
        raise ValueError(f"Project path escapes memory directory: {project}")
    return target


def load_memory(project_dir: Path, expected_project: str | None = None) -> dict[str, Any] | None:
    if not project_dir.parent.exists():
        return None
    with _project_lock(project_dir):
        _recover_transaction(project_dir)
        return _load_memory_unlocked(project_dir, expected_project)


def _load_memory_unlocked(
    project_dir: Path,
    expected_project: str | None = None,
) -> dict[str, Any] | None:
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


def write_project(
    project_dir: Path,
    memory: dict[str, Any],
    markdown_files: dict[str, str],
    *,
    expected_current: dict[str, Any] | None | object = _NO_PRECONDITION,
) -> None:
    validate_memory_document(memory)
    project_dir.parent.mkdir(parents=True, exist_ok=True)
    files = {"memory.json": json.dumps(memory, ensure_ascii=False, indent=2) + "\n", **markdown_files}
    with _project_lock(project_dir):
        _recover_transaction(project_dir)
        if expected_current is not _NO_PRECONDITION:
            current = _load_memory_unlocked(project_dir)
            if current != expected_current:
                raise RuntimeError(
                    f"Project memory changed after it was read; retry the update: {project_dir}"
                )
        staging, _, _, _ = _transaction_paths(project_dir)
        staging.mkdir()
        try:
            if project_dir.exists():
                _reject_links_or_reparse_points(project_dir)
                if not project_dir.is_dir():
                    raise ValueError(f"Project memory path is not a directory: {project_dir}")
                shutil.copytree(project_dir, staging, dirs_exist_ok=True, symlinks=True)
            for name, content in files.items():
                if Path(name).name != name:
                    raise ValueError(f"Invalid output filename: {name}")
                output_path = staging / name
                if output_path.exists() and _is_link_or_reparse_point(output_path):
                    raise ValueError(f"Refusing to write through a link or reparse point: {output_path}")
                _write_complete(output_path, content)
            _replace_directory(project_dir, staging)
        finally:
            if staging.exists():
                shutil.rmtree(staging)


def _write_complete(path: Path, content: str) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())


@contextmanager
def _project_lock(project_dir: Path) -> Iterator[None]:
    lock_path = project_dir.parent / f".{project_dir.name}.lock"
    handle = _open_lock_file(lock_path)
    acquired = False
    try:
        acquired = _try_lock(handle)
        if not acquired:
            raise RuntimeError(f"Project memory is locked by another process: {project_dir}") from None
        yield
    finally:
        try:
            if acquired:
                _unlock(handle)
        finally:
            handle.close()


def _open_lock_file(lock_path: Path) -> BinaryIO:
    if _is_link_or_reparse_point(lock_path):
        raise ValueError(f"Project lock path must not be a link or reparse point: {lock_path}")
    flags = os.O_RDWR | os.O_CREAT
    flags |= getattr(os, "O_BINARY", 0) | getattr(os, "O_NOINHERIT", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(lock_path, flags, 0o600)
    try:
        if _is_link_or_reparse_point(lock_path):
            raise ValueError(f"Project lock path must not be a link or reparse point: {lock_path}")
        return os.fdopen(descriptor, "r+b", buffering=0)
    except BaseException:
        os.close(descriptor)
        raise


def _try_lock(handle: BinaryIO) -> bool:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True

    import fcntl

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _unlock(handle: BinaryIO) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _reject_links_or_reparse_points(root: Path) -> None:
    """Reject links before copying an existing project into writable staging."""
    if _is_link_or_reparse_point(root):
        raise ValueError(f"Project memory path must not be a link or reparse point: {root}")

    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            entries = list(os.scandir(directory))
        except OSError as exc:
            raise ValueError(f"Cannot safely inspect project memory directory {directory}: {exc}") from exc
        for entry in entries:
            path = Path(entry.path)
            if _is_link_or_reparse_point(path):
                raise ValueError(f"Links and reparse points are not allowed in project memory: {path}")
            if entry.is_dir(follow_symlinks=False):
                pending.append(path)


def _is_link_or_reparse_point(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    if stat.S_ISLNK(metadata.st_mode):
        return True
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(getattr(metadata, "st_file_attributes", 0) & reparse_flag)


def _transaction_paths(project_dir: Path) -> tuple[Path, Path, Path, Path]:
    prefix = project_dir.parent / f".{project_dir.name}"
    return (
        prefix.with_name(prefix.name + ".staging"),
        prefix.with_name(prefix.name + ".backup"),
        prefix.with_name(prefix.name + ".transaction.json"),
        prefix.with_name(prefix.name + ".transaction.json.tmp"),
    )


def _write_transaction_phase(journal: Path, temporary: Path, phase: str) -> None:
    payload = json.dumps({"version": 1, "phase": phase}, sort_keys=True) + "\n"
    _write_complete(temporary, payload)
    os.replace(temporary, journal)
    _sync_directory(journal.parent)


def _sync_directory(directory: Path) -> None:
    if os.name == "nt":
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(directory, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _read_transaction_phase(journal: Path) -> str:
    try:
        data = json.loads(journal.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Cannot recover transaction journal {journal}: {exc}") from exc
    phase = data.get("phase") if isinstance(data, dict) and data.get("version") == 1 else None
    if phase not in {"prepared", "backup_created", "activated"}:
        raise RuntimeError(f"Cannot recover transaction journal with invalid state: {journal}")
    return phase


def _recover_transaction(project_dir: Path) -> None:
    staging, backup, journal, temporary = _transaction_paths(project_dir)
    for artifact in (staging, backup, journal, temporary):
        if _is_link_or_reparse_point(artifact):
            raise ValueError(f"Transaction artifact must not be a link or reparse point: {artifact}")
    if temporary.exists():
        temporary.unlink()

    if not journal.exists():
        if backup.exists():
            if project_dir.exists():
                shutil.rmtree(backup)
            else:
                os.replace(backup, project_dir)
                _sync_directory(project_dir.parent)
        if staging.exists():
            shutil.rmtree(staging)
        return

    phase = _read_transaction_phase(journal)
    activation_completed = project_dir.exists() and backup.exists() and not staging.exists()
    if phase == "activated" or activation_completed:
        if not project_dir.exists():
            raise RuntimeError(f"Activated project directory is missing: {project_dir}")
        if backup.exists():
            shutil.rmtree(backup)
        if staging.exists():
            shutil.rmtree(staging)
    else:
        if project_dir.exists() and backup.exists():
            raise RuntimeError(f"Ambiguous interrupted transaction for {project_dir}")
        if backup.exists():
            os.replace(backup, project_dir)
            _sync_directory(project_dir.parent)
        if staging.exists():
            shutil.rmtree(staging)
    journal.unlink()
    _sync_directory(project_dir.parent)


def _replace_directory(project_dir: Path, staging: Path) -> None:
    _, backup, journal, temporary = _transaction_paths(project_dir)
    _write_transaction_phase(journal, temporary, "prepared")
    if not project_dir.exists():
        os.replace(staging, project_dir)
        _sync_directory(project_dir.parent)
        _write_transaction_phase(journal, temporary, "activated")
        journal.unlink()
        _sync_directory(project_dir.parent)
        return

    os.replace(project_dir, backup)
    _sync_directory(project_dir.parent)
    try:
        _write_transaction_phase(journal, temporary, "backup_created")
        os.replace(staging, project_dir)
        _sync_directory(project_dir.parent)
    except BaseException:
        if backup.exists() and not project_dir.exists():
            os.replace(backup, project_dir)
            _sync_directory(project_dir.parent)
            journal.unlink(missing_ok=True)
            temporary.unlink(missing_ok=True)
        raise

    _write_transaction_phase(journal, temporary, "activated")
    shutil.rmtree(backup)
    journal.unlink()
    _sync_directory(project_dir.parent)

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .analyzer import LLMAnalyzer, RuleBasedAnalyzer
from .chunking import DEFAULT_CHUNK_CHARS, MIN_CHUNK_CHARS
from .clipboard import read_clipboard_text
from .history_reader import parse_history, read_history
from .llm import (
    DEFAULT_LLM_RETRIES,
    DEFAULT_LLM_TIMEOUT,
    DEFAULT_MAX_RESPONSE_BYTES,
    ChatCompletionsClient,
)
from .markdown_renderer import render_all
from .models import ProjectCandidate
from .project_names import safe_project_name
from .reconciler import reconcile
from .schema import validate_memory_document
from .storage import load_memory, project_directory, write_project


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Turn a mixed chat history into project-oriented Markdown and JSON memory.",
    )
    parser.add_argument("history", nargs="?", type=Path, help="UTF-8 or CP1251 text history (read-only)")
    parser.add_argument(
        "--clipboard", action="store_true",
        help="Read history directly from the Windows clipboard instead of a file",
    )
    parser.add_argument("--update", action="store_true", help="Merge new facts into existing memory")
    parser.add_argument("--memory-dir", type=Path, default=Path("memory"), help="Output directory")
    parser.add_argument("--projects", help="Comma-separated project names; skips automatic detection")
    parser.add_argument("--yes", action="store_true", help="Accept detected projects without prompting")
    parser.add_argument(
        "--provider", choices=("rules", "llm"), default="rules",
        help="Local conservative rules (default), or an explicitly configured LLM endpoint",
    )
    parser.add_argument(
        "--api-url", default=os.environ.get("CODEX_MEMORY_API_URL", ""),
        help="Chat Completions URL; env: CODEX_MEMORY_API_URL",
    )
    parser.add_argument(
        "--api-key", default=os.environ.get("CODEX_MEMORY_API_KEY", ""),
        help="API key; env: CODEX_MEMORY_API_KEY",
    )
    parser.add_argument(
        "--model", default=os.environ.get("CODEX_MEMORY_MODEL", ""),
        help="Model name; env: CODEX_MEMORY_MODEL",
    )
    parser.add_argument(
        "--chunk-chars", type=int, default=DEFAULT_CHUNK_CHARS,
        help=f"Maximum approximate characters per LLM request (minimum {MIN_CHUNK_CHARS})",
    )
    parser.add_argument(
        "--llm-timeout", type=int, default=DEFAULT_LLM_TIMEOUT,
        help="Timeout in seconds for each LLM request",
    )
    parser.add_argument(
        "--llm-retries", type=int, default=DEFAULT_LLM_RETRIES,
        help="Retries for temporary LLM API failures (0-10)",
    )
    parser.add_argument(
        "--llm-max-response-bytes", type=int, default=DEFAULT_MAX_RESPONSE_BYTES,
        help="Maximum accepted LLM API response size in bytes",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_console_output()
    args = build_parser().parse_args(argv)
    try:
        if args.clipboard and args.history:
            raise ValueError("Specify either a history file or --clipboard, not both")
        if args.clipboard:
            messages = parse_history(read_clipboard_text())
            history_path = Path("clipboard")
        elif args.history:
            history_path = args.history.resolve()
            messages = read_history(history_path)
        else:
            raise ValueError("Specify a history file or use --clipboard")
        if not messages:
            raise ValueError("History file is empty")
        analyzer = _make_analyzer(args)

        if args.projects:
            candidates = _candidates_from_names(args.projects)
        else:
            print(f"Прочитано блоков истории: {len(messages)}")
            candidates = analyzer.detect_projects(messages)
            if not candidates and args.update:
                candidates = _single_existing_candidate(args.memory_dir)

        candidates = _confirm_projects(candidates, args.yes)
        if not candidates:
            print("Проекты не выбраны; файлы не создавались.")
            return 1

        prepared = []
        for candidate in candidates:
            target = project_directory(args.memory_dir, candidate.name)
            existing = load_memory(target, expected_project=candidate.name)
            if args.update and existing is None:
                print(f"  {candidate.name}: существующая память не найдена, будет создана новая")
            if not args.update and existing is not None:
                raise FileExistsError(
                    f"Memory already exists for '{candidate.name}'. Use --update to change it."
                )

            extraction = analyzer.extract(candidate, messages)
            memory = reconcile(
                existing if args.update else None,
                extraction,
                candidate.name,
                candidate.display_name,
                history_path,
            )
            memory["aliases"] = sorted(set([*memory.get("aliases", []), *candidate.aliases]))
            validate_memory_document(memory)
            prepared.append((candidate, target, existing, memory, render_all(memory)))

        # Analyze and validate every project before changing any output files.
        print("\nСоздание памяти:")
        succeeded = []
        failed = []
        for candidate, target, existing, memory, markdown_files in prepared:
            try:
                write_project(target, memory, markdown_files, expected_current=existing)
            except (FileNotFoundError, FileExistsError, ValueError, RuntimeError, OSError) as exc:
                failed.append((candidate.name, exc))
                print(f"  ERROR {candidate.name}: {exc}", file=sys.stderr)
            else:
                succeeded.append(candidate.name)
                print(f"  OK {candidate.name}: {target}")

        if failed:
            print(
                f"\nЗапись завершена частично: успешно {len(succeeded)}, ошибок {len(failed)}. "
                "Успешные проекты уже сохранены; повторите запуск для проектов с ошибками.",
                file=sys.stderr,
            )
            return 2

        if args.clipboard:
            print("\nГотово. Текст из буфера обмена не сохранялся как исходный файл.")
        else:
            print("\nГотово. Исходный файл истории не изменялся.")
        if args.provider == "rules":
            print("Эвристический режим консервативен: проверьте элементы MEDIUM/LOW и [NEEDS_REVIEW].")
        return 0
    except KeyboardInterrupt:
        print("\nОперация отменена пользователем.", file=sys.stderr)
        return 130
    except (FileNotFoundError, FileExistsError, ValueError, RuntimeError, OSError) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 2


def _make_analyzer(args: argparse.Namespace):
    if args.chunk_chars < MIN_CHUNK_CHARS:
        raise ValueError(f"--chunk-chars must be at least {MIN_CHUNK_CHARS}")
    if args.provider == "rules":
        return RuleBasedAnalyzer()
    if not args.api_url or not args.model:
        raise ValueError("--provider llm requires --api-url and --model (or matching environment variables)")
    print("Внимание: история будет отправлена на явно настроенный LLM API.")
    return LLMAnalyzer(
        ChatCompletionsClient(
            args.api_url,
            args.model,
            args.api_key,
            timeout=args.llm_timeout,
            max_response_bytes=args.llm_max_response_bytes,
            retries=args.llm_retries,
        ),
        chunk_chars=args.chunk_chars,
    )


def _candidates_from_names(value: str) -> list[ProjectCandidate]:
    result = []
    seen = set()
    for raw in value.split(","):
        raw = raw.strip()
        if not raw:
            continue
        name = safe_project_name(raw)
        if name not in seen:
            result.append(ProjectCandidate(name=name, display_name=raw.replace("_", " ").title(), confidence="HIGH"))
            seen.add(name)
    return result


def _confirm_projects(candidates: list[ProjectCandidate], assume_yes: bool) -> list[ProjectCandidate]:
    if candidates:
        print("\nОбнаружены проекты:")
        for index, candidate in enumerate(candidates, start=1):
            print(f"  {index}. {candidate.name} ({candidate.confidence})")
    else:
        print("\nАвтоматически определить проекты не удалось.")

    if assume_yes:
        if not candidates:
            raise ValueError("No projects detected. Pass --projects when using --yes.")
        return candidates

    print("Нажмите Enter для подтверждения или введите итоговые имена через запятую.")
    answer = input("Проекты: ").strip()
    return _candidates_from_names(answer) if answer else candidates


def _single_existing_candidate(memory_dir: Path) -> list[ProjectCandidate]:
    if not memory_dir.is_dir():
        return []
    existing = [path for path in memory_dir.iterdir() if path.is_dir() and (path / "memory.json").is_file()]
    if len(existing) != 1:
        return []
    name = safe_project_name(existing[0].name)
    return [ProjectCandidate(name=name, display_name=name.replace("_", " ").title(), confidence="LOW")]


def _configure_console_output() -> None:
    """Prevent localized CLI messages from crashing on restrictive Windows code pages."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(errors="backslashreplace")
            except (OSError, ValueError):
                pass

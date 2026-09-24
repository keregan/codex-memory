import shutil
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from codex_memory.cli import main
from codex_memory.models import ProjectCandidate


class CliTests(unittest.TestCase):
    def test_create_then_update_without_changing_sources(self):
        directory = Path(".test_work") / uuid.uuid4().hex
        directory.mkdir(parents=True)
        try:
            first = directory / "history.txt"
            second = directory / "history_new.txt"
            first_content = "User: В telegram_bot используется SQLite. Нужно добавить тесты."
            second_content = "User: В telegram_bot решили перейти с SQLite на PostgreSQL. Тесты добавлены."
            first.write_text(first_content, encoding="utf-8")
            second.write_text(second_content, encoding="utf-8")
            memory_root = directory / "memory"

            result = main([
                str(first), "--projects", "telegram_bot", "--yes",
                "--memory-dir", str(memory_root),
            ])
            updated = main([
                str(second), "--projects", "telegram_bot", "--yes", "--update",
                "--memory-dir", str(memory_root),
            ])

            self.assertEqual(result, 0)
            self.assertEqual(updated, 0)
            self.assertEqual(first.read_text(encoding="utf-8"), first_content)
            self.assertEqual(second.read_text(encoding="utf-8"), second_content)
            output = memory_root / "telegram_bot"
            self.assertTrue((output / "memory.json").is_file())
            self.assertIn("PostgreSQL", (output / "PROJECT_CONTEXT.md").read_text(encoding="utf-8"))
            self.assertIn("Выполнено", (output / "TASKS.md").read_text(encoding="utf-8"))
        finally:
            shutil.rmtree(directory)

    def test_refuses_to_overwrite_without_update(self):
        directory = Path(".test_work") / uuid.uuid4().hex
        directory.mkdir(parents=True)
        try:
            source = directory / "history.txt"
            source.write_text("telegram_bot uses Python", encoding="utf-8")
            args = [str(source), "--projects", "telegram_bot", "--yes", "--memory-dir", str(directory / "memory")]

            self.assertEqual(main(args), 0)
            self.assertEqual(main(args), 2)
        finally:
            shutil.rmtree(directory)

    def test_analysis_failure_does_not_write_first_project(self):
        class FailingAnalyzer:
            def detect_projects(self, messages):
                return []

            def extract(self, project, messages):
                if project.name == "second_project":
                    raise RuntimeError("simulated failure")
                return {
                    "summary": "First", "purpose": "", "technologies": [],
                    "architecture": [], "components": [], "implemented": [],
                    "constraints": [], "decisions": [], "tasks": [],
                    "open_questions": [], "agent_instructions": {},
                }

        directory = Path(".test_work") / uuid.uuid4().hex
        directory.mkdir(parents=True)
        try:
            source = directory / "history.txt"
            source.write_text("mixed history", encoding="utf-8")
            memory_root = directory / "memory"
            with patch("codex_memory.cli._make_analyzer", return_value=FailingAnalyzer()):
                result = main([
                    str(source), "--projects", "first_project,second_project", "--yes",
                    "--memory-dir", str(memory_root),
                ])

            self.assertEqual(result, 2)
            self.assertFalse((memory_root / "first_project").exists())
        finally:
            shutil.rmtree(directory)


if __name__ == "__main__":
    unittest.main()

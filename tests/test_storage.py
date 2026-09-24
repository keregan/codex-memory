import json
import shutil
import unittest
import uuid
from pathlib import Path

from codex_memory.markdown_renderer import render_all
from codex_memory.models import empty_memory
from codex_memory.storage import load_memory, project_directory, write_project


class StorageTests(unittest.TestCase):
    def test_round_trip(self):
        directory = Path(".test_work") / uuid.uuid4().hex
        directory.mkdir(parents=True)
        try:
            target = project_directory(directory, "telegram_bot")
            memory = empty_memory("telegram_bot")
            write_project(target, memory, render_all(memory))

            self.assertEqual(load_memory(target)["project"], "telegram_bot")
            self.assertTrue((target / "PROJECT_CONTEXT.md").is_file())
            json.loads((target / "memory.json").read_text(encoding="utf-8"))
        finally:
            shutil.rmtree(directory)

    def test_rejects_path_escape(self):
        directory = Path(".test_work") / uuid.uuid4().hex
        directory.mkdir(parents=True)
        try:
            with self.assertRaises(ValueError):
                project_directory(directory, "../outside")
        finally:
            shutil.rmtree(directory)

    def test_rejects_project_mismatch(self):
        directory = Path(".test_work") / uuid.uuid4().hex
        directory.mkdir(parents=True)
        try:
            target = project_directory(directory, "telegram_bot")
            memory = empty_memory("other_project")
            write_project(target, memory, render_all(memory))

            with self.assertRaises(ValueError):
                load_memory(target, expected_project="telegram_bot")
        finally:
            shutil.rmtree(directory)

    def test_invalid_output_filename_changes_nothing(self):
        directory = Path(".test_work") / uuid.uuid4().hex
        directory.mkdir(parents=True)
        try:
            target = project_directory(directory, "telegram_bot")
            with self.assertRaises(ValueError):
                write_project(target, empty_memory("telegram_bot"), {"../escape.md": "bad"})

            self.assertFalse((target / "memory.json").exists())
            self.assertFalse((directory / "escape.md").exists())
        finally:
            shutil.rmtree(directory)


if __name__ == "__main__":
    unittest.main()

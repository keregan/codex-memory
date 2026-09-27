import json
import shutil
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from codex_memory.markdown_renderer import render_all
from codex_memory.models import empty_memory
from codex_memory.storage import load_memory, project_directory, write_project
import codex_memory.storage as storage_module


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

    def test_transaction_preserves_unmanaged_files(self):
        directory = Path(".test_work") / uuid.uuid4().hex
        directory.mkdir(parents=True)
        try:
            target = project_directory(directory, "telegram_bot")
            first = empty_memory("telegram_bot")
            write_project(target, first, render_all(first))
            (target / "NOTES.md").write_text("keep me", encoding="utf-8")
            updated = empty_memory("telegram_bot")
            updated["summary"] = "Updated"

            write_project(target, updated, render_all(updated))

            self.assertEqual((target / "NOTES.md").read_text(encoding="utf-8"), "keep me")
            self.assertEqual(load_memory(target)["summary"], "Updated")
            self.assertEqual(list(directory.glob(".telegram_bot.*")), [])
        finally:
            shutil.rmtree(directory)

    def test_rejects_symlink_without_writing_outside_project(self):
        directory = Path(".test_work") / uuid.uuid4().hex
        directory.mkdir(parents=True)
        try:
            target = project_directory(directory, "telegram_bot")
            original = empty_memory("telegram_bot")
            original["summary"] = "Original"
            write_project(target, original, render_all(original))

            external = directory / "outside.md"
            external.write_text("do not overwrite", encoding="utf-8")
            managed_file = target / "PROJECT_CONTEXT.md"
            managed_file.unlink()
            try:
                managed_file.symlink_to(external.resolve())
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"Symbolic links are not available: {exc}")

            updated = empty_memory("telegram_bot")
            updated["summary"] = "Updated"
            with self.assertRaisesRegex(ValueError, "Links and reparse points"):
                write_project(target, updated, render_all(updated))

            self.assertEqual(external.read_text(encoding="utf-8"), "do not overwrite")
            self.assertEqual(load_memory(target)["summary"], "Original")
            self.assertEqual(list(directory.glob(".telegram_bot.*")), [])
        finally:
            shutil.rmtree(directory)

    def test_transaction_rolls_back_when_directory_swap_fails(self):
        directory = Path(".test_work") / uuid.uuid4().hex
        directory.mkdir(parents=True)
        try:
            target = project_directory(directory, "telegram_bot")
            first = empty_memory("telegram_bot")
            first["summary"] = "Original"
            write_project(target, first, render_all(first))
            updated = empty_memory("telegram_bot")
            updated["summary"] = "Should not persist"
            real_replace = storage_module.os.replace
            calls = 0

            def fail_second_replace(source, destination):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("simulated swap failure")
                return real_replace(source, destination)

            with patch("codex_memory.storage.os.replace", side_effect=fail_second_replace):
                with self.assertRaises(OSError):
                    write_project(target, updated, render_all(updated))

            self.assertEqual(load_memory(target)["summary"], "Original")
            self.assertEqual(list(directory.glob(".telegram_bot.*")), [])
        finally:
            shutil.rmtree(directory)

    def test_load_migrates_v1_document(self):
        directory = Path(".test_work") / uuid.uuid4().hex
        directory.mkdir(parents=True)
        try:
            target = project_directory(directory, "telegram_bot")
            target.mkdir()
            old = empty_memory("telegram_bot")
            old["schema_version"] = 1
            old.pop("created_at")
            old["last_updated"] = "2026-01-01T00:00:00+00:00"
            (target / "memory.json").write_text(json.dumps(old), encoding="utf-8")

            migrated = load_memory(target, expected_project="telegram_bot")

            self.assertEqual(migrated["schema_version"], 2)
            self.assertEqual(migrated["created_at"], old["last_updated"])
            self.assertEqual(json.loads((target / "memory.json").read_text())["schema_version"], 1)
        finally:
            shutil.rmtree(directory)


if __name__ == "__main__":
    unittest.main()

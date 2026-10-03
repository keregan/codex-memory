import json
import shutil
import unittest
import uuid
from pathlib import Path

from codex_memory.history_reader import parse_history, read_history


class HistoryReaderTests(unittest.TestCase):
    def test_parses_history_text_without_a_file(self):
        messages = parse_history("User: Проект telegram_bot\n\nAssistant: Принято")

        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0].role, "user")
        self.assertEqual(messages[1].role, "assistant")

    def test_reads_roles_dates_and_preserves_source(self):
        directory = Path(".test_work") / uuid.uuid4().hex
        directory.mkdir(parents=True)
        try:
            path = directory / "history.txt"
            content = "2026-09-24 User: Создаём telegram_bot.\n\nAssistant: Хорошо."
            path.write_text(content, encoding="utf-8")

            messages = read_history(path)

            self.assertEqual(path.read_text(encoding="utf-8"), content)
            self.assertEqual(len(messages), 2)
            self.assertEqual(messages[0].date, "2026-09-24")
            self.assertEqual(messages[0].role, "user")
            self.assertEqual(messages[1].role, "assistant")
        finally:
            shutil.rmtree(directory)

    def test_preserves_multi_paragraph_markdown_messages(self):
        raw = "## Пользователь\n\nПервый абзац.\n\nВторой абзац.\n\n## Codex\n\nОтвет."

        messages = parse_history(raw)

        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0].role, "user")
        self.assertEqual(messages[0].text, "Первый абзац.\n\nВторой абзац.")
        self.assertEqual(messages[1].role, "assistant")

    def test_reads_json_messages_and_content_parts(self):
        directory = self._make_directory()
        try:
            path = directory / "history.json"
            data = {
                "messages": [
                    {"role": "human", "content": "Вопрос", "timestamp": "2026-10-03"},
                    {
                        "author": {"role": "assistant"},
                        "content": {"parts": ["Часть 1", "Часть 2"]},
                    },
                ]
            }
            original = json.dumps(data, ensure_ascii=False)
            path.write_text(original, encoding="utf-8")

            messages = read_history(path)

            self.assertEqual(path.read_text(encoding="utf-8"), original)
            self.assertEqual([message.role for message in messages], ["user", "assistant"])
            self.assertEqual(messages[0].date, "2026-10-03")
            self.assertEqual(messages[1].text, "Часть 1\n\nЧасть 2")
        finally:
            shutil.rmtree(directory)

    def test_reads_only_active_branch_from_tree_export(self):
        directory = self._make_directory()
        try:
            path = directory / "conversation.json"
            data = {
                "current_node": "answer",
                "mapping": {
                    "root": {"parent": None, "message": None},
                    "question": {
                        "parent": "root",
                        "message": {
                            "author": {"role": "user"},
                            "content": {"parts": ["Основной вопрос"]},
                            "create_time": 1_700_000_000,
                        },
                    },
                    "unused": {
                        "parent": "question",
                        "message": {
                            "author": {"role": "assistant"},
                            "content": {"parts": ["Старая ветка"]},
                        },
                    },
                    "answer": {
                        "parent": "question",
                        "message": {
                            "author": {"role": "assistant"},
                            "content": {"parts": ["Активный ответ"]},
                        },
                    },
                },
            }
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

            messages = read_history(path)

            self.assertEqual([message.text for message in messages], ["Основной вопрос", "Активный ответ"])
            self.assertEqual(messages[0].date, "2023-11-14T22:13:20+00:00")
        finally:
            shutil.rmtree(directory)

    def test_reads_json_lines(self):
        directory = self._make_directory()
        try:
            path = directory / "history.jsonl"
            path.write_text(
                '{"role":"user","content":"Один"}\n'
                '{"role":"assistant","content":"Два"}\n',
                encoding="utf-8",
            )

            messages = read_history(path)

            self.assertEqual([message.text for message in messages], ["Один", "Два"])
            self.assertEqual([message.number for message in messages], [1, 2])
        finally:
            shutil.rmtree(directory)

    def test_reads_chat_messages_sender_format(self):
        raw = json.dumps({
            "chat_messages": [
                {"sender": "human", "text": "Запрос"},
                {"sender": "assistant", "text": "Ответ", "created_at": "2026-10-03T12:00:00Z"},
            ]
        })

        messages = parse_history(raw)

        self.assertEqual([message.role for message in messages], ["user", "assistant"])
        self.assertEqual(messages[1].date, "2026-10-03T12:00:00Z")

    def test_rejects_invalid_json_without_changing_source(self):
        directory = self._make_directory()
        try:
            path = directory / "history.json"
            original = '{"messages": ['
            path.write_text(original, encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Invalid JSON history file"):
                read_history(path)

            self.assertEqual(path.read_text(encoding="utf-8"), original)
        finally:
            shutil.rmtree(directory)

    @staticmethod
    def _make_directory() -> Path:
        directory = Path(".test_work") / uuid.uuid4().hex
        directory.mkdir(parents=True)
        return directory


if __name__ == "__main__":
    unittest.main()

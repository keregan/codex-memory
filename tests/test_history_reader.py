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


if __name__ == "__main__":
    unittest.main()

import unittest

from codex_memory.analyzer import RuleBasedAnalyzer
from codex_memory.models import Message, ProjectCandidate


class RuleBasedAnalyzerTests(unittest.TestCase):
    def test_detects_projects_and_ignores_schema_names(self):
        messages = [
            Message(1, "Обсуждаем telegram_bot и memory_json."),
            Message(2, "В telegram_bot добавим тесты."),
            Message(3, "Также есть personal_site."),
        ]

        projects = RuleBasedAnalyzer().detect_projects(messages)
        names = [project.name for project in projects]

        self.assertEqual(names, ["telegram_bot", "personal_site"])
        self.assertEqual(projects[0].confidence, "HIGH")

    def test_extracts_decision_tasks_and_question(self):
        messages = [Message(
            1,
            "telegram_bot использует SQLite. Решили перейти с SQLite на PostgreSQL.\n"
            "Нужно добавить тесты.\nSQLite или PostgreSQL?",
        )]
        project = ProjectCandidate("telegram_bot", "Telegram Bot", message_numbers=[1])

        result = RuleBasedAnalyzer().extract(project, messages)

        self.assertIn("SQLite", [item["text"] for item in result["technologies"]])
        self.assertIn("PostgreSQL", [item["text"] for item in result["technologies"]])
        self.assertEqual(result["tasks"][0]["status"], "todo")
        self.assertTrue(result["decisions"])
        self.assertTrue(result["open_questions"][0]["text"].startswith("[NEEDS_REVIEW]"))


if __name__ == "__main__":
    unittest.main()

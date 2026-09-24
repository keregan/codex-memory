import unittest
from pathlib import Path

from codex_memory.reconciler import reconcile


class ReconcilerTests(unittest.TestCase):
    def test_completed_task_leaves_todo(self):
        first = reconcile(None, {
            "summary": "Bot", "purpose": "", "technologies": [], "architecture": [],
            "components": [], "implemented": [], "constraints": [], "decisions": [],
            "tasks": [{"title": "Добавить тесты", "status": "todo"}],
            "open_questions": [], "agent_instructions": {},
        }, "bot", "Bot", Path("one.txt"))

        updated = reconcile(first, {
            "summary": "", "purpose": "", "technologies": [], "architecture": [],
            "components": [], "implemented": [], "constraints": [], "decisions": [],
            "tasks": [{"title": "Тесты добавлены", "status": "completed"}],
            "open_questions": [], "agent_instructions": {},
        }, "bot", "Bot", Path("two.txt"))

        self.assertEqual(updated["todo_tasks"], [])
        self.assertEqual(len(updated["completed_tasks"]), 1)

    def test_explicit_technology_migration_replaces_old_value(self):
        first = reconcile(None, {
            "summary": "", "purpose": "", "technologies": ["SQLite"], "architecture": [],
            "components": [], "implemented": [], "constraints": [], "decisions": [],
            "tasks": [], "open_questions": [], "agent_instructions": {},
        }, "bot", "Bot", Path("one.txt"))
        updated = reconcile(first, {
            "summary": "", "purpose": "", "technologies": ["PostgreSQL"], "architecture": [],
            "components": [], "implemented": [], "constraints": [],
            "decisions": [{"title": "Перешли с SQLite на PostgreSQL", "source_blocks": [1]}],
            "tasks": [], "open_questions": [], "agent_instructions": {},
        }, "bot", "Bot", Path("two.txt"))

        names = [item if isinstance(item, str) else item["text"] for item in updated["technologies"]]
        self.assertNotIn("SQLite", names)
        self.assertIn("PostgreSQL", names)


if __name__ == "__main__":
    unittest.main()

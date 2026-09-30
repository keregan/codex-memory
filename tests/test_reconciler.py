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

        technologies = {item["text"]: item for item in updated["technologies"]}
        self.assertEqual(technologies["SQLite"]["status"], "superseded")
        self.assertEqual(technologies["PostgreSQL"]["status"], "active")

    def test_duplicate_fact_keeps_id_and_accumulates_evidence(self):
        first = reconcile(None, {
            "summary": "", "purpose": "", "technologies": [{
                "text": "Python", "confidence": "MEDIUM", "source_blocks": [1],
            }],
            "architecture": [], "components": [], "implemented": [], "constraints": [],
            "decisions": [], "tasks": [], "open_questions": [], "agent_instructions": {},
        }, "bot", "Bot", Path("one.txt"))
        first_id = first["technologies"][0]["id"]

        updated = reconcile(first, {
            "summary": "", "purpose": "", "technologies": [{
                "text": "Python", "confidence": "HIGH", "source_blocks": [4],
            }],
            "architecture": [], "components": [], "implemented": [], "constraints": [],
            "decisions": [], "tasks": [], "open_questions": [], "agent_instructions": {},
        }, "bot", "Bot", Path("two.txt"))

        fact = updated["technologies"][0]
        self.assertEqual(fact["id"], first_id)
        self.assertEqual(fact["confidence"], "HIGH")
        self.assertEqual(fact["source_blocks"], [1, 4])
        self.assertEqual([entry["source"] for entry in fact["evidence"]], ["one.txt", "two.txt"])


if __name__ == "__main__":
    unittest.main()

import unittest

from codex_memory.migrations import migrate_memory_document
from codex_memory.models import SCHEMA_VERSION, empty_memory
from codex_memory.schema import load_json_schema, validate_memory_document


class SchemaMigrationTests(unittest.TestCase):
    def test_bundled_schema_matches_current_version(self):
        schema = load_json_schema()

        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(schema["properties"]["schema_version"]["const"], SCHEMA_VERSION)
        self.assertIn("evidence", schema["$defs"])
        self.assertEqual(
            set(schema["$defs"]["fact"]["required"]),
            {"id", "text", "status", "confidence", "source_blocks", "evidence"},
        )

    def test_migrates_v1_through_current_and_preserves_created_date(self):
        old = empty_memory("telegram_bot")
        old["schema_version"] = 1
        old.pop("created_at")
        old["last_updated"] = "2026-01-02T03:04:05+00:00"
        old["update_history"] = [{
            "date": "2026-01-01T01:02:03+00:00", "source": "history.txt", "mode": "create",
        }]

        migrated, changed = migrate_memory_document(old)

        self.assertTrue(changed)
        self.assertEqual(migrated["schema_version"], SCHEMA_VERSION)
        self.assertEqual(migrated["created_at"], "2026-01-01T01:02:03+00:00")

    def test_migrates_v2_items_to_stable_ids_and_evidence_shape(self):
        old = empty_memory("telegram_bot")
        old["schema_version"] = 2
        old["technologies"] = [
            "Python",
            {"text": "SQLite", "confidence": "HIGH", "source_blocks": [2]},
        ]
        old["todo_tasks"] = ["Добавить тесты"]
        old["decisions"] = [{"title": "Использовать SQLite", "status": "active"}]

        migrated, changed = migrate_memory_document(old)

        self.assertTrue(changed)
        self.assertEqual(migrated["schema_version"], SCHEMA_VERSION)
        self.assertEqual(len(migrated["technologies"][0]["id"]), 20)
        self.assertEqual(migrated["technologies"][1]["source_blocks"], [2])
        self.assertEqual(migrated["technologies"][1]["evidence"], [])
        self.assertEqual(migrated["todo_tasks"][0]["status"], "todo")
        self.assertEqual(migrated["decisions"][0]["status"], "active")

    def test_current_document_is_not_changed(self):
        current = empty_memory("telegram_bot")

        migrated, changed = migrate_memory_document(current)

        self.assertFalse(changed)
        self.assertEqual(migrated, current)

    def test_rejects_future_version_and_unknown_fields(self):
        future = empty_memory("telegram_bot")
        future["schema_version"] = SCHEMA_VERSION + 1
        with self.assertRaises(ValueError):
            migrate_memory_document(future)

        invalid = empty_memory("telegram_bot")
        invalid["unexpected"] = True
        with self.assertRaises(ValueError):
            validate_memory_document(invalid)

        invalid_item = empty_memory("telegram_bot")
        invalid_item["technologies"] = [{"text": "Python", "unexpected": True}]
        with self.assertRaises(ValueError):
            validate_memory_document(invalid_item)

        invalid_decision = empty_memory("telegram_bot")
        invalid_decision["decisions"] = [{"title": "Use Python", "reason": ["not", "text"]}]
        with self.assertRaises(ValueError):
            validate_memory_document(invalid_decision)


if __name__ == "__main__":
    unittest.main()

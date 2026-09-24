import unittest

from codex_memory.models import validate_extraction


class ExtractionValidationTests(unittest.TestCase):
    def test_sanitizes_untrusted_analyzer_fields(self):
        result = validate_extraction({
            "technologies": [
                {"text": "Python", "confidence": "certain", "source_blocks": [1, "2", -1, True]},
                {"unexpected": "ignored"},
                42,
            ],
            "decisions": [{"title": "Use Python", "secret": "discard"}],
            "tasks": [{"title": "Test", "status": "unknown", "extra": "discard"}],
            "agent_instructions": {"rules": ["Keep it local"]},
        })

        self.assertEqual(result["technologies"], [{
            "text": "Python", "confidence": "MEDIUM", "source_blocks": [1, 2],
        }])
        self.assertNotIn("secret", result["decisions"][0])
        self.assertEqual(result["tasks"][0]["status"], "todo")
        self.assertNotIn("extra", result["tasks"][0])

    def test_rejects_wrong_top_level_field_types(self):
        with self.assertRaises(ValueError):
            validate_extraction({"technologies": "Python"})
        with self.assertRaises(ValueError):
            validate_extraction({"agent_instructions": []})


if __name__ == "__main__":
    unittest.main()

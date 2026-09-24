import unittest

from codex_memory.llm import _parse_json_content


class LlmResponseTests(unittest.TestCase):
    def test_parses_plain_and_fenced_json(self):
        self.assertEqual(_parse_json_content('{"ok": true}'), {"ok": True})
        self.assertEqual(_parse_json_content('```json\n{"ok": true}\n```'), {"ok": True})

    def test_rejects_invalid_or_non_object_json(self):
        with self.assertRaises(RuntimeError):
            _parse_json_content("not json")
        with self.assertRaises(RuntimeError):
            _parse_json_content("[]")


if __name__ == "__main__":
    unittest.main()

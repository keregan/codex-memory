import unittest

from codex_memory.project_names import safe_project_name


class ProjectNameTests(unittest.TestCase):
    def test_normalizes_and_handles_windows_reserved_names(self):
        self.assertEqual(safe_project_name(" Telegram Bot "), "telegram_bot")
        self.assertEqual(safe_project_name("CON"), "project_con")

    def test_rejects_empty_and_removes_trailing_dot_after_truncation(self):
        with self.assertRaises(ValueError):
            safe_project_name("...")
        self.assertFalse(safe_project_name("a" * 79 + "..more").endswith("."))


if __name__ == "__main__":
    unittest.main()

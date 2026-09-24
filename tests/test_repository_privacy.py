import re
import unittest
from pathlib import Path


class RepositoryPrivacyTests(unittest.TestCase):
    def test_repository_has_no_obvious_secrets_or_personal_windows_paths(self):
        roots = [
            Path("main.py"), Path("README.md"), Path("CONTRIBUTING.md"), Path("SECURITY.md"),
            Path("AGENTS.md"), Path("codex_memory"), Path("tests"), Path("docs"), Path(".github"),
        ]
        files = []
        for root in roots:
            if root.is_file():
                files.append(root)
            elif root.is_dir():
                files.extend(path for path in root.rglob("*") if path.is_file() and "__pycache__" not in path.parts)

        patterns = {
            "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
            "OpenAI-style API key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
            "personal Windows path": re.compile(r"[A-Za-z]:\\Users\\(?!Example\\)[^\\\s]+\\"),
        }
        findings = []
        for path in files:
            text = path.read_text(encoding="utf-8", errors="ignore")
            for label, pattern in patterns.items():
                if pattern.search(text):
                    findings.append(f"{path}: {label}")

        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()

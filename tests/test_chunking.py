import json
import unittest

from codex_memory.analyzer import LLMAnalyzer, _hierarchical_combine_extractions
from codex_memory.chunking import chunk_messages
from codex_memory.models import Message, ProjectCandidate


class QueueClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def json_completion(self, system, user):
        self.calls.append(json.loads(user.removeprefix("Conversation blocks:\n")))
        return self.responses.pop(0)


class ChunkingTests(unittest.TestCase):
    def test_chunks_in_order_and_splits_oversized_message(self):
        messages = [
            Message(1, "a" * 700, role="user"),
            Message(2, "b" * 1800, role="assistant"),
        ]

        chunks = chunk_messages(messages, max_chars=1000)
        flattened = [message for chunk in chunks for message in chunk]

        self.assertGreaterEqual(len(chunks), 3)
        self.assertEqual(flattened[0].number, 1)
        self.assertTrue(all(message.number == 2 for message in flattened[1:]))
        self.assertEqual("".join(message.text for message in flattened if message.number == 2), "b" * 1800)

    def test_rejects_too_small_chunk(self):
        with self.assertRaises(ValueError):
            chunk_messages([Message(1, "text")], max_chars=999)

    def test_llm_project_detection_merges_chunk_results(self):
        client = QueueClient([
            {"projects": [{
                "name": "telegram_bot", "display_name": "Telegram Bot", "aliases": ["bot"],
                "message_numbers": [1], "confidence": "MEDIUM",
            }]},
            {"projects": [{
                "name": "telegram_bot", "display_name": "Telegram Bot", "aliases": ["tg bot"],
                "message_numbers": [2], "confidence": "HIGH",
            }]},
        ])
        analyzer = LLMAnalyzer(client, chunk_chars=1000)
        messages = [Message(1, "a" * 700), Message(2, "b" * 700)]

        projects = analyzer.detect_projects(messages)

        self.assertEqual(len(client.calls), 2)
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0].aliases, ["bot", "tg bot"])
        self.assertEqual(projects[0].message_numbers, [1, 2])
        self.assertEqual(projects[0].confidence, "HIGH")

    def test_llm_extraction_combines_all_chunks_chronologically(self):
        empty = {
            "purpose": "", "architecture": [], "components": [], "implemented": [],
            "constraints": [], "decisions": [], "tasks": [], "open_questions": [],
            "agent_instructions": {},
        }
        client = QueueClient([
            {**empty, "summary": "Old summary", "technologies": ["SQLite"]},
            {**empty, "summary": "Current summary", "technologies": ["PostgreSQL"]},
        ])
        analyzer = LLMAnalyzer(client, chunk_chars=1000)
        project = ProjectCandidate("telegram_bot", "Telegram Bot", message_numbers=[1, 2])
        messages = [Message(1, "telegram_bot " + "a" * 680), Message(2, "telegram_bot " + "b" * 680)]

        extraction = analyzer.extract(project, messages)

        self.assertEqual(len(client.calls), 2)
        self.assertEqual(extraction["summary"], "Current summary")
        self.assertEqual(extraction["technologies"], ["SQLite", "PostgreSQL"])

    def test_hierarchical_reduce_deduplicates_and_merges_metadata(self):
        empty = {
            "summary": "", "purpose": "", "technologies": [], "architecture": [],
            "components": [], "implemented": [], "constraints": [], "decisions": [],
            "tasks": [], "open_questions": [], "agent_instructions": {},
        }
        extractions = [
            {**empty, "summary": "Reliable summary", "technologies": [{
                "text": "Python", "confidence": "MEDIUM", "source_blocks": [1],
            }]},
            {**empty, "tasks": [{
                "title": "Add API tests", "status": "todo", "confidence": "MEDIUM",
                "source_blocks": [2],
            }]},
            {**empty, "technologies": [{
                "text": "Python", "confidence": "HIGH", "source_blocks": [3],
            }]},
            {**empty, "tasks": [{
                "title": "Add API tests", "status": "completed", "confidence": "HIGH",
                "source_blocks": [4],
            }]},
            {**empty, "summary": "[NEEDS_REVIEW] unclear"},
        ]

        result = _hierarchical_combine_extractions(extractions, fan_in=2)

        self.assertEqual(result["summary"], "Reliable summary")
        self.assertEqual(len(result["technologies"]), 1)
        self.assertEqual(result["technologies"][0]["confidence"], "HIGH")
        self.assertEqual(result["technologies"][0]["source_blocks"], [1, 3])
        self.assertEqual(len(result["tasks"]), 1)
        self.assertEqual(result["tasks"][0]["status"], "completed")
        self.assertEqual(result["tasks"][0]["source_blocks"], [2, 4])

    def test_hierarchical_reduce_rejects_invalid_fan_in(self):
        with self.assertRaises(ValueError):
            _hierarchical_combine_extractions([], fan_in=1)


if __name__ == "__main__":
    unittest.main()

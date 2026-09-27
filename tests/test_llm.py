import io
import json
import unittest
import urllib.error
from unittest.mock import patch

from codex_memory.llm import ChatCompletionsClient, _parse_json_content, _wait_before_retry


class FakeResponse:
    def __init__(self, payload, headers=None):
        self.payload = payload
        self.headers = headers or {}

    def read(self, limit=-1):
        return self.payload if limit < 0 else self.payload[:limit]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


def completion_response(value):
    return json.dumps({
        "choices": [{"message": {"content": json.dumps(value)}}],
    }).encode("utf-8")


class LlmResponseTests(unittest.TestCase):
    def test_parses_plain_and_fenced_json(self):
        self.assertEqual(_parse_json_content('{"ok": true}'), {"ok": True})
        self.assertEqual(_parse_json_content('```json\n{"ok": true}\n```'), {"ok": True})

    def test_rejects_invalid_or_non_object_json(self):
        with self.assertRaises(RuntimeError):
            _parse_json_content("not json")
        with self.assertRaises(RuntimeError):
            _parse_json_content("[]")

    def test_rejects_response_larger_than_limit(self):
        client = ChatCompletionsClient(
            "https://example.invalid/v1/chat/completions",
            "test-model",
            max_response_bytes=10,
            retries=0,
        )
        response = FakeResponse(b"x" * 11)

        with patch("codex_memory.llm.urllib.request.urlopen", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "exceeds the 10-byte limit"):
                client.json_completion("system", "user")

    def test_retries_temporary_http_error_and_honors_retry_after(self):
        client = ChatCompletionsClient(
            "https://example.invalid/v1/chat/completions",
            "test-model",
            retries=1,
        )
        temporary_error = urllib.error.HTTPError(
            client.api_url,
            503,
            "Service Unavailable",
            {"Retry-After": "2"},
            io.BytesIO(b"temporary"),
        )
        success = FakeResponse(completion_response({"ok": True}))

        with patch(
            "codex_memory.llm.urllib.request.urlopen",
            side_effect=[temporary_error, success],
        ) as urlopen, patch("codex_memory.llm.time.sleep") as sleep:
            result = client.json_completion("system", "user")

        self.assertEqual(result, {"ok": True})
        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once_with(2.0)

    def test_does_not_retry_non_temporary_http_error(self):
        client = ChatCompletionsClient(
            "https://example.invalid/v1/chat/completions",
            "test-model",
            retries=2,
        )
        bad_request = urllib.error.HTTPError(
            client.api_url,
            400,
            "Bad Request",
            {},
            io.BytesIO(b"invalid request"),
        )

        with patch(
            "codex_memory.llm.urllib.request.urlopen",
            side_effect=bad_request,
        ) as urlopen, patch("codex_memory.llm.time.sleep") as sleep:
            with self.assertRaisesRegex(RuntimeError, "HTTP 400"):
                client.json_completion("system", "user")

        self.assertEqual(urlopen.call_count, 1)
        sleep.assert_not_called()

    def test_retries_network_error_until_limit(self):
        client = ChatCompletionsClient(
            "https://example.invalid/v1/chat/completions",
            "test-model",
            retries=2,
        )
        network_error = urllib.error.URLError("offline")

        with patch(
            "codex_memory.llm.urllib.request.urlopen",
            side_effect=network_error,
        ) as urlopen, patch("codex_memory.llm.random.uniform", return_value=0), patch(
            "codex_memory.llm.time.sleep"
        ) as sleep:
            with self.assertRaisesRegex(RuntimeError, "Could not reach"):
                client.json_completion("system", "user")

        self.assertEqual(urlopen.call_count, 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [1, 2])

    def test_invalid_retry_after_falls_back_to_bounded_backoff(self):
        with patch("codex_memory.llm.random.uniform", return_value=0.25), patch(
            "codex_memory.llm.time.sleep"
        ) as sleep:
            _wait_before_retry(0, {"Retry-After": "Infinity"})

        sleep.assert_called_once_with(1.25)


if __name__ == "__main__":
    unittest.main()

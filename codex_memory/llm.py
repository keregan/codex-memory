from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any


class ChatCompletionsClient:
    """Small stdlib client for an explicitly configured Chat Completions endpoint."""

    def __init__(self, api_url: str, model: str, api_key: str = "", timeout: int = 120) -> None:
        if not api_url.startswith(("http://", "https://")):
            raise ValueError("--api-url must begin with http:// or https://")
        self.api_url = api_url
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    def json_completion(self, system: str, user: str) -> dict[str, Any]:
        body = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(self.api_url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise RuntimeError(f"LLM API returned HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Could not reach the configured LLM API: {exc.reason}") from exc

        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("Unexpected Chat Completions response shape") from exc
        if not isinstance(content, str):
            raise RuntimeError("LLM returned non-text content")
        return _parse_json_content(content)


def _parse_json_content(content: str) -> dict[str, Any]:
    cleaned = content.strip()
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", cleaned, flags=re.DOTALL | re.IGNORECASE)
    if fence:
        cleaned = fence.group(1)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"LLM did not return valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError("LLM JSON response must be an object")
    return value

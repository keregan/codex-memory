from __future__ import annotations

import json
import math
import random
import re
import time
import urllib.error
import urllib.request
from typing import Any


DEFAULT_LLM_TIMEOUT = 120
DEFAULT_LLM_RETRIES = 2
DEFAULT_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_LLM_RETRIES = 10
RETRYABLE_HTTP_CODES = {429, 502, 503, 504}
MAX_RETRY_DELAY = 30.0


class ChatCompletionsClient:
    """Small stdlib client for an explicitly configured Chat Completions endpoint."""

    def __init__(
        self,
        api_url: str,
        model: str,
        api_key: str = "",
        timeout: int = DEFAULT_LLM_TIMEOUT,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        retries: int = DEFAULT_LLM_RETRIES,
    ) -> None:
        if not api_url.startswith(("http://", "https://")):
            raise ValueError("--api-url must begin with http:// or https://")
        if timeout <= 0:
            raise ValueError("LLM timeout must be greater than zero")
        if max_response_bytes <= 0:
            raise ValueError("LLM maximum response size must be greater than zero")
        if not 0 <= retries <= MAX_LLM_RETRIES:
            raise ValueError(f"LLM retries must be between 0 and {MAX_LLM_RETRIES}")
        self.api_url = api_url
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.max_response_bytes = max_response_bytes
        self.retries = retries

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
        payload = self._request_json(request)

        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("Unexpected Chat Completions response shape") from exc
        if not isinstance(content, str):
            raise RuntimeError("LLM returned non-text content")
        return _parse_json_content(content)

    def _request_json(self, request: urllib.request.Request) -> dict[str, Any]:
        for attempt in range(self.retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    raw = _read_limited_response(response, self.max_response_bytes)
                payload = json.loads(raw.decode("utf-8"))
                if not isinstance(payload, dict):
                    raise RuntimeError("LLM API response must be a JSON object")
                return payload
            except urllib.error.HTTPError as exc:
                detail = exc.read(1000).decode("utf-8", errors="replace")
                if exc.code not in RETRYABLE_HTTP_CODES or attempt >= self.retries:
                    raise RuntimeError(f"LLM API returned HTTP {exc.code}: {detail}") from exc
                _wait_before_retry(attempt, exc.headers)
            except urllib.error.URLError as exc:
                if attempt >= self.retries:
                    raise RuntimeError(f"Could not reach the configured LLM API: {exc.reason}") from exc
                _wait_before_retry(attempt)
            except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
                raise RuntimeError(f"LLM API returned invalid JSON: {exc}") from exc

        raise RuntimeError("LLM request failed after retries")


def _read_limited_response(response: Any, max_bytes: int) -> bytes:
    content_length = response.headers.get("Content-Length")
    if content_length:
        try:
            declared_size = int(content_length)
        except (TypeError, ValueError):
            declared_size = None
        if declared_size is not None and declared_size > max_bytes:
            raise RuntimeError(
                f"LLM API response exceeds the {max_bytes}-byte limit"
            )
    raw = response.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise RuntimeError(f"LLM API response exceeds the {max_bytes}-byte limit")
    return raw


def _wait_before_retry(attempt: int, headers: Any = None) -> None:
    retry_after = headers.get("Retry-After") if headers is not None else None
    try:
        delay = float(retry_after) if retry_after is not None else None
    except (TypeError, ValueError):
        delay = None
    if delay is None or not math.isfinite(delay) or delay < 0:
        delay = (2 ** attempt) + random.uniform(0, 0.25)
    time.sleep(min(delay, MAX_RETRY_DELAY))


def _parse_json_content(content: str) -> dict[str, Any]:
    cleaned = content.strip()
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", cleaned, flags=re.DOTALL | re.IGNORECASE)
    if fence:
        cleaned = fence.group(1)
    try:
        value = json.loads(cleaned)
    except (json.JSONDecodeError, RecursionError) as exc:
        raise RuntimeError(f"LLM did not return valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError("LLM JSON response must be an object")
    return value

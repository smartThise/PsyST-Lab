"""OpenAI 兼容 API client — 支持单轮和多轮对话."""
from __future__ import annotations

import time
from typing import Any

import requests


class APIError(RuntimeError):
    pass


class APIClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float = 0.0,
        max_tokens: int = 64,
        max_retries: int = 5,
        timeout: int = 60,
        extra_body: dict[str, Any] | None = None,
    ):
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_retries = max_retries
        self.timeout = timeout
        self.extra_body = extra_body or {}

    def chat(
        self,
        messages: list[dict[str, str]] | str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """发送消息, 返回 assistant content.

        Args:
            messages: 消息列表 [{"role":"user","content":"..."}]
                      或单条字符串 (自动包装为 user message)
            temperature: 覆盖默认 temperature
            max_tokens: 覆盖默认 max_tokens
        """
        if isinstance(messages, str):
            messages = [{"role": "user", "content": messages}]

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": self.max_tokens if max_tokens is None else max_tokens,
        }
        if self.extra_body:
            payload.update(self.extra_body)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = requests.post(
                    self.url, json=payload, headers=headers, timeout=self.timeout
                )
                if resp.status_code in (429, 500, 502, 503, 504):
                    raise APIError(f"HTTP {resp.status_code}: {resp.text[:200]}")
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"].strip()
            except Exception as exc:
                last_exc = exc
                if attempt >= self.max_retries:
                    break
                backoff = min(2 ** attempt, 30)
                time.sleep(backoff)
        raise APIError(f"API call failed after {self.max_retries} retries: {last_exc}")

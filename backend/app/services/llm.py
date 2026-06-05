from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field

from backend.app.models import AnalysisError, AnalysisErrorSeverity, AnalysisStage


class LLMMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str = Field(min_length=1)
    content: str = Field(min_length=1)


class LLMClient(Protocol):
    def complete(self, messages: list[LLMMessage]) -> str:
        """Return assistant message content."""


@dataclass(frozen=True)
class LLMConfig:
    base_url: str
    api_key: str
    model: str
    timeout_seconds: float = 30.0


class FakeLLMClient:
    def __init__(self, responses: list[str] | None = None) -> None:
        self._responses = list(responses or ['{"ok": true}'])
        self.calls: list[list[LLMMessage]] = []

    def complete(self, messages: list[LLMMessage]) -> str:
        self.calls.append(messages)
        if len(self._responses) > 1:
            return self._responses.pop(0)
        return self._responses[0]


class OpenAICompatibleLLMClient:
    def __init__(
        self,
        config: LLMConfig,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.config = config
        self._client = http_client or httpx.Client(timeout=config.timeout_seconds)

    def complete(self, messages: list[LLMMessage]) -> str:
        base_url = self.config.base_url.rstrip("/")
        response = self._client.post(
            f"{base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.config.model,
                "messages": [message.model_dump() for message in messages],
                "temperature": 0.2,
            },
        )
        response.raise_for_status()
        payload = response.json()
        return str(payload["choices"][0]["message"]["content"])


def create_llm_client_from_env() -> LLMClient | None:
    provider = os.environ.get("LLM_PROVIDER", "fake").strip().lower()
    if provider in {"", "fake", "none", "disabled"}:
        return None
    if provider != "openai_compatible":
        raise RuntimeError(f"Unsupported LLM_PROVIDER: {provider}")

    base_url = os.environ.get("LLM_BASE_URL", "").strip()
    api_key = os.environ.get("LLM_API_KEY", "").strip()
    model = os.environ.get("LLM_MODEL", "").strip()
    if not base_url or not api_key or not model:
        raise RuntimeError(
            "LLM_PROVIDER=openai_compatible requires LLM_BASE_URL, LLM_API_KEY, and LLM_MODEL."
        )
    timeout = float(os.environ.get("LLM_TIMEOUT_SECONDS", "30") or 30)
    return OpenAICompatibleLLMClient(
        LLMConfig(
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout_seconds=timeout,
        )
    )


class StructuredJSONResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data: dict[str, object] | None
    error: AnalysisError | None
    attempts: int


class StructuredJSONCaller:
    def __init__(self, client: LLMClient, stage: AnalysisStage) -> None:
        self.client = client
        self.stage = stage

    def call(self, messages: list[LLMMessage]) -> StructuredJSONResult:
        attempts = 0
        last_content = ""
        retry_messages = list(messages)
        for _ in range(2):
            attempts += 1
            try:
                last_content = self.client.complete(retry_messages)
            except Exception as exc:
                return StructuredJSONResult(
                    data=None,
                    error=AnalysisError(
                        stage=self.stage,
                        code="provider_request_failed",
                        user_message_zh="AI 服务暂时不可用，已使用备用结果。",
                        severity=AnalysisErrorSeverity.WARNING,
                        fallback_applied=True,
                        provider="llm",
                        raw_code=_safe_error_code(exc),
                    ),
                    attempts=attempts,
                )
            try:
                parsed = json.loads(last_content)
            except json.JSONDecodeError:
                retry_messages = [
                    *messages,
                    LLMMessage(
                        role="system",
                        content="Return valid JSON only. Do not include markdown fences.",
                    ),
                ]
                continue
            if isinstance(parsed, dict):
                return StructuredJSONResult(data=parsed, error=None, attempts=attempts)
            break

        return StructuredJSONResult(
            data=None,
            error=AnalysisError(
                stage=self.stage,
                code="invalid_json",
                user_message_zh="AI 结果格式异常，已跳过本次结构化分析。",
                severity=AnalysisErrorSeverity.WARNING,
                fallback_applied=True,
                provider="llm",
                raw_code=last_content[:120],
            ),
            attempts=attempts,
        )


def _safe_error_code(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"http_status_{exc.response.status_code}"
    return type(exc).__name__

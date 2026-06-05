import httpx

from backend.app.models import AnalysisStage
from backend.app.services.llm import (
    FakeLLMClient,
    LLMConfig,
    LLMMessage,
    OpenAICompatibleLLMClient,
    StructuredJSONCaller,
)


def test_fake_llm_client_returns_configured_response() -> None:
    client = FakeLLMClient(responses=['{"reply": "hello"}'])

    content = client.complete([LLMMessage(role="user", content="Hi")])

    assert content == '{"reply": "hello"}'
    assert len(client.calls) == 1


def test_structured_json_caller_retries_once_after_invalid_json() -> None:
    client = FakeLLMClient(responses=["not json", '{"reply": "valid"}'])
    caller = StructuredJSONCaller(client=client, stage=AnalysisStage.GRAMMAR)

    result = caller.call([LLMMessage(role="user", content="Check this sentence")])

    assert result.data == {"reply": "valid"}
    assert result.error is None
    assert result.attempts == 2
    assert len(client.calls) == 2
    assert client.calls[1][-1].role == "system"


def test_structured_json_caller_returns_analysis_error_after_two_failures() -> None:
    client = FakeLLMClient(responses=["not json", "still not json"])
    caller = StructuredJSONCaller(client=client, stage=AnalysisStage.GRAMMAR)

    result = caller.call([LLMMessage(role="user", content="Check this sentence")])

    assert result.data is None
    assert result.error is not None
    assert result.error.code == "invalid_json"
    assert result.error.fallback_applied is True
    assert result.attempts == 2


def test_openai_compatible_client_posts_chat_completion_payload() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers["Authorization"]
        captured["payload"] = request.read()
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"reply": "ok"}',
                        }
                    }
                ]
            },
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = OpenAICompatibleLLMClient(
        config=LLMConfig(
            base_url="https://llm.example.test/v1",
            api_key="test-key",
            model="test-model",
        ),
        http_client=http_client,
    )

    content = client.complete([LLMMessage(role="user", content="Hello")])

    assert content == '{"reply": "ok"}'
    assert captured["url"] == "https://llm.example.test/v1/chat/completions"
    assert captured["auth"] == "Bearer test-key"
    assert b'"model":"test-model"' in captured["payload"]

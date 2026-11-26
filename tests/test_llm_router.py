"""Tests for 3-tier LLM fallback router: DashScope free -> OpenCode Go -> DashScope paid."""

from pathlib import Path

import pytest

from src.llm_router import AutoLLMRouter, ProviderError


def _ok(text='{"ids":["1"]}'):
    return {
        "id": "resp-1",
        "choices": [{"message": {"content": text}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def test_prefers_dashscope_free_pool_first(tmp_path: Path):
    calls = []

    def fake_send(endpoint, key, payload, *, session_id):
        calls.append((endpoint, payload["model"], payload.get("enable_thinking")))
        return _ok()

    router = AutoLLMRouter(
        tmp_path,
        env={"DASHSCOPE_API_KEY": "ds-k", "OPENCODE_API_KEY": "oc-k"},
        send=fake_send,
    )
    content, finish, ep, model = router.complete_json(stage="gate", system="s", user="u")
    assert content == '{"ids":["1"]}'
    assert finish == "stop"
    assert ep == "dashscope_free"
    assert model == "qwen3.8-max-0902"
    assert calls == [("dashscope_free", "qwen3.8-max-0902", False)]


def test_cascades_free_pool_to_opencode_go_to_dashscope_paid(tmp_path: Path):
    calls = []

    def fake_send(endpoint, key, payload, *, session_id):
        calls.append((endpoint, payload["model"]))
        if endpoint == "dashscope_free":
            raise ProviderError(403, "AllocationQuota.FreeTierOnly", "free tier exhausted")
        if endpoint == "opencode_go":
            raise ProviderError(429, "rate_limit_exceeded", "5h quota hit")
        return _ok('{"ok":true}')

    router = AutoLLMRouter(
        tmp_path,
        env={"DASHSCOPE_API_KEY": "ds-k", "OPENCODE_API_KEY": "oc-k"},
        send=fake_send,
    )
    content, _, ep, model = router.complete_json(stage="gate", system="s", user="u")
    assert content == '{"ok":true}'
    assert ep == "dashscope"
    assert model == "qwen3.8-flash"
    assert calls == [
        ("dashscope_free", "qwen3.8-max-0902"),
        ("dashscope_free", "deepseek-v4.1-flash"),
        ("dashscope_free", "deepseek-v4.1-flash-1017"),
        ("opencode_go", "qwen3.8-flash"),
        ("dashscope", "qwen3.8-flash"),
    ]

    # Subsequent call skips already-exhausted free + opencode_go routes directly to paid
    calls.clear()
    _, _, ep2, _ = router.complete_json(stage="gate", system="s", user="u2")
    assert ep2 == "dashscope"
    assert calls == [("dashscope", "qwen3.8-flash")]


def test_opencode_go_used_when_free_pool_exhausted(tmp_path: Path):
    seen_sessions = []

    def fake_send(endpoint, key, payload, *, session_id):
        seen_sessions.append((endpoint, session_id, "enable_thinking" in payload))
        if endpoint == "dashscope_free":
            raise ProviderError(403, "FreeTierOnly", "exhausted")
        return _ok('{"ids":[]}')

    router = AutoLLMRouter(
        tmp_path,
        env={"DASHSCOPE_API_KEY": "ds-k", "OPENCODE_API_KEY": "oc-k"},
        send=fake_send,
    )
    _, _, ep, model = router.complete_json(stage="extraction", system="s", user="u")
    assert ep == "opencode_go"
    assert model == "qwen4-max"
    # OpenCode Go does not pass enable_thinking and carries a stable session_id
    oc_calls = [c for c in seen_sessions if c[0] == "opencode_go"]
    assert len(oc_calls) == 1
    assert oc_calls[0][1]
    assert oc_calls[0][2] is False


def test_raises_when_no_keys(tmp_path: Path):
    router = AutoLLMRouter(tmp_path, env={})
    with pytest.raises(ValueError, match="DASHSCOPE_API_KEY"):
        router.complete_json(stage="gate", system="s", user="u")

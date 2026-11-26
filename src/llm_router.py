"""Three-tier LLM router: DashScope free pool -> OpenCode Go -> DashScope paid."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import threading
import time
import uuid

from dotenv import dotenv_values
import httpx

from .storage import digest, write_json

ENDPOINTS = {
    "dashscope_free": (
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "DASHSCOPE_API_KEY",
    ),
    "opencode_go": (
        "https://opencode.ai/inference/go/openai/v1",
        "OPENCODE_API_KEY",
    ),
    "dashscope": (
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "DASHSCOPE_API_KEY",
    ),
}

DEFAULT_FREE_POOL = (
    "qwen3.8-max-0902",
    "deepseek-v4.1-flash",
    "deepseek-v4.1-flash-1017",
)
OPENCODE_MODELS = {
    "gate": "qwen3.8-flash",
    "extraction": "qwen4-max",
}
DASHSCOPE_PAID_MODELS = {
    "gate": "qwen3.8-flash",
    "extraction": "qwen3.8-flash",
}


class ProviderError(Exception):
    def __init__(self, status: int, code: str, message: str = ""):
        self.status = status
        self.code = str(code)[:80]
        self.message = str(message)[:200]
        super().__init__(f"HTTP {status} ({self.code})")


def _load_key(name: str, env: dict[str, str] | None = None) -> str:
    if env is not None:
        return (env.get(name) or "").strip()
    val = (os.getenv(name) or "").strip()
    if val:
        return val
    keys_file = Path.home() / ".config/ai-keys/keys.env"
    if keys_file.is_file():
        return (dotenv_values(keys_file).get(name) or "").strip()
    return ""


def _post_chat(endpoint: str, api_key: str, payload: dict, *, session_id: str) -> dict:
    base_url = ENDPOINTS[endpoint][0]
    headers = {"Authorization": f"Bearer {api_key}"}
    if endpoint == "opencode_go":
        headers["User-Agent"] = "ai-worlds-tracker/0.1"
        headers["x-opencode-session"] = session_id
    with httpx.Client(timeout=httpx.Timeout(125, connect=12), trust_env=False) as client:
        response = client.post(
            f"{base_url}/chat/completions",
            json=payload,
            headers=headers,
        )
    if response.status_code >= 400:
        try:
            err = response.json().get("error", {})
            code = err.get("code") or err.get("type") or "provider_error"
            msg = err.get("message") or ""
        except (ValueError, AttributeError, TypeError):
            code, msg = "provider_error", response.text[:160]
        raise ProviderError(response.status_code, code, msg)
    return response.json()


def _is_failover_error(endpoint: str, exc: Exception) -> bool:
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
        return True
    if not isinstance(exc, ProviderError):
        return False
    code = exc.code.lower()
    msg = exc.message.lower()
    if exc.status in {402, 429, 500, 502, 503, 504}:
        return True
    if endpoint == "dashscope_free":
        return exc.status in {400, 403, 404} and any(
            tok in code or tok in msg
            for tok in ("freetier", "quota", "exhaust", "allocation", "model", "not found", "access")
        )
    if endpoint == "opencode_go":
        return exc.status in {401, 403, 404} and any(
            tok in code or tok in msg for tok in ("quota", "limit", "model", "auth", "credit")
        )
    return False


def strip_json_text(raw: str) -> str:
    cleaned = re.sub(r"<think>.*?</think>", "", raw or "", flags=re.S).strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned).strip()
    return cleaned


class AutoLLMRouter:
    """Thread-safe 3-tier fallback router: DashScope free -> OpenCode Go -> DashScope paid."""

    def __init__(
        self,
        root: Path | None = None,
        *,
        env: dict[str, str] | None = None,
        free_pool: tuple[str, ...] = DEFAULT_FREE_POOL,
        send=_post_chat,
    ):
        self.root = root
        self.env = env
        self.free_pool = tuple(free_pool)
        self.send = send
        self.session_id = uuid.uuid4().hex
        self._lock = threading.Lock()
        self._exhausted: set[tuple[str, str]] = set()

    def _candidates(self, stage: str) -> list[tuple[str, str, str]]:
        routes: list[tuple[str, str, str]] = []
        ds_key = _load_key("DASHSCOPE_API_KEY", self.env)
        oc_key = _load_key("OPENCODE_API_KEY", self.env)
        if ds_key:
            for model in self.free_pool:
                routes.append(("dashscope_free", model, ds_key))
        if oc_key:
            oc_model = OPENCODE_MODELS.get(stage, "qwen3.8-flash")
            routes.append(("opencode_go", oc_model, oc_key))
            if oc_model != "qwen3.8-flash":
                routes.append(("opencode_go", "qwen3.8-flash", oc_key))
        if ds_key:
            paid_model = DASHSCOPE_PAID_MODELS.get(stage, "qwen3.8-flash")
            routes.append(("dashscope", paid_model, ds_key))
        return routes

    def _record_usage(self, stage: str, endpoint: str, model: str, data: dict) -> None:
        usage = data.get("usage")
        if self.root is None or not isinstance(usage, dict):
            return
        resp_id = str(data.get("id") or uuid.uuid4().hex)
        write_json(
            self.root / "processed/extraction/usage" / (digest(resp_id) + ".json"),
            {
                "stage": stage,
                "endpoint": endpoint,
                "model": model,
                "at": datetime.now(UTC).isoformat(),
                "usage": usage,
            },
        )

    def complete_json(
        self,
        *,
        stage: str,
        system: str,
        user: str,
        max_tokens: int = 2400,
    ) -> tuple[str, str, str, str]:
        """Return (content, finish_reason, endpoint, model) using the 3-tier cascade."""
        routes = self._candidates(stage)
        if not routes:
            raise ValueError(
                "No LLM credentials configured; set DASHSCOPE_API_KEY and/or OPENCODE_API_KEY"
            )
        last_error: Exception | None = None
        for endpoint, model, api_key in routes:
            with self._lock:
                if (endpoint, model) in self._exhausted:
                    continue
            payload: dict = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "max_tokens": max_tokens,
                "temperature": 0,
                "response_format": {"type": "json_object"},
            }
            if endpoint != "opencode_go":
                payload["enable_thinking"] = False
            for attempt in range(2):
                try:
                    data = self.send(endpoint, api_key, payload, session_id=self.session_id)
                    choices = data.get("choices") or []
                    if not choices:
                        raise ValueError(f"{endpoint}/{model} returned empty choices")
                    choice = choices[0]
                    content = strip_json_text((choice.get("message") or {}).get("content") or "")
                    finish = str(choice.get("finish_reason") or "stop")
                    self._record_usage(stage, endpoint, model, data)
                    return content, finish, endpoint, model
                except Exception as exc:
                    last_error = exc
                    if isinstance(exc, ProviderError) and exc.status == 429 and endpoint == "dashscope" and attempt == 0:
                        time.sleep(4)
                        continue
                    if _is_failover_error(endpoint, exc):
                        if endpoint in {"dashscope_free", "opencode_go"} and isinstance(exc, ProviderError):
                            with self._lock:
                                self._exhausted.add((endpoint, model))
                        print(
                            f"LLM route {endpoint}/{model} unavailable ({exc}); falling over",
                            flush=True,
                        )
                        break
                    raise
        raise ValueError(f"All LLM routes failed for {stage}: {last_error}") from last_error


_SHARED: dict[str, AutoLLMRouter] = {}
_SHARED_LOCK = threading.Lock()


def shared_router(root: Path | None) -> AutoLLMRouter:
    key = str(root.resolve()) if root is not None else ""
    with _SHARED_LOCK:
        router = _SHARED.get(key)
        if router is None:
            router = AutoLLMRouter(root)
            _SHARED[key] = router
        return router

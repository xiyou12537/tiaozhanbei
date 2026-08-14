from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Iterator, Protocol

import httpx


class AssistantModelError(RuntimeError):
    def __init__(self, code: str, message: str, status_code: int):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class AssistantRuntimeLimits:
    timeout_seconds: float
    max_output_tokens: int
    max_tool_calls: int
    confirmation_recovery_seconds: float
    context_max_messages: int = 40
    context_max_input_tokens: int = 12000


class AssistantModelAdapter(Protocol):
    def stream(
        self,
        *,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_output_tokens: int,
    ) -> Iterator[dict[str, Any]]: ...


class DisabledAssistantModelAdapter:
    def stream(self, *, system_prompt: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]], max_output_tokens: int) -> Iterator[dict[str, Any]]:
        del system_prompt, messages, tools, max_output_tokens
        raise AssistantModelError("assistant_model_unconfigured", "Molecular Copilot model is not configured on this server.", 503)
        yield  # pragma: no cover - keeps this method an iterator for Protocol callers.


class UnsupportedAssistantModelAdapter:
    """Stable server-side failure for a configured but unsupported model."""

    def stream(self, *, system_prompt: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]], max_output_tokens: int) -> Iterator[dict[str, Any]]:
        del system_prompt, messages, tools, max_output_tokens
        raise AssistantModelError("assistant_model_unsupported_model", "The configured Molecular Copilot model is not supported.", 503)
        yield  # pragma: no cover - keeps this method an iterator for Protocol callers.


@dataclass(frozen=True)
class OpenAICompatibleAssistantModelAdapter:
    base_url: str
    api_key: str
    model: str
    timeout_seconds: float

    def stream(
        self,
        *,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_output_tokens: int,
    ) -> Iterator[dict[str, Any]]:
        payload = self._request_payload(system_prompt, messages, tools, max_output_tokens)
        pending_tool_calls: dict[int, dict[str, str]] = {}
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                with client.stream(
                    "POST",
                    f"{self.base_url.rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json=payload,
                ) as response:
                    if response.status_code == 429:
                        raise AssistantModelError("assistant_model_rate_limited", "Molecular Copilot model is rate limited.", 429)
                    if response.status_code >= 400:
                        raise AssistantModelError("assistant_model_unavailable", "Molecular Copilot model returned an unavailable response.", 502)
                    for line in response.iter_lines():
                        if not line.startswith("data: "):
                            continue
                        data = line[6:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            delta = chunk["choices"][0].get("delta", {})
                        except (KeyError, IndexError, TypeError, ValueError) as exc:
                            raise AssistantModelError("assistant_model_invalid_response", "Molecular Copilot model returned an invalid stream response.", 502) from exc
                        content = delta.get("content")
                        if isinstance(content, str) and content:
                            yield {"type": "message_delta", "delta": content}
                        for tool_call in delta.get("tool_calls", []) or []:
                            index = int(tool_call.get("index", 0))
                            entry = pending_tool_calls.setdefault(index, {"id": "", "name": "", "raw_arguments": ""})
                            entry["id"] = tool_call.get("id") or entry["id"]
                            function = tool_call.get("function") or {}
                            entry["name"] = function.get("name") or entry["name"]
                            entry["raw_arguments"] += function.get("arguments") or ""
        except AssistantModelError:
            raise
        except httpx.TimeoutException as exc:
            raise AssistantModelError("assistant_model_timeout", "Molecular Copilot model request timed out.", 504) from exc
        except httpx.HTTPError as exc:
            raise AssistantModelError("assistant_model_unavailable", "Molecular Copilot model is unavailable.", 502) from exc
        for entry in pending_tool_calls.values():
            try:
                arguments = json.loads(entry["raw_arguments"] or "{}")
            except json.JSONDecodeError as exc:
                raise AssistantModelError("assistant_model_invalid_tool_call", "Molecular Copilot model emitted invalid tool arguments.", 502) from exc
            if (
                not isinstance(arguments, dict)
                or not isinstance(entry["id"], str)
                or not entry["id"]
                or not isinstance(entry["name"], str)
                or not entry["name"]
            ):
                raise AssistantModelError("assistant_model_invalid_tool_call", "Molecular Copilot model emitted an invalid tool call.", 502)
            raw_arguments = entry["raw_arguments"] or json.dumps(arguments, ensure_ascii=False, separators=(",", ":"))
            yield {"type": "tool_call", "id": entry["id"], "name": entry["name"], "raw_arguments": raw_arguments, "arguments": arguments}

    def _request_payload(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_output_tokens: int,
    ) -> dict[str, Any]:
        return {
            "model": self.model,
            "messages": [{"role": "system", "content": system_prompt}, *messages],
            "tools": tools,
            "tool_choice": "auto",
            "stream": True,
            "temperature": 0.2,
            "max_tokens": max_output_tokens,
        }


class DeepSeekAssistantModelAdapter(OpenAICompatibleAssistantModelAdapter):
    """DeepSeek's OpenAI-compatible endpoint with first-version thinking disabled."""

    def _request_payload(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_output_tokens: int,
    ) -> dict[str, Any]:
        payload = super()._request_payload(system_prompt, messages, tools, max_output_tokens)
        payload["thinking"] = {"type": "disabled"}
        return payload


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return min(max(value, minimum), maximum)


def assistant_runtime_limits() -> AssistantRuntimeLimits:
    try:
        timeout_seconds = float(os.getenv("MOLECULAR_ASSISTANT_MODEL_TIMEOUT_SECONDS", "30"))
    except ValueError:
        timeout_seconds = 30.0
    return AssistantRuntimeLimits(
        timeout_seconds=min(max(timeout_seconds, 1.0), 120.0),
        max_output_tokens=_bounded_int("MOLECULAR_ASSISTANT_MODEL_MAX_OUTPUT_TOKENS", 1024, 64, 8192),
        max_tool_calls=_bounded_int("MOLECULAR_ASSISTANT_MAX_TOOL_CALLS", 3, 1, 8),
        confirmation_recovery_seconds=float(_bounded_int("MOLECULAR_ASSISTANT_CONFIRMATION_RECOVERY_SECONDS", 2, 0, 30)),
        context_max_messages=_bounded_int("MOLECULAR_ASSISTANT_CONTEXT_MAX_MESSAGES", 40, 4, 100),
        context_max_input_tokens=_bounded_int("MOLECULAR_ASSISTANT_CONTEXT_MAX_INPUT_TOKENS", 12000, 2048, 65536),
    )


def build_assistant_model_adapter() -> AssistantModelAdapter:
    """Build from server environment only; callers never supply model secrets."""
    provider = os.getenv("MOLECULAR_ASSISTANT_MODEL_PROVIDER", "disabled").strip().lower()
    if provider == "deepseek":
        base_url = os.getenv("MOLECULAR_ASSISTANT_MODEL_BASE_URL", "https://api.deepseek.com").strip() or "https://api.deepseek.com"
        api_key = os.getenv("MOLECULAR_ASSISTANT_MODEL_API_KEY", "").strip()
        model = os.getenv("MOLECULAR_ASSISTANT_MODEL_NAME", "deepseek-v4-flash").strip() or "deepseek-v4-flash"
        if model not in {"deepseek-v4-flash", "deepseek-v4-pro"}:
            return UnsupportedAssistantModelAdapter()
        if not api_key:
            return DisabledAssistantModelAdapter()
        return DeepSeekAssistantModelAdapter(base_url, api_key, model, assistant_runtime_limits().timeout_seconds)
    if provider == "openai_compatible":
        base_url = os.getenv("MOLECULAR_ASSISTANT_MODEL_BASE_URL", "").strip()
        api_key = os.getenv("MOLECULAR_ASSISTANT_MODEL_API_KEY", "").strip()
        model = os.getenv("MOLECULAR_ASSISTANT_MODEL_NAME", "").strip()
        if not base_url or not api_key or not model:
            return DisabledAssistantModelAdapter()
        return OpenAICompatibleAssistantModelAdapter(base_url, api_key, model, assistant_runtime_limits().timeout_seconds)
    return DisabledAssistantModelAdapter()

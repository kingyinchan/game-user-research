from __future__ import annotations

import os
from typing import Any

from openai import OpenAI


class LLMService:
    """Thin OpenAI-compatible wrapper used by agent tasks."""

    def __init__(
        self,
        client: OpenAI | None,
        model: str,
        temperature: float,
        max_tokens: int,
        reasoning_effort: str | None = None,
        provider_extra_body: dict[str, Any] | None = None,
    ):
        self.client = client
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.reasoning_effort = reasoning_effort
        self.provider_extra_body = provider_extra_body or None

    @classmethod
    def from_config(cls, llm_config: dict[str, Any] | None = None) -> "LLMService | None":
        llm_config = llm_config or {}
        if not llm_config.get("enabled", False):
            return None

        api_key_env = llm_config.get("api_key_env")
        base_url_env = llm_config.get("base_url_env")
        model_env = llm_config.get("model_env")

        api_key = llm_config.get("api_key", "")
        if not api_key:
            api_key = os.getenv(api_key_env, "") if api_key_env else os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            return None

        base_url = ""
        if base_url_env:
            base_url = os.getenv(base_url_env, "")
        if not base_url:
            base_url = llm_config.get("base_url", "") or os.getenv("OPENAI_BASE_URL", "https://api.groq.com/openai/v1")

        model = ""
        if model_env:
            model = os.getenv(model_env, "")
        if not model:
            model = llm_config.get("model", "") or os.getenv("OPENAI_MODEL", "llama-3.3-70b-versatile")

        client = OpenAI(api_key=api_key, base_url=base_url)
        return cls(
            client=client,
            model=model,
            temperature=float(llm_config.get("temperature", 0.2)),
            max_tokens=int(llm_config.get("max_tokens", 1200)),
            reasoning_effort=str(llm_config.get("reasoning_effort", "")).strip() or None,
            provider_extra_body=llm_config.get("extra_body") if isinstance(llm_config.get("extra_body"), dict) else None,
        )

    def is_available(self) -> bool:
        return self.client is not None

    def generate_text(self, system_prompt: str, user_prompt: str) -> str:
        if self.client is None:
            raise RuntimeError("LLM service is not available.")

        request_kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if self.reasoning_effort:
            request_kwargs["reasoning_effort"] = self.reasoning_effort
        if self.provider_extra_body:
            request_kwargs["extra_body"] = {"extra_body": self.provider_extra_body}

        try:
            response = self.client.chat.completions.create(
                **request_kwargs,
            )
        except TypeError as exc:
            if self.reasoning_effort and "reasoning_effort" in str(exc):
                request_kwargs.pop("reasoning_effort", None)
                response = self.client.chat.completions.create(
                    **request_kwargs,
                )
            else:
                raise
        choice = response.choices[0]
        content = choice.message.content
        if isinstance(content, list):
            text_parts = [part.text for part in content if getattr(part, "text", None)]
            content_text = "\n".join(text_parts).strip()
        else:
            content_text = (content or "").strip()

        finish_reason = str(getattr(choice, "finish_reason", "") or "").lower()
        if finish_reason in {"length", "max_tokens"}:
            raise RuntimeError(
                f"LLM 输出被截断（finish_reason={finish_reason}）。请提高 max_tokens 或缩小 commentary payload。"
            )

        if not content_text:
            raise RuntimeError("LLM 没有返回可用文本内容。")

        return content_text

from __future__ import annotations

import os
from typing import Any

from openai import OpenAI


class LLMService:
    """Thin OpenAI-compatible wrapper used by agent tasks."""

    def __init__(self, client: OpenAI | None, model: str, temperature: float, max_tokens: int):
        self.client = client
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

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
        )

    def is_available(self) -> bool:
        return self.client is not None

    def generate_text(self, system_prompt: str, user_prompt: str) -> str:
        if self.client is None:
            raise RuntimeError("LLM service is not available.")

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        return response.choices[0].message.content.strip()

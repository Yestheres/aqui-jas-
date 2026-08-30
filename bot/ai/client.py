from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass(frozen=True, slots=True)
class AIConfig:
    api_key: str
    base_url: str
    model: str


class AIClient:
    """OpenAI-compatible Chat Completions client."""

    def __init__(self, config: AIConfig) -> None:
        self.config = config

    async def chat(self, messages: list[dict[str, str]], *, temperature: float = 0.2) -> str:
        url = self.config.base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature,
        }
        headers = {"Authorization": f"Bearer {self.config.api_key}"}

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("Resposta inesperada do provedor de IA.") from exc

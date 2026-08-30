from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass(slots=True, frozen=True)
class AIConfig:
    api_key: str
    base_url: str
    model: str


class AIClient:
    """Minimal OpenAI-compatible client; works with providers exposing Chat Completions."""

    def __init__(self, config: AIConfig) -> None:
        self.config = config

    async def chat(self, system: str, user: str) -> str:
        url = self.config.base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        headers = {"Authorization": f"Bearer {self.config.api_key}"}
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        return str(data["choices"][0]["message"]["content"])

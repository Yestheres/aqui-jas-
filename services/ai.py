from __future__ import annotations

import json
import logging
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


def fallback_ai_description(server_name: str, summary: str, focus: str = "comunidade") -> str:
    base_summary = summary.strip() or "focamos em criar uma comunidade ativa e acolhedora."
    return (
        f"Olá! Somos {server_name} e estamos em busca de parcerias que fortaleçam nossa comunidade e tragam valor para ambos os lados. "
        f"{base_summary} Nosso foco está em {focus}, com boa convivência, troca de experiências e crescimento mútuo. "
        "Estamos abertos a colaborações, eventos, suporte à comunidade e oportunidades de alcance junto à nossa base."
    )


def generate_ai_description(server_name: str, summary: str, focus: str = "comunidade") -> str:
    cleaned_name = (server_name or "nosso servidor").strip()
    cleaned_summary = (summary or "").strip()
    cleaned_focus = (focus or "comunidade").strip()

    if not cleaned_name and not cleaned_summary:
        return "Descrição não disponível. Informe o nome do servidor e o resumo da parceria."

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return fallback_ai_description(cleaned_name or "nosso servidor", cleaned_summary, cleaned_focus)

    model = os.getenv("OPENAI_MODEL", "glm-4.5-flash")
    base_url = os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Você é uma IA especializada em melhorar descrições de servidores Discord. "
                    "Não invente fatos que não foram informados. Apenas embeleze a descrição, use emojis de forma natural e mantenha a proposta fiel ao que foi dito. "
                    "Responda em português, sem listas longas, sem mentir e sem mencionar que você é IA."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Melhore a descrição de parceria do servidor {cleaned_name}. "
                    f"Contexto: {cleaned_summary or 'servidor focado em comunidade, eventos e troca de conhecimento'}. "
                    f"Foco principal: {cleaned_focus}. "
                    "Deixe o texto mais bonito, acolhedor e persuasivo, mantendo a honestidade e adicionando emojis sem exagero."
                ),
            },
        ],
        "temperature": 0.7,
    }

    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=20) as response:
            payload_response = json.loads(response.read().decode("utf-8"))
            content = payload_response["choices"][0]["message"]["content"].strip()
            if content:
                return content
    except (HTTPError, URLError, KeyError, ValueError, TimeoutError) as exc:
        logger.warning("Falha ao gerar descrição com IA: %s", exc)

    return fallback_ai_description(cleaned_name or "nosso servidor", cleaned_summary, cleaned_focus)

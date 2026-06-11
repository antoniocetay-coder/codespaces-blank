"""Cliente HTTP único para OpenRouter.

Centraliza todas as chamadas ao endpoint /chat/completions para evitar
repetição de boilerplate nos call sites. Suporta o flag `reasoning`
usado pelos modelos Xiaomi MiMo.
"""

import json
import requests
from config import OPENROUTER_BASE_URL


def _post(messages, model, api_key, temperature=0.4, reasoning=False):
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if reasoning:
        payload["reasoning"] = {"enabled": True}

    response = requests.post(
        f"{OPENROUTER_BASE_URL}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        data=json.dumps(payload),
        timeout=180,
    )
    response.raise_for_status()
    data = response.json()
    return data["choices"][0]["message"]


def chat_text(prompt, model, api_key, temperature=0.4, reasoning=False):
    """Retorna o conteúdo textual da resposta."""
    msg = _post(
        [{"role": "user", "content": prompt}],
        model, api_key, temperature, reasoning,
    )
    return msg.get("content") or ""


def chat_json(prompt, model, api_key, temperature=0.4, reasoning=False):
    """Retorna string crua; limpar_json() cuida de blocos ```json```."""
    return chat_text(prompt, model, api_key, temperature, reasoning)

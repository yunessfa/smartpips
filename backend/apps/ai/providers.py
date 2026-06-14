"""
A thin OpenAI-compatible chat client that works with DeepSeek, OpenAI,
OpenRouter, Groq, or any custom compatible endpoint.
"""
import requests


class AIClientError(Exception):
    pass


def chat_completion(provider, messages: list[dict]) -> str:
    """Call the provider's /chat/completions endpoint and return the text reply.

    `provider` is an AIProvider instance.
    `messages` is a list of {"role": ..., "content": ...} dicts.
    """
    if not provider.api_key and provider.provider_type != "ollama":
        raise AIClientError(
            "No API key set for the active AI provider. Add one on the AI page."
        )

    base = provider.base_url.rstrip("/")
    url = f"{base}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {provider.api_key or 'ollama'}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": provider.model,
        "messages": messages,
        "temperature": provider.temperature,
        "max_tokens": 3500,
        "stream": False,
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=60)
    except requests.RequestException as exc:
        raise AIClientError(f"Could not reach the AI provider: {exc}") from exc

    if resp.status_code >= 400:
        raise AIClientError(
            f"AI provider returned {resp.status_code}: {resp.text[:300]}"
        )

    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise AIClientError(f"Unexpected response shape from provider: {data}") from exc

"""
A thin OpenAI-compatible chat client that works with DeepSeek, OpenAI, OpenRouter,
Groq, GitHub Models, Ollama, or any custom compatible endpoint. Also surfaces
rate-limit info so the UI can warn when a free quota is running low.
"""
import requests


class AIClientError(Exception):
    pass


def _extract_rate_limit(headers) -> dict:
    """Collect any rate-limit / quota headers the provider returns."""
    info = {}
    for k, v in headers.items():
        lk = k.lower()
        if "ratelimit" in lk or "rate-limit" in lk or lk == "retry-after":
            info[lk] = v
    return info


def _summarise_rate(info: dict) -> str:
    """Human one-liner from whatever rate headers we found."""
    if not info:
        return ""
    remaining = (info.get("x-ratelimit-remaining-requests")
                 or info.get("x-ratelimit-remaining")
                 or info.get("ratelimit-remaining"))
    limit = (info.get("x-ratelimit-limit-requests")
             or info.get("x-ratelimit-limit")
             or info.get("ratelimit-limit"))
    reset = (info.get("x-ratelimit-reset")
             or info.get("ratelimit-reset")
             or info.get("retry-after"))
    parts = []
    if remaining is not None and limit is not None:
        parts.append(f"{remaining}/{limit} requests left")
    elif remaining is not None:
        parts.append(f"{remaining} requests left")
    if reset:
        parts.append(f"resets in ~{reset}s")
    return ", ".join(parts)


def _post(provider, messages, max_tokens=3500):
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
        "max_tokens": max_tokens,
        "stream": False,
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=90)
    except requests.RequestException as exc:
        raise AIClientError(f"Could not reach the AI provider: {exc}") from exc

    rate = _extract_rate_limit(resp.headers)

    if resp.status_code == 429:
        retry = resp.headers.get("retry-after")
        extra = f" Try again in ~{retry}s." if retry else ""
        raise AIClientError(
            "Rate limit reached for this model (free quota)." + extra
            + " Switch model or wait a bit."
        )
    if resp.status_code >= 400:
        raise AIClientError(
            f"AI provider returned {resp.status_code}: {resp.text[:300]}"
        )

    data = resp.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise AIClientError(f"Unexpected response shape from provider: {data}") from exc
    return content, rate


def chat_completion(provider, messages: list[dict]) -> str:
    """Return the assistant text reply (raises AIClientError on failure)."""
    content, _rate = _post(provider, messages)
    return content


def test_provider(provider) -> dict:
    """Tiny ping that also reports remaining quota when the provider exposes it."""
    content, rate = _post(
        provider,
        [{"role": "user", "content": "Reply with the single word: OK"}],
        max_tokens=20,
    )
    return {"ok": True, "reply": content.strip(), "rate": _summarise_rate(rate), "rate_raw": rate}

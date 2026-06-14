"""
Reads recent posts from PUBLIC Telegram channels via the t.me/s/ web preview.
No bot token required. Network errors are swallowed so the app works offline.
"""
import re
from html import unescape

import requests

from .models import TelegramChannel

# Each message body sits in <div class="tgme_widget_message_text ...">...</div>
_MSG_RE = re.compile(
    r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
    re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")


def _clean(html: str) -> str:
    text = html.replace("<br/>", "\n").replace("<br>", "\n")
    text = _TAG_RE.sub("", text)
    return unescape(text).strip()


def fetch_channel_messages(username: str, limit: int = 5) -> list[dict]:
    username = username.lstrip("@").strip()
    if not username:
        return []
    url = f"https://t.me/s/{username}"
    try:
        resp = requests.get(
            url, timeout=6, headers={"User-Agent": "Mozilla/5.0 (SmartPips)"}
        )
        resp.raise_for_status()
    except requests.RequestException:
        return []

    messages = []
    for raw in _MSG_RE.findall(resp.text):
        text = _clean(raw)
        if text:
            messages.append({"channel": username, "text": text[:400]})
    # newest posts are last in the page
    return messages[-limit:]


def gather_telegram_signals(limit_per_channel: int = 5, max_total: int = 12) -> list[dict]:
    signals = []
    for ch in TelegramChannel.objects.filter(is_active=True):
        signals.extend(fetch_channel_messages(ch.username, limit_per_channel))
    return signals[:max_total]

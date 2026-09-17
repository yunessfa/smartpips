"""
Reads recent headlines from active sources that have an RSS/Atom `feed_url`.

Uses only the standard library + requests so there is no extra dependency.
Network failures are swallowed gracefully so the assistant still works offline.
"""
import re
from xml.etree import ElementTree as ET

import requests

from .models import Source

# Strip HTML tags from RSS summaries.
_TAG_RE = re.compile(r"<[^>]+>")


def _clean(text: str) -> str:
    if not text:
        return ""
    return _TAG_RE.sub("", text).strip()


def _parse_feed(xml_text: str, limit: int) -> list[dict]:
    items = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items

    # RSS 2.0 -> channel/item ; Atom -> entry
    nodes = root.findall(".//item")
    is_atom = False
    if not nodes:
        # Atom uses a default namespace; match by local tag name.
        nodes = [el for el in root.iter() if el.tag.endswith("entry")]
        is_atom = True

    for node in nodes[:limit]:
        if is_atom:
            title = node.findtext("{*}title") or ""
            link_el = node.find("{*}link")
            link = link_el.get("href") if link_el is not None else ""
            summary = node.findtext("{*}summary") or node.findtext("{*}content") or ""
            published = node.findtext("{*}updated") or node.findtext("{*}published") or ""
        else:
            title = node.findtext("title") or ""
            link = node.findtext("link") or ""
            summary = node.findtext("description") or ""
            published = node.findtext("pubDate") or ""

        items.append(
            {
                "title": _clean(title),
                "link": link.strip(),
                "summary": _clean(summary)[:280],
                "published": published.strip(),
            }
        )
    return items


def fetch_source_headlines(source: Source, limit: int = 4) -> list[dict]:
    if not source.feed_url:
        return []
    try:
        resp = requests.get(
            source.feed_url,
            timeout=6,
            headers={"User-Agent": "SmartPips/1.0 (+news reader)"},
        )
        resp.raise_for_status()
    except requests.RequestException:
        return []
    headlines = _parse_feed(resp.text, limit)
    for h in headlines:
        h["source"] = source.name
        h["weight"] = source.weight
    return headlines


def gather_news(limit_per_source: int = 4, max_total: int = 14) -> list[dict]:
    """Collect recent headlines across all active sources with a feed."""
    news = []
    for source in Source.objects.filter(is_active=True).exclude(feed_url=""):
        news.extend(fetch_source_headlines(source, limit_per_source))
    # Highest-trust sources first, then truncate.
    news.sort(key=lambda h: h.get("weight", 0), reverse=True)
    return news[:max_total]

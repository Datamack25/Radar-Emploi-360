"""Recherche web de secours (quand l'IA n'a pas de recherche native) : SerpApi (Google) ou Tavily.

Utilise la même clé SERPAPI_KEY que Google Emploi, ou TAVILY_API_KEY.
"""
from __future__ import annotations

import os

import requests


def _serpapi(q: str, n: int = 5) -> list[dict]:
    key = os.environ.get("SERPAPI_KEY", "").strip()
    if not key:
        return []
    r = requests.get("https://serpapi.com/search.json", timeout=30,
                     params={"engine": "google", "q": q, "hl": "fr", "gl": "fr", "num": n, "api_key": key})
    if r.status_code != 200:
        return []
    return [{"title": x.get("title", ""), "url": x.get("link", ""), "snippet": x.get("snippet", "")}
            for x in (r.json().get("organic_results") or [])[:n] if x.get("link")]


def _tavily(q: str, n: int = 5) -> list[dict]:
    key = os.environ.get("TAVILY_API_KEY", "").strip()
    if not key:
        return []
    r = requests.post("https://api.tavily.com/search", timeout=40,
                      json={"api_key": key, "query": q, "max_results": n, "search_depth": "basic"})
    if r.status_code != 200:
        return []
    return [{"title": x.get("title", ""), "url": x.get("url", ""), "snippet": (x.get("content") or "")[:500]}
            for x in r.json().get("results") or [] if x.get("url")]


def available() -> bool:
    return bool(os.environ.get("SERPAPI_KEY", "").strip() or os.environ.get("TAVILY_API_KEY", "").strip())


def search(q: str, n: int = 5) -> list[dict]:
    try:
        return _tavily(q, n) or _serpapi(q, n)
    except requests.RequestException:
        return []


def search_many(queries: list[str], n: int = 4) -> list[dict]:
    out, seen = [], set()
    for q in queries:
        for r in search(q, n):
            if r["url"] not in seen:
                seen.add(r["url"])
                out.append(r)
    return out[:20]

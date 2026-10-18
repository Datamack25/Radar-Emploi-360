"""Accès aux modèles d'IA, sans SDK (requêtes HTTP directes) : Gemini, Claude (Anthropic), OpenAI, Ollama (local).

- complete()  : génération de texte (option JSON).
- research()  : génération appuyée sur une recherche web, avec la liste des sources (liens).
               Gemini (Google Search), Claude (web search) et OpenAI (web search) la font nativement ;
               sinon, la recherche passe par SerpApi ou Tavily (services/websearch.py) et l'IA rédige à partir des extraits.

Le fournisseur est choisi par LLM_PROVIDER (secrets / .env) ou, à défaut, le premier dont la clé est présente.
"""
from __future__ import annotations

import json
import os
import re

import requests

PROVIDERS = {
    "gemini": {"label": "Google Gemini", "key": "GEMINI_API_KEY", "model_env": "GEMINI_MODEL", "model": "gemini-2.5-flash",
               "web": True},
    "anthropic": {"label": "Claude (Anthropic)", "key": "ANTHROPIC_API_KEY", "model_env": "ANTHROPIC_MODEL",
                  "model": "claude-sonnet-5-5", "web": True},
    "openai": {"label": "OpenAI", "key": "OPENAI_API_KEY", "model_env": "OPENAI_MODEL", "model": "gpt-4.1-mini", "web": True},
    "ollama": {"label": "Ollama (local)", "key": "OLLAMA_HOST", "model_env": "OLLAMA_MODEL", "model": "mistral", "web": False},
}


class LLMError(Exception):
    pass


def available_providers() -> list[str]:
    return [p for p, d in PROVIDERS.items() if os.environ.get(d["key"], "").strip()]


def default_provider() -> str | None:
    wanted = os.environ.get("LLM_PROVIDER", "").strip().lower()
    av = available_providers()
    if wanted in av:
        return wanted
    return av[0] if av else None


def parse_json(text: str):
    """Extrait le premier objet ou tableau JSON d'une réponse (tolère ```json ... ```)."""
    t = str(text or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.M).strip()
    try:
        return json.loads(t)
    except ValueError:
        pass
    for open_c, close_c in (("{", "}"), ("[", "]")):
        i, j = t.find(open_c), t.rfind(close_c)
        if i != -1 and j > i:
            try:
                return json.loads(t[i:j + 1])
            except ValueError:
                continue
    raise LLMError("Réponse de l'IA illisible (JSON attendu).")


class LLM:
    def __init__(self, provider: str | None = None, timeout: int = 180):
        self.provider = provider if provider in PROVIDERS else default_provider()
        self.timeout = timeout

    # ------------------------------------------------------------------ infos
    @property
    def ok(self) -> bool:
        return bool(self.provider and os.environ.get(PROVIDERS[self.provider]["key"], "").strip())

    @property
    def label(self) -> str:
        return f"{PROVIDERS[self.provider]['label']} · {self.model}" if self.ok else "Aucune IA configurée"

    @property
    def model(self) -> str:
        d = PROVIDERS.get(self.provider or "", {})
        return os.environ.get(d.get("model_env", ""), "").strip() or d.get("model", "")

    @property
    def native_web(self) -> bool:
        return self.ok and PROVIDERS[self.provider]["web"]

    def _key(self) -> str:
        return os.environ.get(PROVIDERS[self.provider]["key"], "").strip()

    # ------------------------------------------------------------------ appels
    def complete(self, system: str, prompt: str, json_mode: bool = False, max_tokens: int = 4096, temperature: float = 0.3):
        if not self.ok:
            raise LLMError("Aucune IA configurée (ajoutez une clé GEMINI_API_KEY, ANTHROPIC_API_KEY, OPENAI_API_KEY ou OLLAMA_HOST).")
        if json_mode:
            system += "\n\nRéponds UNIQUEMENT avec un objet JSON valide, sans texte autour."
        text = getattr(self, f"_{self.provider}")(system, prompt, json_mode, max_tokens, temperature, web=False)[0]
        return parse_json(text) if json_mode else text

    def research(self, system: str, prompt: str, max_tokens: int = 6000) -> tuple[str, list[dict]]:
        """Texte + sources [{title, url}] ; utilise la recherche web native si le fournisseur la propose."""
        if not self.ok:
            raise LLMError("Aucune IA configurée.")
        if self.native_web:
            try:
                return getattr(self, f"_{self.provider}")(system, prompt, False, max_tokens, 0.2, web=True)
            except LLMError:
                pass  # repli : recherche externe puis rédaction
        from .websearch import search_many
        queries = [q for q in re.findall(r"RECHERCHE:\s*(.+)", prompt)][:6] or [prompt[:180]]
        results = search_many(queries)
        if not results:
            text, _ = getattr(self, f"_{self.provider}")(
                system + "\n\nAucune recherche web n'a pu être faite : signale clairement les informations à vérifier.",
                prompt, False, max_tokens, 0.2, web=False)
            return text, []
        ctx = "\n".join(f"[{i + 1}] {r['title']} — {r['url']}\n{r.get('snippet', '')}" for i, r in enumerate(results))
        text, _ = getattr(self, f"_{self.provider}")(
            system + "\n\nAppuie-toi sur les extraits web numérotés fournis et cite-les sous la forme [n].",
            f"{prompt}\n\nEXTRAITS WEB :\n{ctx}", False, max_tokens, 0.2, web=False)
        return text, [{"title": r["title"], "url": r["url"]} for r in results]

    # ------------------------------------------------------------------ fournisseurs
    def _post(self, url, **kw):
        try:
            r = requests.post(url, timeout=self.timeout, **kw)
        except requests.RequestException as exc:
            raise LLMError(f"{PROVIDERS[self.provider]['label']} injoignable : {type(exc).__name__}") from exc
        if r.status_code >= 400:
            raise LLMError(f"{PROVIDERS[self.provider]['label']} : HTTP {r.status_code} — {r.text[:300]}")
        try:
            return r.json()
        except ValueError as exc:
            raise LLMError("Réponse illisible du fournisseur d'IA.") from exc

    def _gemini(self, system, prompt, json_mode, max_tokens, temperature, web=False):
        body = {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens}}
        if json_mode and not web:
            body["generationConfig"]["responseMimeType"] = "application/json"
        if web:
            body["tools"] = [{"google_search": {}}]
        j = self._post(f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
                       headers={"x-goog-api-key": self._key(), "Content-Type": "application/json"}, json=body)
        cand = (j.get("candidates") or [{}])[0]
        text = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []))
        if not text:
            raise LLMError(f"Gemini n'a rien renvoyé ({cand.get('finishReason', 'raison inconnue')}).")
        sources, seen = [], set()
        for ch in (cand.get("groundingMetadata") or {}).get("groundingChunks", []) or []:
            w = ch.get("web") or {}
            if w.get("uri") and w["uri"] not in seen:
                seen.add(w["uri"])
                sources.append({"title": w.get("title") or w["uri"], "url": w["uri"]})
        return text, sources

    def _anthropic(self, system, prompt, json_mode, max_tokens, temperature, web=False):
        body = {"model": self.model, "max_tokens": max_tokens, "system": system,
                "messages": [{"role": "user", "content": prompt}]}
        if web:
            body["tools"] = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 6}]
        else:
            body["temperature"] = temperature
        j = self._post("https://api.anthropic.com/v1/messages",
                       headers={"x-api-key": self._key(), "anthropic-version": "2023-06-01", "content-type": "application/json"},
                       json=body)
        parts, sources, seen = [], [], set()
        for b in j.get("content", []):
            if b.get("type") == "text":
                parts.append(b.get("text", ""))
                for c in b.get("citations") or []:
                    if c.get("url") and c["url"] not in seen:
                        seen.add(c["url"])
                        sources.append({"title": c.get("title") or c["url"], "url": c["url"]})
            elif b.get("type") == "web_search_tool_result" and isinstance(b.get("content"), list):
                for res in b["content"]:
                    if res.get("url") and res["url"] not in seen:
                        seen.add(res["url"])
                        sources.append({"title": res.get("title") or res["url"], "url": res["url"]})
        text = "".join(parts).strip()
        if not text:
            raise LLMError("Claude n'a rien renvoyé.")
        return text, sources

    def _openai(self, system, prompt, json_mode, max_tokens, temperature, web=False):
        h = {"Authorization": f"Bearer {self._key()}", "Content-Type": "application/json"}
        if web:
            j = self._post("https://api.openai.com/v1/responses", headers=h,
                           json={"model": self.model, "instructions": system, "input": prompt,
                                 "tools": [{"type": "web_search"}], "max_output_tokens": max_tokens})
            parts, sources, seen = [], [], set()
            for item in j.get("output", []):
                if item.get("type") != "message":
                    continue
                for c in item.get("content", []):
                    if c.get("type") == "output_text":
                        parts.append(c.get("text", ""))
                        for a in c.get("annotations") or []:
                            if a.get("type") == "url_citation" and a.get("url") not in seen:
                                seen.add(a["url"])
                                sources.append({"title": a.get("title") or a["url"], "url": a["url"]})
            text = "".join(parts).strip()
            if not text:
                raise LLMError("OpenAI n'a rien renvoyé.")
            return text, sources
        body = {"model": self.model, "temperature": temperature, "max_tokens": max_tokens,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        j = self._post("https://api.openai.com/v1/chat/completions", headers=h, json=body)
        return j["choices"][0]["message"]["content"], []

    def _ollama(self, system, prompt, json_mode, max_tokens, temperature, web=False):
        host = self._key().rstrip("/")
        if not host.startswith("http"):
            host = "http://" + host
        body = {"model": self.model, "stream": False, "options": {"temperature": temperature, "num_predict": max_tokens},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]}
        if json_mode:
            body["format"] = "json"
        j = self._post(f"{host}/api/chat", json=body)
        return (j.get("message") or {}).get("content", ""), []

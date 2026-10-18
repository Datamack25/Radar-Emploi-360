"""API officielle Jooble (agrégateur d'offres ; clé gratuite JOOBLE_KEY sur jooble.org/api/about)."""
from __future__ import annotations

import os
import re

from ..http import Http, HttpError
from ..text import html_to_text

URL = "https://jooble.org/api/{key}"


def _iso(s) -> str | None:
    s = str(s or "").strip()
    if not s:
        return None
    s = re.sub(r"(\.\d{6})\d+", r"\1", s)  # Jooble renvoie 7 décimales
    return s if re.match(r"\d{4}-\d{2}-\d{2}", s) else None


def _normalize(j: dict) -> dict:
    return {
        "source": "jooble", "source_id": str(j.get("id") or j.get("link")), "title": html_to_text(j.get("title", "")),
        "company": j.get("company") or "Entreprise non communiquée", "location": j.get("location", ""),
        "description": html_to_text(j.get("snippet", "")), "posted_at": _iso(j.get("updated")),
        "url": j.get("link"), "apply_url": j.get("link"), "logo": None,
        "raw": {"loc_all": j.get("location", ""), "country": None, "employment": j.get("type") or "",
                "salary_text": j.get("salary") or ""},
        "extra": {"via": j.get("source") or ""},
    }


def fetch(cfg, http: Http, progress) -> tuple[list[dict], list[str]]:
    key = os.environ.get("JOOBLE_KEY", "").strip()
    out, warns, seen = [], [], set()
    pages = int(cfg.recherche.get("pages_jooble", 2))
    for kw in cfg.recherche.get("mots_cles", []):
        n_kw = 0
        for p in range(1, pages + 1):
            r = http.request("POST", URL.format(key=key), json={"keywords": kw, "location": "France", "page": str(p)})
            if r.status_code in (401, 403):
                raise HttpError("clé Jooble refusée (vérifiez JOOBLE_KEY)")
            if r.status_code != 200:
                warns.append(f"« {kw} » : HTTP {r.status_code}")
                break
            jobs = (r.json() or {}).get("jobs") or []
            for j in jobs:
                o = _normalize(j)
                if o["source_id"] not in seen:
                    seen.add(o["source_id"])
                    out.append(o)
                    n_kw += 1
            if len(jobs) < 20:
                break
        progress(f"Jooble · « {kw} » : {n_kw} offre(s) lue(s)")
    return out, warns

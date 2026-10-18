"""Google Emploi (Google for Jobs) via l'API SerpApi (clé SERPAPI_KEY, offre gratuite limitée).

Google Emploi regroupe les offres publiées sur LinkedIn, Indeed, Welcome to the Jungle, HelloWork, APEC,
Jobteaser, les sites carrières des employeurs, etc. : c'est la façon autorisée d'en couvrir le plus possible.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone

from ..http import Http, HttpError
from ..text import norm

URL = "https://serpapi.com/search.json"
AGGREGATORS = ("linkedin", "indeed", "glassdoor", "jooble", "talent.com", "jobrapido", "optioncarriere", "adzuna",
               "monster", "hellowork", "meteojob", "jobijoba", "neuvoo", "whatjobs", "trovit")


def relative_date(txt) -> str | None:
    """« il y a 3 jours », « 3 days ago », « il y a 5 heures », « il y a 30+ jours » -> date ISO."""
    t = norm(txt)
    if not t:
        return None
    now = datetime.now(timezone.utc)
    m = re.search(r"(\d+)\+?\s*(minute|min|heure|hour|h\b|jour|day|j\b|semaine|week|mois|month)", t)
    if not m:
        return now.isoformat() if re.search(r"aujourd|today|instant|just", t) else None
    n, unit = int(m.group(1)), m.group(2)
    delta = (timedelta(minutes=n) if unit.startswith("min") else timedelta(hours=n) if unit in ("heure", "hour", "h")
             else timedelta(weeks=n) if unit in ("semaine", "week") else timedelta(days=30 * n) if unit in ("mois", "month")
             else timedelta(days=n))
    return (now - delta).isoformat()


def _best_link(options: list) -> str | None:
    """Préfère le lien de l'employeur ; sinon le premier site d'offres proposé."""
    opts = [o for o in options or [] if o.get("link", "").startswith("http")]
    for o in opts:
        if not any(a in norm(o.get("title", "") + " " + o.get("link", "")) for a in AGGREGATORS):
            return o["link"]
    return opts[0]["link"] if opts else None


def _normalize(j: dict) -> dict:
    ext = j.get("detected_extensions") or {}
    exts = " ".join(str(x) for x in j.get("extensions") or [])
    highlights = "\n".join(f"{h.get('title', '')}\n" + "\n".join(f"• {i}" for i in h.get("items") or [])
                           for h in j.get("job_highlights") or [])
    desc = (j.get("description") or "") + ("\n\n" + highlights if highlights else "")
    apply = _best_link(j.get("apply_options"))
    url = apply or j.get("share_link")
    via = re.sub(r"^(via|par)\s+", "", str(j.get("via") or ""), flags=re.I)
    return {
        "source": "google", "source_id": str(j.get("job_id") or f"{j.get('title')}|{j.get('company_name')}")[:300],
        "title": j.get("title", ""), "company": j.get("company_name") or "Entreprise non communiquée",
        "location": j.get("location", ""), "description": desc, "posted_at": relative_date(ext.get("posted_at") or exts),
        "url": url, "apply_url": apply or url, "logo": j.get("thumbnail"),
        "raw": {"loc_all": j.get("location", ""), "country": None,
                "employment": " ".join(filter(None, [ext.get("schedule_type"), exts])),
                "salary_text": ext.get("salary") or ""},
        "extra": {"via": via, "google_link": j.get("share_link"),
                  "candidater": [{"site": o.get("title", ""), "url": o.get("link", "")} for o in (j.get("apply_options") or [])[:6]]},
    }


def fetch(cfg, http: Http, progress) -> tuple[list[dict], list[str]]:
    key = os.environ.get("SERPAPI_KEY", "").strip()
    out, warns, seen = [], [], set()
    kws = cfg.recherche.get("mots_cles_google") or cfg.recherche.get("mots_cles", [])
    pages = int(cfg.recherche.get("pages_google", 1))
    for kw in kws:
        token, n_kw = None, 0
        for _ in range(pages):
            params = {"engine": "google_jobs", "q": kw, "location": "France", "gl": "fr", "hl": "fr",
                      "google_domain": "google.fr", "api_key": key}
            if token:
                params["next_page_token"] = token
            r = http.get(URL, params=params)
            if r.status_code == 401:
                raise HttpError("clé SerpApi refusée (vérifiez SERPAPI_KEY)")
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            if data.get("error"):
                if "hasn't returned any results" in data["error"]:
                    break
                if re.search(r"run out|plan|limit", data["error"], re.I):
                    raise HttpError(f"quota SerpApi épuisé : {data['error']}")
                warns.append(f"« {kw} » : {data['error']}")
                break
            if r.status_code != 200:
                warns.append(f"« {kw} » : HTTP {r.status_code}")
                break
            for j in data.get("jobs_results") or []:
                o = _normalize(j)
                if o["source_id"] not in seen:
                    seen.add(o["source_id"])
                    out.append(o)
                    n_kw += 1
            token = (data.get("serpapi_pagination") or {}).get("next_page_token")
            if not token:
                break
        progress(f"Google Emploi · « {kw} » : {n_kw} offre(s) lue(s)")
    return out, warns

"""API officielle Adzuna (index France : /jobs/fr/)."""
from __future__ import annotations

import os

from ..http import Http, HttpError
from ..text import html_to_text

URL = "https://api.adzuna.com/v1/api/jobs/fr/search/{page}"


def _normalize(j: dict) -> dict:
    loc = j.get("location") or {}
    predicted = str(j.get("salary_is_predicted", "0")) == "1"
    smin, smax = j.get("salary_min"), j.get("salary_max")
    sal = None if predicted or not (smin or smax) else (int(smin or smax), int(smax or smin))
    return {
        "source": "adzuna", "source_id": str(j.get("id")), "title": html_to_text(j.get("title", "")),
        "company": (j.get("company") or {}).get("display_name") or "Entreprise non communiquée",
        "location": loc.get("display_name", ""), "description": html_to_text(j.get("description", "")),
        "posted_at": j.get("created"), "url": j.get("redirect_url"), "apply_url": j.get("redirect_url"), "logo": None,
        "raw": {"area": loc.get("area") or [], "contract_type": j.get("contract_type"),
                "employment": " ".join(filter(None, [j.get("contract_type"), j.get("contract_time")])), "salary": sal},
        "extra": {},
    }


def fetch(cfg, http: Http, progress) -> tuple[list[dict], list[str]]:
    app_id, app_key = os.environ.get("ADZUNA_APP_ID", "").strip(), os.environ.get("ADZUNA_APP_KEY", "").strip()
    out, warns, seen = [], [], set()
    pages = int(cfg.recherche.get("pages_adzuna", 2))
    for kw in cfg.recherche.get("mots_cles", []):
        n_kw = 0
        for p in range(1, pages + 1):
            params = {"app_id": app_id, "app_key": app_key, "results_per_page": 50, "what": kw,
                      "max_days_old": int(cfg.candidat.get("fraicheur_jours", 30)), "sort_by": "date",
                      "content-type": "application/json"}
            r = http.get(URL.format(page=p), params=params)
            if r.status_code in (401, 403):
                raise HttpError("clés Adzuna refusées (vérifiez ADZUNA_APP_ID et ADZUNA_APP_KEY)")
            if r.status_code != 200:
                warns.append(f"« {kw} » : HTTP {r.status_code}")
                break
            res = (r.json() or {}).get("results") or []
            for j in res:
                if j.get("id") and j["id"] not in seen:
                    seen.add(j["id"])
                    out.append(_normalize(j))
                    n_kw += 1
            if len(res) < 50:
                break
        progress(f"Adzuna · « {kw} » : {n_kw} nouvelle(s) offre(s) lue(s)")
    return out, warns

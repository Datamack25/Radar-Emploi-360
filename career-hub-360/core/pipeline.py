"""Mise à jour : lecture des sources → filtres (France, métier, junior, contrat, salaire) → score → doublons → stockage."""
from __future__ import annotations

import os
import re
from collections import Counter

from .annuaire import load_annuaire
from .filters import evaluate
from .http import Http, HttpError
from .scoring import score
from .sources import adzuna, ats, france_travail, google_jobs, jooble
from .text import norm, norm_title

PRIORITY = {"ats": 0, "france_travail": 1, "google": 2, "jooble": 3, "adzuna": 4}


def ats_targets(cfg, store):
    ann = load_annuaire(cfg)
    found = store.tokens()
    targets = []
    for e in ann.employers:
        if e.token and e.ats in ats.PARSERS:
            targets.append((e, e.ats, e.token))
        elif e.nom in found and found[e.nom]["ats"] in ats.PARSERS:
            targets.append((e, found[e.nom]["ats"], found[e.nom]["token"]))
    return ann, targets


def _dkey(o) -> str:
    comp = re.sub(r"\b(sa|sas|sasu|se|group|groupe|france|bank|banque|the|&|et|cie)\b", " ", norm(o["company"]))
    comp = re.sub(r"[^a-z0-9]", "", comp)
    title = re.sub(r"\b(cdi|cdd|interim|junior|jr)\b|[^a-z0-9 ]", " ", norm_title(o["title"]))
    title = re.sub(r"\s+", " ", title).strip()
    return f"{comp}|{title}|{o.get('dept') or ''}"


def run_update(cfg, store, progress=print) -> dict:
    ann, targets = ats_targets(cfg, store)
    run_id = store.start_run()
    rep = {"per_source": [], "fetched": 0, "kept": 0, "duplicates_removed": 0, "expired": 0, "rejected": {}}
    raw_offers, ok_sources = [], set()

    def source(key, label, enabled, why_off, job):
        entry = {"key": key, "label": label, "status": "désactivée", "fetched": 0, "kept": 0, "warnings": [], "message": why_off}
        if enabled:
            try:
                offers, warns = job()
                entry.update(status="ok", fetched=len(offers), warnings=warns, message="")
                for o in offers:
                    o["_src_label"] = key
                raw_offers.extend(offers)
                ok_sources.add(key)
            except HttpError as exc:
                entry.update(status="erreur", message=str(exc))
                progress(f"⚠️ {label} : {exc}")
            except Exception as exc:  # noqa: BLE001
                entry.update(status="erreur", message=f"{type(exc).__name__} : {exc}")
                progress(f"⚠️ {label} : {type(exc).__name__} : {exc}")
        rep["per_source"].append(entry)

    http = Http(cfg.user_agent, delay=0.15)
    ft_on = bool(os.environ.get("FT_CLIENT_ID") and os.environ.get("FT_CLIENT_SECRET"))
    az_on = bool(os.environ.get("ADZUNA_APP_ID") and os.environ.get("ADZUNA_APP_KEY"))
    progress("Lecture de France Travail…")
    source("france_travail", "France Travail", ft_on, "Clés FT_CLIENT_ID / FT_CLIENT_SECRET absentes",
           lambda: france_travail.fetch(cfg, http, progress))
    g_on = bool(os.environ.get("SERPAPI_KEY"))
    progress("Lecture de Google Emploi…")
    source("google", "Google Emploi (LinkedIn, Indeed, WTTJ, HelloWork…)", g_on, "Clé SERPAPI_KEY absente",
           lambda: google_jobs.fetch(cfg, http, progress))
    progress("Lecture de Jooble…")
    source("jooble", "Jooble", bool(os.environ.get("JOOBLE_KEY")), "Clé JOOBLE_KEY absente",
           lambda: jooble.fetch(cfg, http, progress))
    progress("Lecture d'Adzuna…")
    source("adzuna", "Adzuna", az_on, "Clés ADZUNA_APP_ID / ADZUNA_APP_KEY absentes", lambda: adzuna.fetch(cfg, http, progress))

    def _ats():
        offers, warns, n_ok = ats.fetch(targets, Http(cfg.user_agent, delay=0.3), progress)
        if targets and not n_ok:
            raise HttpError("aucun site carrières n'a répondu")
        return offers, warns
    progress("Lecture des sites carrières…")
    source("ats", "Sites carrières des employeurs", bool(targets), "Aucun site carrières lisible : onglet Employeurs → « Trouver… »", _ats)

    rejected = Counter()
    kept = []
    for o in raw_offers:
        why = evaluate(o, cfg)
        if why:
            rejected[why] += 1
            continue
        o["category"], o["employeur"] = ann.category(o["company"])
        o["score"], o["breakdown"] = score(o, cfg)
        o["uid"] = f"{o['source']}:{o['source_id']}"
        o["dkey"] = _dkey(o)
        o.setdefault("extra", {})
        if o.get("employeur"):
            o["extra"]["employeur"] = o["employeur"]
        kept.append(o)

    best = {}
    for o in sorted(kept, key=lambda x: (PRIORITY.get(x["source"], 9), -x["score"])):
        k = o["dkey"]
        if k in best:
            b = best[k]
            b["also"].append({"source": o["source"], "url": o["url"]})
            if not b.get("salary_max") and o.get("salary_max"):
                b["salary_min"], b["salary_max"] = o["salary_min"], o["salary_max"]
            rep["duplicates_removed"] += 1
        else:
            o["also"] = []
            best[k] = o
    final = list(best.values())

    per = Counter(o["source"] for o in final)
    for s in rep["per_source"]:
        s["kept"] = per.get(s["key"], 0)
    store.upsert(final, run_id)
    rep["expired"] = store.expire(run_id, ok_sources)
    rep["fetched"] = len(raw_offers)
    rep["kept"] = len(final)
    rep["rejected"] = dict(rejected)
    store.finish_run(run_id, rep)
    progress(f"Terminé : {len(final)} offres retenues sur {len(raw_offers)} lues.")
    return rep

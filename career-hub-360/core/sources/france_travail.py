"""API officielle France Travail « Offres d'emploi v2 » (francetravail.io)."""
from __future__ import annotations

import os
import re

from ..http import Http, HttpError

TOKEN_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token"
SEARCH_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"
SCOPE = "api_offresdemploiv2 o2dsoffre"
PAGE = 150


def _explain(r) -> str:
    try:
        j = r.json()
        txt = f"{j.get('error', '')} {j.get('error_description', '')}".strip()
    except ValueError:
        txt = r.text[:200].strip()
    if "invalid_client" in txt:
        why = "identifiant ou clé secrète refusés"
    elif "invalid_scope" in txt:
        why = "application non abonnée à l'API « Offres d'emploi v2 »"
    else:
        why = "authentification refusée"
    return f"{why} — réponse de France Travail : HTTP {r.status_code} {txt or '(vide)'}"


def get_token(http: Http) -> str:
    r = http.request("POST", TOKEN_URL, params={"realm": "/partenaire"},
                     data={"grant_type": "client_credentials", "client_id": os.environ.get("FT_CLIENT_ID", "").strip(),
                           "client_secret": os.environ.get("FT_CLIENT_SECRET", "").strip(), "scope": SCOPE})
    if r.status_code != 200:
        raise HttpError(_explain(r))
    return r.json()["access_token"]


def _publiee_depuis(days: int) -> int:
    return next((v for v in (1, 3, 7, 14, 31) if v >= days), 31)


def _normalize(j: dict) -> dict:
    lieu = j.get("lieuTravail") or {}
    ent = j.get("entreprise") or {}
    origine = j.get("origineOffre") or {}
    parts = origine.get("partenaires") or []
    sal = j.get("salaire") or {}
    url = f"https://candidat.francetravail.fr/offres/recherche/detail/{j['id']}"
    apply = (j.get("contact") or {}).get("urlPostulation") or origine.get("urlOrigine") or url
    return {
        "source": "france_travail", "source_id": str(j["id"]), "title": j.get("intitule", ""),
        "company": ent.get("nom") or "Entreprise non communiquée", "location": lieu.get("libelle", ""),
        "description": j.get("description", ""), "posted_at": j.get("dateCreation"), "url": url, "apply_url": apply,
        "logo": ent.get("logo"),
        "raw": {"ft_libelle": lieu.get("libelle", ""), "code_postal": lieu.get("codePostal"),
                "type_contrat": j.get("typeContrat"), "type_contrat_libelle": j.get("typeContratLibelle"),
                "nature": j.get("natureContrat"), "alternance": j.get("alternance"),
                "experience_exige": j.get("experienceExige"), "experience_libelle": j.get("experienceLibelle"),
                "salaire": " ".join(filter(None, [sal.get("libelle"), sal.get("commentaire"),
                                                  sal.get("complement1"), sal.get("complement2")]))},
        "extra": {"partenaire": parts[0].get("nom", "") if parts else "", "mise_a_jour": j.get("dateActualisation"),
                  "salaire_affiche": sal.get("libelle") or sal.get("commentaire") or ""},
    }


def fetch(cfg, http: Http, progress) -> tuple[list[dict], list[str]]:
    token = get_token(http)
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    out, warns, seen = [], [], set()
    pages = int(cfg.recherche.get("pages_france_travail", 2))
    depuis = _publiee_depuis(int(cfg.candidat.get("fraicheur_jours", 30)))
    for kw in cfg.recherche.get("mots_cles", []):
        mots = ",".join(w for w in re.split(r"[\s,]+", kw) if w)
        n_kw = 0
        for p in range(pages):
            params = {"motsCles": mots, "publieeDepuis": depuis, "typeContrat": "CDI,CDD,MIS", "sort": 1,
                      "range": f"{p * PAGE}-{p * PAGE + PAGE - 1}"}
            r = http.get(SEARCH_URL, params=params, headers=headers)
            if r.status_code == 204:
                break
            if r.status_code == 401:
                headers["Authorization"] = f"Bearer {get_token(http)}"
                r = http.get(SEARCH_URL, params=params, headers=headers)
            if r.status_code not in (200, 206):
                warns.append(f"« {kw} » : HTTP {r.status_code} {r.text[:120]}")
                break
            res = (r.json() or {}).get("resultats") or []
            for j in res:
                if j.get("id") and j["id"] not in seen:
                    seen.add(j["id"])
                    out.append(_normalize(j))
                    n_kw += 1
            m = re.search(r"/(\d+)", r.headers.get("Content-Range", ""))
            total = int(m.group(1)) if m else len(res)
            if len(res) < PAGE or (p + 1) * PAGE >= total:
                break
        progress(f"France Travail · « {kw} » : {n_kw} nouvelle(s) offre(s) lue(s)")
    return out, warns

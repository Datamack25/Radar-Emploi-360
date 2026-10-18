"""Configuration : config/profil.toml (valeurs par défaut) + data/profil_utilisateur.json (profil saisi dans l'application).

Le profil enregistré par l'Agent Profil remplace les mots-clés de recherche, l'expérience maximale, le salaire, etc.
Chaque agent lit cette configuration, mais aucun n'en a besoin pour fonctionner : sans profil, les valeurs par défaut
de config/profil.toml s'appliquent.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
DATA = ROOT / "data"
PROFILE_JSON = DATA / "profil_utilisateur.json"

# Champs du profil utilisateur (Agent Profil) et valeurs vides
EMPTY_PROFILE = {
    "nom": "", "titre": "", "resume": "", "localisation": "France", "email": "", "telephone": "",
    "experience_ans": 0, "postes_cibles": [], "competences": [], "outils": [], "certifications": [],
    "formation": [], "langues": [], "experiences": [], "mots_cles_recherche": [],
    "mode_filtre": "conformite",  # "conformite" = règles expertes Radar ; "profil" = selon les postes et compétences du profil
}


def load_user_profile() -> dict:
    try:
        if PROFILE_JSON.exists():
            data = json.loads(PROFILE_JSON.read_text(encoding="utf-8"))
            return {**EMPTY_PROFILE, **data}
    except (OSError, ValueError):
        pass
    return dict(EMPTY_PROFILE)


def save_user_profile(p: dict) -> None:
    DATA.mkdir(exist_ok=True)
    PROFILE_JSON.write_text(json.dumps({**EMPTY_PROFILE, **p}, ensure_ascii=False, indent=1), encoding="utf-8")


@dataclass
class Config:
    profil: dict
    user: dict = field(default_factory=dict)

    @property
    def candidat(self) -> dict:
        c = dict(self.profil.get("candidat", {}))
        u = self.user or {}
        if u.get("nom"):
            c["nom"] = u["nom"]
        for k in ("experience_max_ans", "salaire_min_annuel", "fraicheur_jours", "duree_min_mois", "contrats"):
            if u.get(k) not in (None, "", []):
                c[k] = u[k]
        return c

    @property
    def recherche(self) -> dict:
        r = dict(self.profil.get("recherche", {}))
        kws = [k for k in (self.user or {}).get("mots_cles_recherche", []) if str(k).strip()]
        if kws:
            r["mots_cles"] = kws
            r["mots_cles_google"] = kws[:6]
        return r

    @property
    def mode_filtre(self) -> str:
        return (self.user or {}).get("mode_filtre") or "conformite"

    @property
    def db_path(self) -> Path:
        DATA.mkdir(exist_ok=True)
        return DATA / "career_hub.db"

    @property
    def employeurs_csv(self) -> Path:
        return CONFIG / "employeurs.csv"

    @property
    def user_agent(self) -> str:
        contact = os.environ.get("RADAR_CONTACT", "").strip()
        return "CareerHub360/1.0 (veille personnelle d'offres d'emploi" + (f"; contact: {contact}" if contact else "") + ")"

    def extra_employers(self) -> list[dict]:
        p = DATA / "employeurs_ajoutes.json"
        try:
            return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
        except (OSError, ValueError):
            return []

    def save_extra_employers(self, lst: list[dict]) -> None:
        DATA.mkdir(exist_ok=True)
        (DATA / "employeurs_ajoutes.json").write_text(json.dumps(lst, ensure_ascii=False, indent=1), encoding="utf-8")


def load_config() -> Config:
    with open(CONFIG / "profil.toml", "rb") as f:
        return Config(tomllib.load(f), load_user_profile())

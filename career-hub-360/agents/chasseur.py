"""Agent 2 — Chasseur d'offres : collecte les offres récentes correspondant au profil sur les sources autorisées
(API France Travail, Google Emploi via SerpApi, Jooble, Adzuna, sites carrières des employeurs), les filtre, les note
sur 100, supprime les doublons et les enregistre. Lancé par le bouton « Mettre à jour ».
"""
from __future__ import annotations

import os
from urllib.parse import quote_plus

from core.pipeline import ats_targets, run_update
from core.sources.liens import deep_links

from .base import Agent, AgentInfo

SOURCES_KEYS = {
    "France Travail": ("FT_CLIENT_ID", "FT_CLIENT_SECRET"),
    "Google Emploi (LinkedIn, Indeed, WTTJ, APEC, HelloWork…)": ("SERPAPI_KEY",),
    "Jooble": ("JOOBLE_KEY",),
    "Adzuna": ("ADZUNA_APP_ID", "ADZUNA_APP_KEY"),
}


def cabinet_links(term: str, city: str = "Paris") -> dict:
    """Cabinets de recrutement spécialisés banque / finance / conformité (recherches pré-remplies)."""
    q, c = quote_plus(term), quote_plus(city or "Paris")
    return {
        "Fed Finance": f"https://www.fedfinance.fr/offres-d-emploi?keywords={q}",
        "Michael Page": f"https://www.michaelpage.fr/jobs/{q.lower()}",
        "Page Personnel": f"https://www.pagepersonnel.fr/jobs/{q.lower()}",
        "Robert Half": f"https://www.roberthalf.fr/recherche-emploi?keyword={q}&location={c}",
        "Hays": f"https://www.hays.fr/recherche-emploi?q={q}&l={c}",
        "Walters People": f"https://www.walterspeople.fr/offres-d-emploi.html?keywords={q}",
        "Morgan McKinley": f"https://www.morganmckinley.com/fr/jobs/{q.lower()}",
        "Fyte": f"https://www.fyte.com/fr/offres-d-emploi?keyword={q}",
    }


class AgentChasseur(Agent):
    info = AgentInfo(
        key="chasseur", nom="Agent Chasseur d'offres", icone="🔎",
        mission="Recherche les offres récentes qui correspondent à votre profil sur les plateformes autorisées et les sites "
                "carrières, filtre (niveau, contrat, salaire, fraîcheur), note sur 100 et supprime les doublons.",
        entrees=["Profil (postes, mots-clés, critères) — ou critères par défaut", "Clés des plateformes"],
        sorties=["Offres notées avec liens pour candidater", "Recherches pré-remplies (LinkedIn, Indeed, APEC, cabinets…)"])

    @staticmethod
    def sources_status() -> dict[str, bool]:
        return {lab: all(os.environ.get(k, "").strip() for k in keys) for lab, keys in SOURCES_KEYS.items()}

    def update(self, progress=print) -> dict:
        return self.run_logged(run_update, self.cfg, self.store, progress=progress,
                               summary=lambda r: f"{r['kept']} offres retenues sur {r['fetched']} lues")

    def targets(self):
        return ats_targets(self.cfg, self.store)

    def manual_links(self, kws: list[str], lieu: str = "France", jours: int = 14) -> dict[str, dict]:
        return {k: {**deep_links(k, lieu, jours), **cabinet_links(k, "Paris" if lieu in ("France", "") else lieu)} for k in kws}

    def readiness(self) -> tuple[str, str]:
        on = sum(self.sources_status().values())
        n = len(self.store.list())
        if on and n:
            return "ok", f"{n} offres en base · {on}/4 plateformes branchées"
        if on:
            return "partiel", f"{on}/4 plateformes branchées · lancez une mise à jour"
        return "manque", "Aucune clé de plateforme (sites carrières seulement)"

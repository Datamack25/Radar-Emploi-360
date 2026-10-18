"""Annuaire des employeurs (config/employeurs.csv + ajouts) et rattachement d'une offre à un type d'employeur."""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from urllib.parse import quote_plus

from .text import norm

CATEGORIES = ["Banque", "Fintech / PSP", "Crypto", "Transfert d'argent", "RegTech", "Cabinet", "Assurance",
              "Gestion d'actifs", "Régulateur / public", "Recrutement / intérim", "Autre"]

_FALLBACK = [
    (re.compile(r"\b(hays|robert half|michael page|page personnel|pagegroup|walters people|robert walters|fed finance|fed group|"
                r"adecco|randstad|manpower|expectra|hudson|spring france|morgan philips|kelly services|synergie|proman|"
                r"approach people|harvey nash|selescope|interim|recrutement|recruitment|staffing)\b"), "Recrutement / intérim"),
    (re.compile(r"\b(banque|bank|banca|credit (?:agricole|mutuel|cooperatif|du nord|municipal)|caisse d'epargne|"
                r"banque populaire|bred|lcl|cic|natixis)\b"), "Banque"),
    (re.compile(r"\b(assurances?|assureur|mutuelle|mutualite|insurance|prevoyance|reassurance)\b"), "Assurance"),
    (re.compile(r"\b(asset management|gestion d'actifs|investment managers?|investissement|capital partners)\b"), "Gestion d'actifs"),
    (re.compile(r"\b(crypto|blockchain|bitcoin|web3)\b"), "Crypto"),
    (re.compile(r"\b(payments?|paiements?|pay|fintech|neobanque|psp|monnaie electronique)\b"), "Fintech / PSP"),
    (re.compile(r"\b(conseil|consulting|consultants|advisory|audit|partners)\b"), "Cabinet"),
]


@dataclass
class Employer:
    nom: str
    categorie: str
    site: str = ""
    ats: str = ""
    token: str = ""
    alias: list = field(default_factory=list)
    ajoute: bool = False

    def names(self) -> list[str]:
        return [self.nom] + list(self.alias)

    def search_links(self) -> dict:
        kw = quote_plus(f"{self.nom} conformité")
        g = quote_plus(f'"{self.nom}" (conformité OR LCB-FT OR KYC OR compliance OR sanctions) emploi junior')
        return {"Google": f"https://www.google.com/search?q={g}",
                "LinkedIn": f"https://www.linkedin.com/jobs/search/?keywords={kw}&location=France&geoId=105015875&f_TPR=r1209600",
                "WTTJ": f"https://www.welcometothejungle.com/fr/jobs?query={kw}&refinementList%5Boffices.country_code%5D%5B%5D=FR"}


class Annuaire:
    def __init__(self, employers: list[Employer]):
        self.employers = employers
        pats = []
        for e in employers:
            for n in e.names():
                k = norm(n)
                if len(k) >= 2:
                    pats.append((len(k), re.compile(r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])"), e))
        self._pats = sorted(pats, key=lambda x: -x[0])

    def match(self, company: str) -> Employer | None:
        c = norm(company)
        for _, p, e in self._pats:
            if p.search(c):
                return e
        return None

    def category(self, company: str) -> tuple[str, str | None]:
        e = self.match(company)
        if e:
            return e.categorie, e.nom
        c = norm(company)
        for rx, cat in _FALLBACK:
            if rx.search(c):
                return cat, None
        return "Autre", None


def load_annuaire(cfg) -> Annuaire:
    emps: list[Employer] = []
    seen = set()
    with open(cfg.employeurs_csv, encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter=";"):
            nom = (row.get("nom") or "").strip()
            if not nom or nom.startswith("#"):
                continue
            seen.add(nom)
            emps.append(Employer(nom, (row.get("categorie") or "Autre").strip(), (row.get("site") or "").strip(),
                                 (row.get("ats") or "").strip(), (row.get("token") or "").strip(),
                                 [a.strip() for a in (row.get("alias") or "").split("|") if a.strip()]))
    for x in cfg.extra_employers():
        if x.get("nom") and x["nom"] not in seen:
            emps.append(Employer(x["nom"], x.get("categorie", "Autre"), x.get("site", ""), x.get("ats", ""),
                                 x.get("token", ""), [], True))
    return Annuaire(emps)

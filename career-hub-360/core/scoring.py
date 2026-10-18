"""Note sur 100 : adéquation métier, niveau junior, contrat, salaire, fraîcheur, employeur, mots du profil."""
from __future__ import annotations

import re

from .text import norm, norm_title

PROFILE_TERMS = re.compile(
    r"\b(tracfin|declarations? de soupcon|\bds\b|swift|sepa|gel des avoirs|ppe|pep|criblage|screening|filtrage|kyb|"
    r"examens? renforces?|vigilance renforcee|alertes?|surveillance des (?:transactions|operations)|transaction monitoring|"
    r"lexisnexis|bridger|world-?check|gafi|fatf|droits? de communication|requisitions?|revue periodique|"
    r"beneficiaires? effectifs|ubo|adverse media|presse negative|correspondent banking|psp|etablissement de paiement|"
    r"monnaie electronique|ordonnance|acpr|cartographie des risques)\b")

CORE_TITLE = re.compile(r"\b(lcb ?-? ?ft|lab ?-? ?ft|aml|anti ?-? ?blanchiment|kyc|kyb|sanctions?|embargos?|"
                        r"securite financiere|financial crime|gel des avoirs)\b")

CAT_PTS = {"Banque": 8, "Fintech / PSP": 8, "Transfert d'argent": 8, "Crypto": 7, "RegTech": 7, "Cabinet": 6,
           "Assurance": 6, "Gestion d'actifs": 6, "Régulateur / public": 7, "Recrutement / intérim": 3, "Autre": 2}


def score(o: dict, cfg) -> tuple[int, list]:
    c = cfg.candidat
    t = norm_title(o["title"])
    d = norm(o.get("description"))
    parts = []

    if o["family"] == "conformite":
        parts.append(("Métier cœur (LCB-FT / KYC / sanctions dans l'intitulé)", 35) if CORE_TITLE.search(t)
                     else ("Métier conformité", 28))
    elif o["family"] == "ba":
        parts.append(("Business analyst sur un sujet conformité / KYC", 28))
    elif o["family"] == "profil":
        u = getattr(cfg, "user", None) or {}
        cibles = [norm_title(x) for x in u.get("postes_cibles") or [] if str(x).strip()]
        parts.append(("Intitulé = un de vos postes ciblés", 32) if any(c and c in t for c in cibles)
                     else ("Métier proche de vos postes ciblés", 24))
    else:
        parts.append(("Analyste crédit", 24))

    if o["exp_min"] == 0 or o.get("junior"):
        parts.append(("Ouvert aux débutants / juniors", 15))
    elif o["exp_min"] is not None and o["exp_min"] <= 1:
        parts.append(("1 an d'expérience demandé au plus", 11))
    elif o["exp_min"] is not None:
        parts.append((f"{o['exp_min']} ans d'expérience demandés (dans votre fourchette)", 6))
    else:
        parts.append(("Expérience non précisée", 5))

    k, m = o["contract"], o.get("duration")
    if k == "CDI":
        parts.append(("CDI", 12))
    elif k in ("CDD", "Intérim"):
        parts.append((f"{k} de {int(m)} mois" if m else f"{k}, durée non précisée",
                      9 if (m and m >= 6) else 7 if m else 5))
    else:
        parts.append(("Contrat non précisé", 4))

    smin = int(c.get("salaire_min_annuel", 33000))
    if o.get("salary_max") and o["salary_max"] >= smin:
        parts.append((f"Salaire indiqué ≥ {smin // 1000} k€", 10))
    else:
        parts.append(("Salaire non indiqué", 3))

    a = o.get("age")
    if a is None:
        parts.append(("Date de publication inconnue", 2))
    else:
        parts.append(("Publiée cette semaine" if a <= 7 else "Publiée ces 2 dernières semaines" if a <= 14 else "Publiée ce mois-ci",
                      10 if a <= 3 else 8 if a <= 7 else 5 if a <= 14 else 2))

    parts.append((f"Employeur : {o.get('category') or 'Autre'}", CAT_PTS.get(o.get("category") or "Autre", 2)))

    hits = sorted(set(m.group(1) for m in PROFILE_TERMS.finditer(d)))
    u = getattr(cfg, "user", None) or {}
    for sk in (u.get("competences") or []) + (u.get("outils") or []):
        k = norm(sk)
        if len(k) >= 2 and re.search(r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])", d):
            hits.append(sk)
    hits = sorted(set(hits))
    if hits:
        parts.append((f"Proche de votre expérience ({', '.join(hits[:5])})", min(10, 2 * len(hits))))

    return min(100, sum(p for _, p in parts)), parts

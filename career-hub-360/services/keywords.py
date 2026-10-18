"""Lexique de compétences et extraction de mots-clés (fonctionne sans IA).

Sert à : analyser une offre collée, mesurer la correspondance CV ↔ offre (score type ATS), repérer les compétences
les plus demandées par le marché dans les offres collectées.
"""
from __future__ import annotations

import re
from collections import Counter

from core.text import norm

# (libellé affiché, variantes normalisées recherchées)
LEXICON: dict[str, list[str]] = {
    # --- Conformité / sécurité financière
    "LCB-FT": ["lcb-ft", "lcb ft", "lcbft", "lab-ft", "lutte contre le blanchiment", "anti-blanchiment", "anti blanchiment"],
    "AML / CFT": ["aml", "anti-money laundering", "anti money laundering", "cft", "aml/cft"],
    "KYC": ["kyc", "know your customer", "connaissance client"],
    "KYB": ["kyb", "know your business"],
    "Sanctions & embargos": ["sanctions", "embargo", "embargos", "gel des avoirs", "asset freeze"],
    "Filtrage / screening": ["filtrage", "screening", "criblage", "name screening"],
    "PPE / PEP": ["ppe", "pep", "personnes politiquement exposees", "politically exposed"],
    "Surveillance transactionnelle": ["transaction monitoring", "surveillance des transactions", "surveillance des operations",
                                      "surveillance transactionnelle", "alertes"],
    "Déclaration de soupçon (Tracfin)": ["declaration de soupcon", "declarations de soupcon", "tracfin"],
    "Due diligence / EDD": ["due diligence", "edd", "examen renforce", "examens renforces", "vigilance renforcee", "cdd client"],
    "Bénéficiaires effectifs (UBO)": ["beneficiaire effectif", "beneficiaires effectifs", "ubo", "ultimate beneficial owner"],
    "Adverse media / presse négative": ["adverse media", "presse negative", "negative news"],
    "Correspondance bancaire": ["correspondent banking", "correspondance bancaire", "correspondant bancaire", "wolfsberg"],
    "Approche par les risques": ["approche par les risques", "risk-based approach", "risk based approach", "cartographie des risques"],
    "Contrôle permanent": ["controle permanent", "controle de second niveau", "controle de 2nd niveau", "second line", "2nd line"],
    "Contrôle interne": ["controle interne", "internal control"],
    "Conformité réglementaire": ["conformite", "compliance", "regulatory compliance"],
    "Fraude": ["fraude", "fraud", "lutte contre la fraude", "anti-fraude"],
    "Anti-corruption (Sapin II)": ["anti-corruption", "anticorruption", "sapin 2", "sapin ii"],
    "Contrôle des exportations": ["export control", "controle des exportations", "double usage", "dual use"],
    "Déontologie / MIF II": ["deontologie", "mif 2", "mifid", "mif ii", "mifid ii", "abus de marche"],
    "ACPR / AMF": ["acpr", "amf", "autorite des marches financiers", "autorite de controle prudentiel"],
    "GAFI / FATF": ["gafi", "fatf"],
    "Directives européennes AML (AMLD / AMLA)": ["amld", "6amld", "5amld", "amla", "directive anti-blanchiment"],
    "Reporting réglementaire": ["reporting reglementaire", "regulatory reporting", "corep", "finrep", "surfi"],
    "Bâle III / prudentiel": ["bale iii", "bale 3", "basel iii", "prudentiel", "crr", "crd"],
    "Risque de crédit": ["risque de credit", "credit risk", "analyse credit", "analyse de credit", "octroi", "scoring credit"],
    "Analyse financière": ["analyse financiere", "financial analysis", "etats financiers", "liasse fiscale", "bilan", "ratios"],
    "Gestion des risques": ["gestion des risques", "risk management", "risques operationnels", "operational risk"],
    "Audit": ["audit", "auditeur", "audit interne"],
    "Paiements / PSP": ["psp", "prestataire de services de paiement", "etablissement de paiement", "monnaie electronique", "dsp2", "psd2", "sepa", "swift"],
    "Crypto-actifs / MiCA": ["crypto", "crypto-actifs", "mica", "psan", "blockchain"],
    "Marchés financiers": ["marches financiers", "produits derives", "derives", "trading", "front office", "middle office", "back office"],
    "Valeur à risque (VaR)": ["value at risk", "valeur a risque"],
    "Gestion de portefeuille": ["gestion de portefeuille", "portfolio management", "asset management", "gestion d'actifs"],
    "Finance durable / ESG": ["esg", "sfdr", "finance durable", "taxonomie"],
    "Business analysis": ["business analyst", "business analysis", "amoa", "moa", "recueil des besoins", "specifications fonctionnelles", "user stories"],
    "Gestion de projet": ["gestion de projet", "project management", "chef de projet", "pilotage de projet"],
    "Agile / Scrum": ["agile", "scrum", "kanban", "sprint"],
    # --- Outils
    "Excel / VBA": ["excel", "vba", "tableaux croises dynamiques", "tcd"],
    "Python": ["python", "pandas", "numpy"],
    "SQL": ["sql", "postgresql", "mysql", "requetes"],
    "Power BI": ["power bi", "powerbi"],
    "Tableau": ["tableau software"],
    "Looker": ["looker"],
    "Jira": ["jira"],
    "Confluence": ["confluence"],
    "SAS": ["sas base", "sas enterprise", "logiciel sas", "sas eg"],
    "R": ["langage r", "rstudio"],
    "Bloomberg": ["bloomberg"],
    "World-Check / Refinitiv": ["world-check", "worldcheck", "world check", "refinitiv", "lseg"],
    "LexisNexis / Bridger": ["lexisnexis", "bridger"],
    "Dow Jones Risk": ["dow jones", "factiva"],
    "Fircosoft / Fircosoft Continuity": ["fircosoft", "firco"],
    "Actimize / NICE": ["actimize", "nice actimize"],
    "Salesforce": ["salesforce"],
    "SAP": ["sap"],
    "Pack Office": ["pack office", "microsoft office", "powerpoint", "word"],
    "Machine learning / IA": ["machine learning", "intelligence artificielle", "data science", "ia generative", "llm"],
    # --- Langues & certifications
    "Anglais professionnel": ["anglais", "english", "bilingue", "toeic", "toefl", "ielts"],
    "Espagnol": ["espagnol", "spanish"],
    "Certification AMF": ["certification amf"],
    "CAMS / ACAMS": ["cams", "acams"],
    "CFA": ["cfa"],
    # --- Savoir-être
    "Rigueur": ["rigueur", "rigoureux", "rigoureuse", "attention to detail"],
    "Esprit d'analyse": ["esprit d'analyse", "esprit analytique", "capacites d'analyse", "analytical skills", "analytique"],
    "Esprit de synthèse": ["synthese", "esprit de synthese"],
    "Autonomie": ["autonomie", "autonome", "autonomous"],
    "Travail en équipe": ["travail en equipe", "esprit d'equipe", "teamwork", "team player"],
    "Communication / rédaction": ["qualites redactionnelles", "aisance redactionnelle", "redaction", "communication ecrite", "communication orale"],
    "Gestion des priorités": ["gestion des priorites", "sens de l'organisation", "bonne organisation"],
    "Curiosité": ["curiosite", "curieux", "curieuse"],
    "Confidentialité / discrétion": ["confidentialite", "discretion"],
}

SOFT = {"Rigueur", "Esprit d'analyse", "Esprit de synthèse", "Autonomie", "Travail en équipe", "Communication / rédaction",
        "Gestion des priorités", "Curiosité", "Confidentialité / discrétion"}

_RX = {lab: re.compile(r"(?<![a-z0-9])(" + "|".join(re.escape(v) for v in sorted(vs, key=len, reverse=True)) + r")(?![a-z0-9])")
       for lab, vs in LEXICON.items()}

_STOP = set("""a au aux avec ce ces cette dans de des du elle en et etre il ils je la le les leur leurs lui ma mais me mes
moi mon ne nos notre nous on ou par pas pour qu que qui sa se ses son sur ta te tes toi ton tu un une vos votre vous y
d l s n c j m qu' est sont sera serez avez avoir fait faire plus tres bien tout tous toute toutes the and or of to in for
with on at by an be is are will you your our we this that as from h f cdi cdd poste profil mission missions vous
entreprise equipe nous rejoindre recherche recherchons candidat candidate experience ans annee annees afin ainsi
selon sein etc dont lors via notamment egalement aupres entre chez autres autre type niveau tant deux trois
""".split())


def find_skills(text: str) -> list[str]:
    """Compétences du lexique présentes dans un texte (ordre du lexique)."""
    t = norm(text)
    return [lab for lab, rx in _RX.items() if rx.search(t)]


def skill_counts(texts: list[str]) -> Counter:
    """Nombre de textes (offres) mentionnant chaque compétence."""
    c = Counter()
    for tx in texts:
        c.update(set(find_skills(tx)))
    return c


def top_terms(text: str, n: int = 25) -> list[str]:
    """Mots et expressions fréquents d'un texte, hors mots vides (complément du lexique)."""
    t = norm(text)
    words = [w for w in re.findall(r"[a-z][a-z0-9+#'-]{2,}", t) if w not in _STOP]
    bi = [f"{a} {b}" for a, b in zip(words, words[1:]) if a not in _STOP and b not in _STOP]
    c = Counter(words) + Counter({k: v * 2 for k, v in Counter(bi).items() if v >= 2})
    return [w for w, _ in c.most_common(n)]


def match_report(cv_text: str, offer_text: str) -> dict:
    """Correspondance CV ↔ offre : compétences demandées trouvées / manquantes et score sur 100."""
    asked = find_skills(offer_text)
    have = set(find_skills(cv_text))
    found = [s for s in asked if s in have]
    missing = [s for s in asked if s not in have]
    hard = [s for s in asked if s not in SOFT]
    hard_found = [s for s in hard if s in have]
    # Les compétences techniques pèsent 75 %, le savoir-être 25 %
    soft = [s for s in asked if s in SOFT]
    soft_found = [s for s in soft if s in have]
    score = 0.0
    if hard:
        score += 75 * len(hard_found) / len(hard)
    if soft:
        score += 25 * len(soft_found) / len(soft)
    if hard and not soft:
        score = 100 * len(hard_found) / len(hard)
    if soft and not hard:
        score = 100 * len(soft_found) / len(soft)
    return {"asked": asked, "found": found, "missing": missing, "score": round(score) if asked else 0}


# ---------------------------------------------------------------- analyse d'une offre sans IA
_TITLE_HINT = re.compile(r"\b(h/f|f/h|h-f|f-h|\(h/f\)|\(f/h\)|cdi|cdd)\b", re.I)


def guess_offer_fields(text: str) -> dict:
    """Intitulé, entreprise, lieu, contrat et expérience devinés dans une offre collée (à vérifier par l'utilisateur)."""
    lines = [l.strip(" •-*\t") for l in str(text or "").splitlines() if l.strip()]
    title = ""
    for l in lines[:12]:
        if _TITLE_HINT.search(l) and len(l) < 140:
            title = re.sub(r"\s*[-–|]\s*(cdi|cdd).*$", "", l, flags=re.I).strip()
            break
    if not title and lines:
        title = lines[0][:120]
    title = re.sub(r"\s*\(?\b[hfm]\s*/\s*[hfm]\b\)?", "", title, flags=re.I).strip(" -–|")
    company = ""
    for rx in (r"(?:chez|rejoindre|rejoignez|au sein de|au sein d')\s+([A-Z][\w&'’.\- ]{1,40}?)(?=[,.;:!\n]| en | pour | et |$)",
               r"^([A-Z][\w&'’.\- ]{1,40}?)\s+(?:recrute|recherche|is hiring|is looking)",
               r"(?:entreprise|société|employeur|company)\s*:\s*([^\n]{2,60})"):
        m = re.search(rx, text or "", re.M)
        if m:
            company = m.group(1).strip(" .,'’")
            break
    if not company and len(lines) > 1 and len(lines[1].split()) <= 5 and lines[1][:1].isupper() and not re.search(r"[.:!?]$", lines[1]):
        company = re.split(r"\s+[—–-]\s+", lines[1])[0].strip()
    loc = ""
    m = re.search(r"(?i:lieu|localisation|location|ville|bas[ée]e? [àa])\s*:?\s*([A-ZÉ][\w\-’']{2,40}(?: [A-ZÉ][\w\-’']+)*)", text or "")
    if m:
        loc = m.group(1).strip()
    t = norm(text)
    contract = "CDI" if re.search(r"\bcdi\b", t) else "CDD" if re.search(r"\bcdd\b", t) else "Intérim" if "interim" in t else ""
    m = re.search(r"(\d{1,2})\s*(?:a|-|à)?\s*\d{0,2}\s*ans? (?:d'|minimum d')?experience", t)
    exp = ("Débutant accepté" if m.group(1) == "0" else f"{m.group(1)} an(s) minimum") if m else ("Débutant / junior accepté" if re.search(r"junior|debutant|jeune diplome", t) else "")
    return {"poste": title, "entreprise": company, "lieu": loc, "contrat": contract, "experience": exp,
            "competences_requises": find_skills(text), "mots_cles": top_terms(text, 20)}

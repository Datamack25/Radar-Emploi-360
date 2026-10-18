"""Règles de sélection : métier, niveau junior, contrat et durée, salaire, lieu.

Chaque offre passe par `evaluate`, qui renvoie la raison du rejet (ou None) et complète l'offre
(famille de métier, contrat, durée, salaire, expérience, département, région).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from . import geo
from .text import norm, norm_title

# ---------------------------------------------------------------- métiers
CONF_TITLE = re.compile(
    r"\b(conformite|compliance|lcb|lcb ?-? ?ft|lab ?-? ?ft|aml|cft|anti ?-? ?blanchiment|blanchiment|kyc|kyb|"
    r"know your customer|sanctions?|embargos?|gel des avoirs|securite financiere|financial (?:crime|security)|fincrime|"
    r"tracfin|deontologie|deontologue|controle permanent|screening|transaction monitoring|"
    r"surveillance des (?:transactions|operations|flux)|export control|trade compliance|anti ?-? ?corruption|"
    r"onboarding client|kyc analyst)\b")
DOMAIN_EXCLU = re.compile(
    r"\b(qualite|quality|pharma\w*|technicien\w*|electri\w*|btp|chantier|hse|qhse|batiment|rgpd|gdpr|dpo|"
    r"data protection|privacy|donnees personnelles|environnement\w*|alimentaire|medical|nucleaire|ferroviaire|"
    r"cyber\w*|it compliance|securite informatique|ssi|iso ?27001|soc ?2|controle technique|immobilier|urbanisme|"
    r"commercial\w*|vendeu\w*|conseiller clientele|charge\w* de clientele|developpeu\w*|developer|software|"
    r"juriste|avocat\w*|paralegal|legal counsel|comptable|accountant|auditeur interne)\b")
BA_TITLE = re.compile(r"\b(business analyst\w*|business analyste|analyste (?:metier|fonctionnel\w*|business)|ba|amoa|moa|"
                      r"functional analyst|consultant\w* (?:metier|fonctionnel\w*))\b")
CREDIT_TITLE = re.compile(
    r"\b(analyste|analyst|charge\w* d'(?:analyse|etudes?)|chargee? d'analyse)\b.{0,40}?\b(credits?|engagements?|octroi|"
    r"risques? de contrepartie)\b|\bcredit (?:risk )?analyst\b|\bcredit risk\b.{0,15}\banalyst")
GENERIC_TITLE = re.compile(r"\b(analyste|analyst|consultant\w*|gestionnaire|officer|associate|specialist|specialiste|"
                           r"charge\w* d'etudes|operateur|back[ -]?office|middle[ -]?office)\b")
STRONG = re.compile(r"\b(kyc|kyb|lcb ?-? ?ft|lab ?-? ?ft|aml|anti ?-? ?blanchiment|blanchiment|sanctions?|embargos?|"
                    r"gel des avoirs|conformite|compliance|tracfin|screening|filtrage|ppe|peps?|financement du terrorisme|"
                    r"due diligence|vigilance|edd|connaissance client|know your customer)\b")

FAMILIES = {"conformite": "Conformité · LCB-FT · KYC · sanctions", "ba": "Business analyst conformité / KYC",
            "credit": "Analyste crédit", "profil": "Selon votre profil"}

# Mots trop génériques pour identifier un métier à eux seuls
_GENERIC_TOKENS = {"analyste", "analyst", "charge", "chargee", "junior", "senior", "consultant", "consultante", "officer",
                   "specialist", "specialiste", "gestionnaire", "assistant", "assistante", "manager", "responsable", "de",
                   "des", "du", "la", "le", "les", "en", "et", "the", "of", "and", "h", "f", "cdi", "cdd", "poste", "metier"}


def _profile_terms(cfg) -> tuple[list[str], set[str], list[str]]:
    """Expressions des postes ciblés, mots distinctifs, et compétences du profil (normalisés)."""
    u = getattr(cfg, "user", None) or {}
    phrases = [norm_title(x) for x in (u.get("postes_cibles") or []) + (u.get("mots_cles_recherche") or []) if str(x).strip()]
    tokens = {t for ph in phrases for t in re.findall(r"[a-z0-9+#-]{3,}", ph) if t not in _GENERIC_TOKENS}
    skills = [norm(x) for x in (u.get("competences") or []) + (u.get("outils") or []) if len(norm(x)) >= 2]
    return phrases, tokens, skills


def family_profile(cfg, title_n: str, desc_n: str) -> str | None:
    """Rattachement d'une offre au profil de l'utilisateur (mode « selon mon profil »)."""
    phrases, tokens, skills = _profile_terms(cfg)
    if not phrases and not skills:
        return family(title_n, desc_n)
    if any(ph and ph in title_n for ph in phrases):
        return "profil"
    title_tokens = set(re.findall(r"[a-z0-9+#-]{3,}", title_n))
    skill_hits = sum(1 for s in skills if re.search(r"(?<![a-z0-9])" + re.escape(s) + r"(?![a-z0-9])", desc_n))
    if title_tokens & tokens and skill_hits >= 2:
        return "profil"
    if GENERIC_TITLE.search(title_n) and skill_hits >= 4:
        return "profil"
    return None

# ---------------------------------------------------------------- niveau
SENIOR = re.compile(r"\b(senior|sr|confirme|confirmee|experimente|experimentee|expert\w*|manager|head|lead|leader|"
                    r"directeur|directrice|director|chief|cco|responsable|principal|vp|vice ?-? ?president|"
                    r"superviseur|supervisor|chef|team leader|partner|associe|managing)\b")
JUNIOR = re.compile(r"\b(junior|jr|debutant\w*|jeunes? diplome\w*|premiere experience|first experience|graduate|"
                    r"entry ?-? ?level|sortie d'ecole|recent graduate|0 ?(?:a|-) ?[123] ans?|niveau 1)\b")
STAGE = re.compile(r"\b(stages?|stagiaire|intern|interns|internship|alternance|alternant\w*|apprenti\w*|apprentissage|"
                   r"contrat pro\w*|professionnalisation|v\.i\.e|volontariat international|work ?-? ?study|working student|"
                   r"werkstudent|these|cifre|freelance|free ?-? ?lance|independant|portage salarial|benevol\w*|"
                   r"service civique|summer job|job d'ete)\b")

_W = r"(?:[\w'+-]+\s+){0,3}?"
EXP_RX = [
    re.compile(r"(\d{1,2})\s*(?:a|-|/|ou)\s*\d{1,2}\s*(?:ans?|annees?)\s+" + _W + r"(?:d')?experience"),
    re.compile(r"(\d{1,2})\s*\+?\s*(?:ans?|annees?)\s+" + _W + r"(?:d')?experience"),
    re.compile(r"experience\s+(?:[\w']+\s+){0,4}?(?:de|d'au moins|minimum de|minimum|d'environ)\s+(\d{1,2})\s*(?:ans?|annees?)"),
    re.compile(r"(?:minimum|au moins|min\.?)\s+(?:de\s+)?(\d{1,2})\s*(?:ans?|annees?)\b"),
    re.compile(r"(\d{1,2})\s*\+?\s*(?:-\s*\d{1,2}\s*)?years?\s+" + _W + r"experience"),
    re.compile(r"(?:at least|minimum(?: of)?)\s+(\d{1,2})\s+years?"),
]

# ---------------------------------------------------------------- contrat
CDI_RX = re.compile(r"\b(cdi|permanent|contrat a duree indeterminee|full[ -]?time permanent|unbefristet)\b")
CDD_RX = re.compile(r"\b(cdd|fixed[ -]?term|contrat a duree determinee|temporary|temporaire|remplacement|conge maternite)\b")
INTERIM_RX = re.compile(r"\b(interim\w*|travail temporaire|mission d'interim|mission interimaire|temp to perm)\b")
DUR_RX = [
    (re.compile(r"(?:cdd|mission|interim\w*|contrat|duree|fixed[ -]?term|contract|remplacement)[^.\n]{0,60}?\b(\d{1,2})\s*mois"), 1),
    (re.compile(r"\b(\d{1,2})\s*mois\b[^.\n]{0,30}?(?:cdd|mission|renouvelable|contrat)"), 1),
    (re.compile(r"\b(\d{1,2})\s*[- ]?months?\b[^.\n]{0,30}?(?:contract|fixed|temporary|mission)|"
                r"(?:contract|fixed[ -]?term|temporary)[^.\n]{0,40}?\b(\d{1,2})\s*[- ]?months?"), 1),
    (re.compile(r"(?:cdd|mission|interim\w*|contrat|duree)[^.\n]{0,40}?\b(\d{1,2})\s*semaines?"), 1 / 4.33),
]

# ---------------------------------------------------------------- salaire
SAL_KW = re.compile(r"salaire|remuneration|package|brut|gross|salary|compensation|fixe|variable|par an|/ ?an\b|annuel|"
                    r"pay range|base pay|k ?eur|keur|\bk\b|eur ?/ ?an|par mois|mensuel")
SAL_EXCLU = re.compile(r"capital|chiffre d'affaires|\bca\b|levee|leve|millions?|milliards?|\bmd\b|fonds|actifs|encours|"
                       r"transactions?|volume|clients|budget|amende|sanction de|montant")
K_RANGE = re.compile(r"(\d{2,3})(?:[.,]\d)?\s*(?:k ?eur|keur|k)?\s*(?:eur\s*)?(?:-|a|to|/|et)\s*(?:eur)?\s*(\d{2,3})(?:[.,]\d)?\s*(?:k ?eur|keur|k\b)")
K_ONE = re.compile(r"(?<![\d.,])(\d{2,3})(?:[.,]\d)?\s*(?:k ?eur|keur|k\b)")
EUR = re.compile(r"(?<![\d.,])(\d{1,3}(?:[ .,]\d{3})+|\d{4,6})(?:[.,]\d{1,2})?\s*(?:euros?|eur)\b|\beur\s*(\d{1,3}(?:[ .,]\d{3})+|\d{4,6})(?![\d])")


def _years_from_ft(o) -> tuple[int | None, str]:
    raw = o.get("raw") or {}
    exige, lib = raw.get("experience_exige"), norm(raw.get("experience_libelle"))
    if exige == "D" or "debutant" in lib:
        return 0, "Débutant accepté"
    m = re.search(r"(\d+)\s*an", lib)
    if m:
        return int(m.group(1)), f"{m.group(1)} an(s) d'expérience"
    m = re.search(r"(\d+)\s*mois", lib)
    if m:
        return int(m.group(1)) // 12, f"{m.group(1)} mois d'expérience"
    return None, ""


def experience(o, title_n: str, desc_n: str) -> tuple[int | None, str]:
    """Années minimales demandées (None si non indiqué) et libellé affiché."""
    if o["source"] == "france_travail":
        y, lab = _years_from_ft(o)
        if y is not None:
            return y, lab
    vals = []
    for rx in EXP_RX:
        for m in rx.finditer(desc_n):
            v = int(m.group(1))
            if v < 8:  # « fort de 15 ans d'expérience » décrit l'entreprise, pas le poste
                vals.append(v)
    if vals:
        v = min(vals)
        return v, "Débutant accepté" if v == 0 else f"{v} an{'s' if v > 1 else ''} d'expérience minimum"
    if JUNIOR.search(title_n) or JUNIOR.search(desc_n):
        return 0, "Junior / débutant accepté"
    return None, "Expérience non précisée"


def family(title_n: str, desc_n: str) -> str | None:
    if DOMAIN_EXCLU.search(title_n):
        return None
    n_strong = len(set(m.group(1) for m in STRONG.finditer(desc_n)))
    if BA_TITLE.search(title_n) and (CONF_TITLE.search(title_n) or n_strong >= 2):
        return "ba"
    if CONF_TITLE.search(title_n):
        return "conformite"
    if CREDIT_TITLE.search(title_n):
        return "credit"
    if GENERIC_TITLE.search(title_n) and n_strong >= 3:
        return "conformite"
    return None


def title_could_match(title: str) -> bool:
    t = norm_title(title)
    return bool(CONF_TITLE.search(t) or CREDIT_TITLE.search(t) or BA_TITLE.search(t) or GENERIC_TITLE.search(t))


def _months(text: str) -> float | None:
    for rx, factor in DUR_RX:
        m = rx.search(text)
        if m:
            v = next((g for g in m.groups() if g), None)
            if v:
                return round(int(v) * factor, 1)
    return None


def contract_info(o, title_n: str, desc_n: str) -> tuple[str | None, float | None, str | None]:
    """(contrat, durée en mois, raison de rejet)."""
    raw = o.get("raw") or {}
    if o["source"] == "france_travail":
        tc = (raw.get("type_contrat") or "").upper()
        lib = norm(raw.get("type_contrat_libelle"))
        nature = norm(raw.get("nature"))
        if raw.get("alternance") or re.search(r"apprentissage|professionnalisation", nature):
            return None, None, "Stage / alternance / freelance"
        kind = {"CDI": "CDI", "DIN": "CDI", "CDD": "CDD", "DDI": "CDD", "MIS": "Intérim"}.get(tc)
        if not kind:
            return None, None, "Contrat non retenu (saisonnier, libéral, franchise…)"
        months = None
        m = re.search(r"(\d+)\s*mois", lib)
        if m:
            months = float(m.group(1))
        else:
            m = re.search(r"(\d+)\s*jour", lib)
            if m:
                months = round(int(m.group(1)) / 30, 1)
        if months is None and kind != "CDI":
            months = _months(desc_n)
        return kind, months, None

    emp = norm(raw.get("employment"))
    if STAGE.search(emp) or re.search(r"\b(intern|internship|apprentice|freelance|contractor|prestataire|stage)\b", emp):
        return None, None, "Stage / alternance / freelance"
    kind = None
    for text in (title_n, emp):
        if INTERIM_RX.search(text):
            kind = "Intérim"
        elif CDD_RX.search(text) or re.search(r"\b(contract|temporary|fixed)\b", text):
            kind = "CDD"
        elif CDI_RX.search(text) or re.search(r"\b(full ?-? ?time|fulltime|regular)\b", text):
            kind = "CDI"
        if kind:
            break
    if o["source"] == "adzuna" and not kind:
        kind = {"permanent": "CDI", "contract": "CDD"}.get(raw.get("contract_type") or "")
    if not kind or kind == "CDD":
        head = desc_n[:4000]
        if re.search(r"type de contrat\s*:?\s*(stage|alternance|apprentissage|freelance)", head):
            return None, None, "Stage / alternance / freelance"
        if INTERIM_RX.search(head) and not CDI_RX.search(head):
            kind = "Intérim"
        elif not kind:
            kind = "CDI" if CDI_RX.search(head) else "CDD" if CDD_RX.search(head) else "Non précisé"
    months = _months(desc_n + " " + title_n) if kind in ("CDD", "Intérim") else None
    return kind, months, None


def parse_ft_salary(lib: str) -> tuple[int | None, int | None]:
    t = norm(lib)
    nums = [float(x.replace(",", ".")) for x in re.findall(r"(\d+(?:[.,]\d+)?)\s*euros?", t)]
    if not nums:
        return None, None
    if t.startswith("horaire") or "horaire" in t[:15]:
        factor = 1607
    elif t.startswith("mensuel") or "mensuel" in t[:15]:
        m = re.search(r"sur\s*(\d+(?:[.,]\d+)?)\s*mois", t)
        factor = float(m.group(1).replace(",", ".")) if m else 12
    else:
        factor = 1
    vals = [int(n * factor) for n in nums if 5 <= n * factor <= 300000]
    vals = [v for v in vals if v >= 12000]
    return (min(vals), max(vals)) if vals else (None, None)


def parse_salary_text(text: str) -> tuple[int | None, int | None]:
    """Cherche une rémunération annuelle dans un texte libre (fourchettes en k€, montants en €, mensuels)."""
    t = norm(text)
    vals = []

    def ctx(a, b, span=80):
        return t[max(0, a - span): b + span]

    for m in K_RANGE.finditer(t):
        c = ctx(m.start(), m.end(), 50)
        if SAL_EXCLU.search(c) and not re.search(r"salaire|remuneration|salary|package", c):
            continue
        a, b = int(m.group(1)) * 1000, int(m.group(2)) * 1000
        if 18000 <= a <= 200000 and 18000 <= b <= 250000 and a <= b:
            vals += [a, b]
    if not vals:
        for m in K_ONE.finditer(t):
            c = ctx(m.start(), m.end(), 60)
            if not re.search(r"salaire|remuneration|salary|package|brut|gross|compensation|fixe|eur", c) or SAL_EXCLU.search(c):
                continue
            v = int(m.group(1)) * 1000
            if 18000 <= v <= 200000:
                vals.append(v)
    for m in EUR.finditer(t):
        c = ctx(m.start(), m.end())
        if not SAL_KW.search(c) or SAL_EXCLU.search(ctx(m.start(), m.end(), 40)):
            continue
        v = float(re.sub(r"[ .,]", "", m.group(1) or m.group(2)))
        near = ctx(m.start(), m.end(), 40)
        if v <= 10000 and re.search(r"mois|mensuel|month", near):
            mm = re.search(r"sur\s*(1[2-4])\s*mois", c)
            v *= int(mm.group(1)) if mm else 12
        if 18000 <= v <= 250000:
            vals.append(int(v))
    return (min(vals), max(vals)) if vals else (None, None)


def salary(o) -> tuple[int | None, int | None]:
    raw = o.get("raw") or {}
    if o["source"] == "france_travail":
        lo, hi = parse_ft_salary(raw.get("salaire") or "")
        if lo:
            return lo, hi
    s = raw.get("salary")
    if s and (s[0] or s[1]):
        return s[0] or s[1], s[1] or s[0]
    if raw.get("salary_text"):
        lo, hi = parse_salary_text("salaire " + raw["salary_text"])
        if lo:
            return lo, hi
    return parse_salary_text(o.get("title", "") + "\n" + (o.get("description") or ""))


def geo_of(o) -> geo.Geo:
    raw = o.get("raw") or {}
    if o["source"] == "france_travail":
        return geo.from_ft(raw.get("ft_libelle") or o.get("location"), raw.get("code_postal"))
    if o["source"] == "adzuna":
        return geo.from_adzuna(raw.get("area"), o.get("location"))
    return geo.classify(raw.get("loc_all") or o.get("location"), raw.get("country"))


FOREIGN_POST = re.compile(r"(?:poste|base|basee|situe|situee|localise|localisee|located|based|position)\s+(?:est\s+)?"
                          r"(?:a|au|aux|en|in)\s+(luxembourg|belgique|belgium|bruxelles|brussels|suisse|switzerland|geneve|"
                          r"geneva|zurich|lausanne|monaco|londres|london|espagne|spain|madrid|allemagne|germany|"
                          r"irlande|ireland|dublin|pays[ -]bas|netherlands|amsterdam|portugal|lisbonne|lisbon|bresil|brazil|"
                          r"perou|peru|maroc|morocco|casablanca|tunisie|senegal|dakar|abidjan|cote d'ivoire)\b")


def _age_days(iso) -> float | None:
    if not iso:
        return None
    try:
        d = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - d).total_seconds() / 86400


def evaluate(o: dict, cfg) -> str | None:
    """Renvoie la raison du rejet, ou None si l'offre est retenue (l'offre est alors complétée)."""
    c = cfg.candidat
    title_n = norm_title(o.get("title"))
    desc_n = norm(o.get("description"))

    g = geo_of(o)
    if g.status != "fr" or FOREIGN_POST.search(desc_n[:3000]) or (
            geo._FOREIGN_RX.search(geo._gnorm(o.get("title"))) and not geo._FR_RX.search(geo._gnorm(o.get("title")))):
        return "Hors France (étranger ou lieu non précisé)"
    if STAGE.search(title_n):
        return "Stage / alternance / freelance"
    fam = family_profile(cfg, title_n, desc_n) if getattr(cfg, "mode_filtre", "conformite") == "profil" else family(title_n, desc_n)
    if not fam:
        return "Métier hors cible"
    if SENIOR.search(title_n) and not JUNIOR.search(title_n):
        return "Intitulé senior / encadrement"
    exp_min, exp_label = experience(o, title_n, desc_n)
    max_y = int(c.get("credit_experience_max_ans", 1)) if fam == "credit" else int(c.get("experience_max_ans", 3))
    if exp_min is not None and exp_min > max_y:
        return "Trop d'expérience exigée"
    kind, months, why = contract_info(o, title_n, desc_n)
    if why:
        return why
    allowed = set(c.get("contrats", ["CDI", "CDD", "Intérim"])) | {"Non précisé"}
    if kind not in allowed:
        return "Contrat non retenu (saisonnier, libéral, franchise…)"
    if kind in ("CDD", "Intérim") and months is not None and months < float(c.get("duree_min_mois", 3)):
        return f"CDD / intérim de moins de {c.get('duree_min_mois', 3)} mois"
    smin, smax = salary(o)
    if smax and smax < int(c.get("salaire_min_annuel", 33000)):
        return f"Salaire sous {int(c.get('salaire_min_annuel', 33000)) // 1000} k€"
    age = _age_days(o.get("posted_at"))
    if age is not None and age > int(c.get("fraicheur_jours", 30)):
        return "Publiée il y a trop longtemps"

    o.update(family=fam, contract=kind, duration=months, salary_min=smin, salary_max=smax, exp_min=exp_min,
             experience=exp_label, dept=g.dept, region=g.region, junior=bool(JUNIOR.search(title_n) or JUNIOR.search(desc_n[:3000])),
             age=age)
    return None

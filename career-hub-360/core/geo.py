"""Localisation : décide si une offre est en France (métropole + outre-mer) et en déduit département et région.

Règle : une offre n'est retenue que si un signal français est trouvé (code département, code postal,
ville, région, « France »). Sans signal français (« Remote », « Europe », « São Paulo », « Luxembourg »…) elle est écartée.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .text import norm

IDF, ARA, HDF, PACA, GE = "Île-de-France", "Auvergne-Rhône-Alpes", "Hauts-de-France", "Provence-Alpes-Côte d'Azur", "Grand Est"
OCC, NA, NOR, BRE, PDL = "Occitanie", "Nouvelle-Aquitaine", "Normandie", "Bretagne", "Pays de la Loire"
CVL, BFC, COR, OM = "Centre-Val de Loire", "Bourgogne-Franche-Comté", "Corse", "Outre-mer"

DEPTS = {
    "01": ("Ain", ARA), "02": ("Aisne", HDF), "03": ("Allier", ARA), "04": ("Alpes-de-Haute-Provence", PACA),
    "05": ("Hautes-Alpes", PACA), "06": ("Alpes-Maritimes", PACA), "07": ("Ardèche", ARA), "08": ("Ardennes", GE),
    "09": ("Ariège", OCC), "10": ("Aube", GE), "11": ("Aude", OCC), "12": ("Aveyron", OCC), "13": ("Bouches-du-Rhône", PACA),
    "14": ("Calvados", NOR), "15": ("Cantal", ARA), "16": ("Charente", NA), "17": ("Charente-Maritime", NA), "18": ("Cher", CVL),
    "19": ("Corrèze", NA), "2A": ("Corse-du-Sud", COR), "2B": ("Haute-Corse", COR), "21": ("Côte-d'Or", BFC),
    "22": ("Côtes-d'Armor", BRE), "23": ("Creuse", NA), "24": ("Dordogne", NA), "25": ("Doubs", BFC), "26": ("Drôme", ARA),
    "27": ("Eure", NOR), "28": ("Eure-et-Loir", CVL), "29": ("Finistère", BRE), "30": ("Gard", OCC), "31": ("Haute-Garonne", OCC),
    "32": ("Gers", OCC), "33": ("Gironde", NA), "34": ("Hérault", OCC), "35": ("Ille-et-Vilaine", BRE), "36": ("Indre", CVL),
    "37": ("Indre-et-Loire", CVL), "38": ("Isère", ARA), "39": ("Jura", BFC), "40": ("Landes", NA), "41": ("Loir-et-Cher", CVL),
    "42": ("Loire", ARA), "43": ("Haute-Loire", ARA), "44": ("Loire-Atlantique", PDL), "45": ("Loiret", CVL), "46": ("Lot", OCC),
    "47": ("Lot-et-Garonne", NA), "48": ("Lozère", OCC), "49": ("Maine-et-Loire", PDL), "50": ("Manche", NOR), "51": ("Marne", GE),
    "52": ("Haute-Marne", GE), "53": ("Mayenne", PDL), "54": ("Meurthe-et-Moselle", GE), "55": ("Meuse", GE), "56": ("Morbihan", BRE),
    "57": ("Moselle", GE), "58": ("Nièvre", BFC), "59": ("Nord", HDF), "60": ("Oise", HDF), "61": ("Orne", NOR),
    "62": ("Pas-de-Calais", HDF), "63": ("Puy-de-Dôme", ARA), "64": ("Pyrénées-Atlantiques", NA), "65": ("Hautes-Pyrénées", OCC),
    "66": ("Pyrénées-Orientales", OCC), "67": ("Bas-Rhin", GE), "68": ("Haut-Rhin", GE), "69": ("Rhône", ARA), "70": ("Haute-Saône", BFC),
    "71": ("Saône-et-Loire", BFC), "72": ("Sarthe", PDL), "73": ("Savoie", ARA), "74": ("Haute-Savoie", ARA), "75": ("Paris", IDF),
    "76": ("Seine-Maritime", NOR), "77": ("Seine-et-Marne", IDF), "78": ("Yvelines", IDF), "79": ("Deux-Sèvres", NA), "80": ("Somme", HDF),
    "81": ("Tarn", OCC), "82": ("Tarn-et-Garonne", OCC), "83": ("Var", PACA), "84": ("Vaucluse", PACA), "85": ("Vendée", PDL),
    "86": ("Vienne", NA), "87": ("Haute-Vienne", NA), "88": ("Vosges", GE), "89": ("Yonne", BFC), "90": ("Territoire de Belfort", BFC),
    "91": ("Essonne", IDF), "92": ("Hauts-de-Seine", IDF), "93": ("Seine-Saint-Denis", IDF), "94": ("Val-de-Marne", IDF),
    "95": ("Val-d'Oise", IDF), "971": ("Guadeloupe", OM), "972": ("Martinique", OM), "973": ("Guyane", OM), "974": ("La Réunion", OM),
    "976": ("Mayotte", OM),
}
REGION_NAMES = [IDF, ARA, HDF, PACA, GE, OCC, NA, NOR, BRE, PDL, CVL, BFC, COR, OM]

REGION_ALIASES = {
    "ile de france": IDF, "idf": IDF, "region parisienne": IDF, "auvergne rhone alpes": ARA, "rhone alpes": ARA, "auvergne": ARA,
    "hauts de france": HDF, "provence alpes cote d'azur": PACA, "paca": PACA, "cote d'azur": PACA, "provence": PACA,
    "grand est": GE, "alsace": GE, "lorraine": GE, "champagne": GE, "occitanie": OCC, "nouvelle aquitaine": NA, "aquitaine": NA,
    "normandie": NOR, "bretagne": BRE, "pays de la loire": PDL, "centre val de loire": CVL, "bourgogne franche comte": BFC,
    "bourgogne": BFC, "franche comte": BFC, "corse": COR, "guadeloupe": OM, "martinique": OM, "guyane": OM, "la reunion": OM,
    "reunion": OM, "mayotte": OM, "outre mer": OM, "dom tom": OM,
}

CITIES = {
    # Île-de-France
    "paris": "75", "la defense": "92", "puteaux": "92", "courbevoie": "92", "nanterre": "92", "boulogne billancourt": "92",
    "issy les moulineaux": "92", "levallois perret": "92", "neuilly sur seine": "92", "rueil malmaison": "92", "montrouge": "92",
    "malakoff": "92", "clichy": "92", "chatillon": "92", "clamart": "92", "meudon": "92", "suresnes": "92", "saint cloud": "92",
    "vanves": "92", "colombes": "92", "gennevilliers": "92", "asnieres sur seine": "92", "bagneux": "92", "sevres": "92",
    "saint denis la plaine": "93", "la plaine saint denis": "93", "montreuil": "93", "saint ouen": "93", "pantin": "93",
    "noisy le grand": "93", "bobigny": "93", "aubervilliers": "93", "ivry sur seine": "94", "charenton le pont": "94",
    "vincennes": "94", "creteil": "94", "fontenay sous bois": "94", "arcueil": "94", "gentilly": "94", "rungis": "94",
    "maisons alfort": "94", "orly": "94", "massy": "91", "evry": "91", "evry courcouronnes": "91", "les ulis": "91", "saclay": "91",
    "versailles": "78", "guyancourt": "78", "saint quentin en yvelines": "78", "velizy": "78", "velizy villacoublay": "78",
    "montigny le bretonneux": "78", "cergy": "95", "cergy pontoise": "95", "roissy": "95", "argenteuil": "95",
    "marne la vallee": "77", "serris": "77", "melun": "77", "noisiel": "77", "champs sur marne": "77",
    # Régions
    "lyon": "69", "villeurbanne": "69", "limonest": "69", "ecully": "69", "marseille": "13", "aix en provence": "13", "nice": "06",
    "sophia antipolis": "06", "valbonne": "06", "cannes": "06", "antibes": "06", "toulon": "83", "avignon": "84",
    "montpellier": "34", "toulouse": "31", "labege": "31", "blagnac": "31", "bordeaux": "33", "merignac": "33", "pessac": "33",
    "nantes": "44", "saint herblain": "44", "saint nazaire": "44", "rennes": "35", "cesson sevigne": "35", "saint malo": "35",
    "brest": "29", "quimper": "29", "lorient": "56", "vannes": "56", "lille": "59", "roubaix": "59", "tourcoing": "59",
    "villeneuve d'ascq": "59", "marcq en baroeul": "59", "croix": "59", "valenciennes": "59", "dunkerque": "59", "arras": "62",
    "calais": "62", "lens": "62", "amiens": "80", "beauvais": "60", "compiegne": "60", "strasbourg": "67", "schiltigheim": "67",
    "mulhouse": "68", "colmar": "68", "metz": "57", "thionville": "57", "nancy": "54", "reims": "51", "troyes": "10",
    "dijon": "21", "besancon": "25", "belfort": "90", "montbeliard": "25", "macon": "71", "auxerre": "89", "nevers": "58",
    "grenoble": "38", "saint etienne": "42", "clermont ferrand": "63", "annecy": "74", "chambery": "73", "valence": "26",
    "nimes": "30", "perpignan": "66", "beziers": "34", "pau": "64", "bayonne": "64", "biarritz": "64", "la rochelle": "17",
    "niort": "79", "poitiers": "86", "limoges": "87", "angouleme": "16", "perigueux": "24", "brive la gaillarde": "19",
    "tours": "37", "orleans": "45", "blois": "41", "bourges": "18", "chartres": "28", "le mans": "72", "angers": "49",
    "cholet": "49", "laval": "53", "la roche sur yon": "85", "caen": "14", "rouen": "76", "le havre": "76", "cherbourg": "50",
    "albi": "81", "montauban": "82", "rodez": "12", "tarbes": "65", "agen": "47", "ajaccio": "2A", "bastia": "2B",
    "fort de france": "972", "pointe a pitre": "971", "baie mahault": "971", "les abymes": "971", "cayenne": "973",
    "saint pierre (la reunion)": "974", "mamoudzou": "976",
}

FOREIGN = [
    "belgique", "belgium", "bruxelles", "brussels", "anvers", "antwerp", "liege", "gand", "luxembourg", "suisse", "switzerland",
    "geneve", "geneva", "zurich", "lausanne", "bale", "basel", "monaco", "espagne", "spain", "madrid", "barcelona", "barcelone",
    "italie", "italy", "milan", "milano", "rome", "allemagne", "germany", "deutschland", "berlin", "munich", "munchen", "frankfurt",
    "francfort", "hamburg", "royaume uni", "united kingdom", "england", "london", "londres", "edinburgh", "manchester", "ireland",
    "irlande", "dublin", "pays bas", "netherlands", "amsterdam", "rotterdam", "portugal", "lisbonne", "lisbon", "lisboa", "porto",
    "pologne", "poland", "warsaw", "varsovie", "krakow", "romania", "roumanie", "bucharest", "austria", "autriche", "wien",
    "sweden", "suede", "stockholm", "denmark", "copenhagen", "norway", "oslo", "finland", "helsinki", "malta", "malte", "cyprus",
    "chypre", "greece", "grece", "athens", "czech", "prague", "hungary", "budapest", "lithuania", "vilnius", "estonia", "tallinn",
    "latvia", "riga", "brazil", "bresil", "brasil", "sao paulo", "rio de janeiro", "peru", "perou", "lima", "mexico", "mexique",
    "colombia", "colombie", "bogota", "argentina", "argentine", "buenos aires", "chile", "chili", "santiago", "usa",
    "united states", "etats unis", "new york", "san francisco", "chicago", "miami", "canada", "montreal", "toronto",
    "vancouver", "quebec", "singapore", "singapour", "hong kong", "japan", "japon", "tokyo", "china", "chine", "shanghai",
    "india", "inde", "bangalore", "bengaluru", "mumbai", "dubai", "abu dhabi", "emirats", "uae", "israel", "tel aviv",
    "australia", "australie", "sydney", "maroc", "morocco", "casablanca", "rabat", "tunisie", "tunisia", "tunis", "algerie",
    "algeria", "alger", "senegal", "dakar", "cote d'ivoire", "ivory coast", "abidjan", "cameroun", "cameroon", "douala",
    "nigeria", "lagos", "kenya", "nairobi", "south africa", "afrique du sud", "johannesburg", "cape town", "egypt", "egypte",
    "cairo", "le caire", "turkey", "turquie", "istanbul", "philippines", "manila", "vietnam", "indonesia", "jakarta",
    "malaysia", "kuala lumpur", "haiti", "maurice", "mauritius", "madagascar", "gabon", "libreville", "congo", "kinshasa",
    "benin", "cotonou", "togo", "lome", "mali", "bamako", "burkina", "ouagadougou", "guinee", "conakry", "emea", "latam",
    "apac", "americas", "north america",
]

DOM_CC = {"fr", "fra", "france", "gp", "mq", "gf", "re", "yt", "pm", "bl", "mf"}


def _rx(words):
    return re.compile(r"(?<![a-z0-9])(" + "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True)) + r")(?![a-z0-9])")


_CITY_RX = _rx(CITIES)
_REGION_RX = _rx(REGION_ALIASES)
_FOREIGN_RX = _rx(FOREIGN)
_FR_RX = re.compile(r"(?<![a-z])(france|fr|francia|frankreich|metropole)(?![a-z])")
_CP_RX = re.compile(r"(?<!\d)((?:0[1-9]|[1-8]\d|9[0-5])\d{3}|97[1-6]\d{2}|20[0-6]\d{2})(?!\d)")


@dataclass
class Geo:
    status: str  # "fr" | "foreign" | "unknown"
    dept: str = ""
    region: str = ""


def _gnorm(s) -> str:
    return re.sub(r"\s+", " ", norm(s).replace("-", " ").replace("_", " ")).strip()


def dept_from_cp(cp: str) -> str:
    cp = str(cp or "").strip()
    if not re.fullmatch(r"\d{5}", cp):
        return ""
    if cp.startswith("97"):
        return cp[:3] if cp[:3] in DEPTS else ""
    if cp.startswith("20"):
        return "2A" if int(cp) < 20200 else "2B"
    return cp[:2] if cp[:2] in DEPTS else ""


def _with_dept(d: str) -> Geo:
    return Geo("fr", d, DEPTS[d][1]) if d in DEPTS else Geo("fr")


def classify(text, country=None) -> Geo:
    """Texte libre de lieu (+ code pays éventuel) -> Geo."""
    t = _gnorm(text)
    cc = _gnorm(country)
    fr_signal = None
    m = _CITY_RX.search(t)
    if m:
        fr_signal = _with_dept(CITIES[m.group(1)])
    else:
        m = _REGION_RX.search(t)
        if m:
            fr_signal = Geo("fr", "", REGION_ALIASES[m.group(1)])
        elif _FR_RX.search(t):
            fr_signal = Geo("fr")
    foreign = bool(_FOREIGN_RX.search(t))
    if not fr_signal and not foreign:
        m = _CP_RX.search(t)
        if m:
            fr_signal = _with_dept(dept_from_cp(m.group(1)))
    if cc:
        if cc in DOM_CC or cc.startswith("france"):
            return fr_signal or Geo("fr")
        return fr_signal or Geo("foreign")
    if fr_signal:
        return fr_signal
    return Geo("foreign") if foreign else Geo("unknown")


def from_ft(libelle: str, code_postal=None) -> Geo:
    """Lieu France Travail : « 75 - Paris 8e », « 99 - Belgique », « Ile-de-France », « France »."""
    lib = str(libelle or "")
    m = re.match(r"\s*(\d{2,3}|2A|2B)\s*-", lib, re.I)
    if m:
        code = m.group(1).upper()
        if code == "99":
            return Geo("foreign")
        if code in DEPTS:
            return _with_dept(code)
    d = dept_from_cp(code_postal)
    if d:
        return _with_dept(d)
    g = classify(lib)
    return Geo("fr") if g.status == "unknown" else g  # France Travail publie en France sauf mention contraire


def from_adzuna(area, display_name: str) -> Geo:
    area = [str(a) for a in (area or [])]
    if area and _gnorm(area[0]) != "france":
        return Geo("foreign")
    g = classify(" , ".join(area[1:] + [display_name or ""]))
    if g.status == "foreign":
        return g
    return g if g.status == "fr" else Geo("fr")


def region_of(dept: str) -> str:
    return DEPTS.get(dept, ("", ""))[1]

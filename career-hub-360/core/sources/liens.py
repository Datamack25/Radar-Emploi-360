"""Recherches pré-remplies sur les sites qui interdisent la collecte automatique (ouvertes par vous)."""
from __future__ import annotations

from urllib.parse import quote_plus


def deep_links(kw: str, lieu: str = "France", jours: int = 14) -> dict:
    q, l = quote_plus(kw), quote_plus(lieu or "France")
    return {
        "LinkedIn": f"https://www.linkedin.com/jobs/search/?keywords={q}&location={l}&geoId=105015875"
                    f"&f_TPR=r{jours * 86400}&f_E=1%2C2&f_JT=F%2CC%2CT",
        "Indeed": f"https://fr.indeed.com/jobs?q={q}&l={l}&fromage={jours}&sc=0kf%3Aexplvl%28ENTRY_LEVEL%29%3B",
        "Welcome to the Jungle": f"https://www.welcometothejungle.com/fr/jobs?query={q}"
                                 "&refinementList%5Boffices.country_code%5D%5B%5D=FR",
        "APEC": f"https://www.apec.fr/candidat/recherche-emploi.html/emploi?motsCles={q}",
        "HelloWork": f"https://www.hellowork.com/fr-fr/emploi/recherche.html?k={q}&l={l}",
        "France Travail (site)": f"https://candidat.francetravail.fr/offres/recherche?motsCles={q}&offresPartenaires=true"
                                 "&experience=1&typeContrat=CDI,CDD,MIS",
        "Jobteaser": f"https://www.jobteaser.com/fr/job-offers?q={q}&contract=cdi&contract=cdd",
        "Google Emploi": f"https://www.google.com/search?q={quote_plus(kw + ' emploi junior ' + (lieu or 'France'))}&ibp=htl;jobs",
    }

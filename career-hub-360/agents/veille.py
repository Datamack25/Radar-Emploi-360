"""Agent 4 — Veille marché & conseil : analyse le profil face au marché (état du marché, attentes des recruteurs,
rémunérations, plan d'action) avec les liens des sources. Deux volets indépendants :
- statistiques calculées sur les offres réellement collectées (sources = les offres elles-mêmes) ;
- recherche web par l'IA (sources citées), ou, sans IA, portails de référence à consulter.
"""
from __future__ import annotations

import json
import statistics
from collections import Counter
from datetime import datetime

from services.documents import markdown_to_docx, safe_filename, save_output, to_pdf
from services.keywords import SOFT, find_skills, skill_counts

from .base import DATA, OUTPUTS, Agent, AgentInfo, ensure_dirs, now_tag

REPORT = DATA / "veille_rapport.json"

REFERENCES_GENERALES = [
    ("APEC — études sur l'emploi cadre et les salaires", "https://corporate.apec.fr"),
    ("France Travail — statistiques et Besoins en main-d'œuvre (BMO)", "https://statistiques.francetravail.org"),
    ("DARES — études du ministère du Travail", "https://dares.travail-emploi.gouv.fr"),
    ("Insee — emploi et salaires", "https://www.insee.fr"),
    ("Glassdoor — salaires déclarés", "https://www.glassdoor.fr/Salaires/index.htm"),
    ("Michael Page — études de rémunération", "https://www.michaelpage.fr"),
    ("Hays — guide des salaires", "https://www.hays.fr"),
    ("Robert Walters — étude de rémunérations", "https://www.robertwalters.fr"),
]
REFERENCES_CONFORMITE = [
    ("ACPR — contrôle LCB-FT des banques et assurances", "https://acpr.banque-france.fr"),
    ("Tracfin — rapports annuels et tendances", "https://www.economie.gouv.fr/tracfin"),
    ("AMF — conformité et certification AMF", "https://www.amf-france.org"),
    ("GAFI / FATF — normes et listes de pays", "https://www.fatf-gafi.org"),
    ("ACAMS — certification CAMS", "https://www.acams.org"),
    ("DG Trésor — gel des avoirs et sanctions", "https://www.tresor.economie.gouv.fr/services-aux-entreprises/sanctions-economiques"),
]

SYSTEM = ("Tu es conseiller(ère) carrière et analyste du marché de l'emploi en France. Tu t'appuies sur des sources "
          "récentes et vérifiables, tu cites chaque donnée chiffrée, et tu distingues clairement les faits sourcés de tes "
          "recommandations. Si une donnée n'est pas trouvée, dis-le. Français clair et concret.")


class AgentVeille(Agent):
    info = AgentInfo(
        key="veille", nom="Agent Veille marché & conseil", icone="📡",
        mission="Recherche des informations récentes sur le marché de votre métier (tendances, attentes des recruteurs, "
                "salaires) et vous conseille sur votre profil, avec les liens des sources.",
        entrees=["Profil (ou métier saisi)", "Offres collectées (facultatif)", "IA avec recherche web (facultatif)"],
        sorties=["Rapport de veille sourcé (Word + PDF)", "Compétences attendues vs votre profil", "Statistiques des offres"])

    # ------------------------------------------------------------------ données des offres collectées
    def market_from_offers(self, family: str | None = None) -> dict:
        rows = [r for r in self.store.list() if r.get("status") != "Ignorée" and (not family or r.get("family") == family)]
        if not rows:
            return {"n": 0}
        sal = [((r["salary_min"] or r["salary_max"]) + (r["salary_max"] or r["salary_min"])) / 2
               for r in rows if r.get("salary_max") or r.get("salary_min")]
        skills = skill_counts([f"{r['title']} {r['description']}" for r in rows])
        return {
            "n": len(rows),
            "contrats": Counter(r.get("contract") or "Non précisé" for r in rows).most_common(),
            "junior_pct": round(100 * sum(1 for r in rows if r.get("exp_min") == 0 or r.get("junior")) / len(rows)),
            "employeurs": Counter(r["company"] for r in rows if "non communiqu" not in r["company"].lower()).most_common(12),
            "types": Counter(r.get("category") or "Autre" for r in rows).most_common(),
            "regions": Counter(r.get("region") or "Non précisée" for r in rows).most_common(8),
            "salaires": {"n": len(sal), "median": round(statistics.median(sal)) if sal else None,
                         "min": round(min(sal)) if sal else None, "max": round(max(sal)) if sal else None},
            "competences": skills.most_common(25),
            "exemples": [{"title": f"{r['title']} — {r['company']}", "url": r.get("apply_url") or r.get("url")}
                         for r in sorted(rows, key=lambda x: -x["score"])[:8]],
        }

    @staticmethod
    def gap(profile: dict, cv_text: str, market: dict) -> list[dict]:
        """Compétences attendues par le marché (part des offres) face au profil."""
        if not market.get("n"):
            return []
        mine = set(find_skills(" ".join([cv_text] + (profile.get("competences") or []) + (profile.get("outils") or [])
                                        + (profile.get("certifications") or []) + (profile.get("langues") or []))))
        out = []
        for s, c in market.get("competences", []):
            out.append({"Compétence": s, "Demandée dans (%)": round(100 * c / market["n"]), "Dans votre profil": s in mine,
                        "Type": "Savoir-être" if s in SOFT else "Technique"})
        return out

    # ------------------------------------------------------------------ rapport
    def references(self, profile: dict) -> list[tuple[str, str]]:
        conf = {"LCB-FT", "AML / CFT", "KYC", "Sanctions & embargos", "Conformité réglementaire"}
        txt = " ".join((profile.get("postes_cibles") or []) + (profile.get("competences") or []))
        refs = list(REFERENCES_GENERALES)
        if conf & set(find_skills(txt)) or profile.get("mode_filtre") == "conformite":
            refs = REFERENCES_CONFORMITE + refs
        return refs

    def build_report(self, profile: dict, cv_text: str, metier: str, lieu: str, use_ai: bool = True,
                     question: str = "") -> dict:
        return self.run_logged(self._build_report, profile, cv_text, metier, lieu, use_ai, question,
                               summary=lambda r: f"rapport ({len(r.get('sources', []))} sources)")

    def _build_report(self, profile, cv_text, metier, lieu, use_ai, question) -> dict:
        market = self.market_from_offers()
        refs = self.references(profile)
        date = datetime.now().strftime("%d/%m/%Y")
        stats_md = self._stats_md(market)
        if use_ai and self.llm.ok:
            year = datetime.now().year
            prompt = (
                f"Prépare une note de veille et de conseil pour un candidat qui vise : {metier} — {lieu} — date : {date}.\n"
                "Cherche sur le web des informations RÉCENTES (année en cours ou précédente) et cite les sources.\n"
                "Structure en Markdown, titres '## ' :\n"
                "## 1. Votre profil face au marché (forces, points à renforcer, positionnement)\n"
                "## 2. État du marché (dynamique de recrutement, secteurs et employeurs qui recrutent, tendances réglementaires "
                "ou technologiques qui créent des besoins)\n"
                "## 3. Ce qu'attendent les recruteurs (compétences, outils, certifications, savoir-être, niveau d'anglais)\n"
                "## 4. Rémunérations (fourchettes pour ce niveau d'expérience, Paris vs régions, par type d'employeur)\n"
                "## 5. Plan d'action concret (30 / 60 / 90 jours : formations, certifications, mots-clés à ajouter au CV, "
                "employeurs à cibler)\n"
                + (f"## 6. Réponse à la question du candidat : {question}\n" if question.strip() else "")
                + "Chaque chiffre doit être sourcé. Termine par une liste des sources consultées.\n"
                f"RECHERCHE: marché emploi {metier} France {year}\n"
                f"RECHERCHE: salaire {metier} junior {year}\n"
                f"RECHERCHE: compétences recherchées {metier} recrutement\n"
                f"RECHERCHE: tendances recrutement {metier} {year}\n\n"
                f"PROFIL DU CANDIDAT : {json.dumps({k: profile.get(k) for k in ('titre', 'experience_ans', 'postes_cibles', 'competences', 'outils', 'certifications', 'langues', 'formation')}, ensure_ascii=False)}\n\n"
                f"EXTRAIT DU CV :\n{cv_text[:5000]}\n\n"
                f"STATISTIQUES DES OFFRES COLLECTÉES PAR LA PLATEFORME (données réelles) :\n{stats_md}")
            text, sources = self.llm.research(SYSTEM, prompt)
            mode = f"IA avec recherche web — {self.llm.label}"
        else:
            text = self._rules_report(profile, cv_text, metier, lieu, market)
            sources = []
            mode = "Sans IA : statistiques des offres collectées + portails de référence"
        sources = sources + [{"title": t, "url": u} for t, u in refs if u not in {s["url"] for s in sources}]
        sources += [{"title": "Offre : " + e["title"], "url": e["url"]} for e in market.get("exemples", []) if e.get("url")]
        rep = {"date": date, "metier": metier, "lieu": lieu, "mode": mode, "markdown": text, "stats_md": stats_md,
               "sources": sources}
        DATA.mkdir(exist_ok=True)
        REPORT.write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
        return rep

    @staticmethod
    def last_report() -> dict | None:
        try:
            return json.loads(REPORT.read_text(encoding="utf-8")) if REPORT.exists() else None
        except (OSError, ValueError):
            return None

    @staticmethod
    def _stats_md(m: dict) -> str:
        if not m.get("n"):
            return "Aucune offre collectée pour l'instant (lancez l'Agent Chasseur d'offres)."
        s = m["salaires"]
        lines = [f"- Offres analysées : {m['n']}",
                 f"- Offres ouvertes aux débutants / juniors : {m['junior_pct']} %",
                 "- Contrats : " + ", ".join(f"{k} {v}" for k, v in m["contrats"]),
                 "- Types d'employeurs : " + ", ".join(f"{k} {v}" for k, v in m["types"][:6]),
                 "- Régions : " + ", ".join(f"{k} {v}" for k, v in m["regions"][:6]),
                 "- Employeurs qui publient le plus : " + ", ".join(f"{k} ({v})" for k, v in m["employeurs"][:8])]
        if s["n"]:
            lines.append(f"- Salaires affichés ({s['n']} offres) : médiane {s['median'] // 1000} k€, de {s['min'] // 1000} "
                         f"à {s['max'] // 1000} k€ brut annuel")
        else:
            lines.append("- Salaires : aucune offre n'affiche de salaire")
        lines.append("- Compétences les plus citées : " + ", ".join(f"{k} ({round(100 * v / m['n'])} %)"
                                                                    for k, v in m["competences"][:12]))
        return "\n".join(lines)

    def _rules_report(self, profile, cv_text, metier, lieu, market) -> str:
        g = self.gap(profile, cv_text, market)
        missing = [x for x in g if not x["Dans votre profil"] and x["Demandée dans (%)"] >= 15]
        have = [x for x in g if x["Dans votre profil"]]
        md = [f"## 1. Votre profil face aux offres collectées — {metier} ({lieu})"]
        if not market.get("n"):
            md.append("Aucune offre n'a encore été collectée : lancez la mise à jour des offres pour obtenir des statistiques "
                      "réelles sur votre marché.")
        else:
            md.append(f"Sur {market['n']} offres récentes correspondant à vos critères :")
            if have:
                md.append("- **Vos atouts reconnus** : " + ", ".join(f"{x['Compétence']} ({x['Demandée dans (%)']} % des offres)"
                                                                     for x in have[:8]))
            if missing:
                md.append("- **À renforcer ou à faire apparaître dans le CV** : "
                          + ", ".join(f"{x['Compétence']} ({x['Demandée dans (%)']} %)" for x in missing[:8]))
        md += ["", "## 2. Ce que montrent les offres", self._stats_md(market), "",
               "## 3. Recommandations",
               "- Reprenez dans votre CV les intitulés exacts des compétences les plus citées que vous possédez réellement.",
               "- Ciblez en priorité les types d'employeurs et les régions qui publient le plus d'offres ci-dessus.",
               "- Pour chaque compétence manquante très demandée : formation courte, certification ou projet personnel à "
               "mettre en avant.",
               "- Activez une IA (onglet Réglages) pour obtenir une analyse du marché appuyée sur des sources web récentes.",
               "", "## 4. Où vérifier l'état du marché et les salaires",
               "Les portails ci-dessous publient des études régulières (liens dans les sources)."]
        return "\n".join(md)

    # ------------------------------------------------------------------ export
    def export(self, rep: dict) -> tuple[bytes, bytes, str, tuple[str, str]]:
        md = (f"# Veille marché & conseil — {rep['metier']}\n{rep['lieu']} · {rep['date']} · {rep['mode']}\n---\n"
              f"{rep['markdown']}\n\n## Données des offres collectées\n{rep.get('stats_md', '')}\n\n## Sources\n"
              + "\n".join(f"- [{s['title']}]({s['url']})" for s in rep.get("sources", []) if s.get("url")))
        docx = markdown_to_docx(md)
        pdf, method = to_pdf(None, md)  # PDF ReportLab : liens cliquables
        ensure_dirs()
        base = f"Veille_{safe_filename(rep['metier'])}_{now_tag()}"
        paths = (save_output(OUTPUTS, base + ".docx", docx), save_output(OUTPUTS, base + ".pdf", pdf))
        try:
            self.store.add_document("Veille", rep["metier"], "", None, paths[0], paths[1], {})
        except Exception:  # noqa: BLE001
            pass
        return docx, pdf, method, paths

    def readiness(self) -> tuple[str, str]:
        r = self.last_report()
        ia = "recherche web IA" if self.llm.native_web else ("IA + recherche externe" if self.llm.ok else "sans IA")
        if r:
            return "ok", f"Dernier rapport : {r['date']} · {ia}"
        return "partiel", f"Aucun rapport · {ia}"

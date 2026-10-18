"""Agent 1 — Profil : lit le CV et la lettre modèles, en extrait le profil (postes visés, compétences, expérience…)
et pose un diagnostic du CV. Le profil enregistré sert de critères à la recherche d'offres et de contexte aux autres agents.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from core.config import EMPTY_PROFILE, load_user_profile, save_user_profile
from services.documents import SourceDoc, read_document
from services.keywords import find_skills

from .base import TEMPLATES, Agent, AgentInfo, ensure_dirs

TOOLS = {"Excel / VBA", "Python", "SQL", "Power BI", "Tableau", "Looker", "Jira", "Confluence", "SAS", "R", "Bloomberg",
         "World-Check / Refinitiv", "LexisNexis / Bridger", "Dow Jones Risk", "Fircosoft / Fircosoft Continuity",
         "Actimize / NICE", "Salesforce", "SAP", "Pack Office", "Machine learning / IA"}
CERTS = {"Certification AMF", "CAMS / ACAMS", "CFA"}
LANGS = {"Anglais professionnel", "Espagnol"}

ACTION_VERBS = re.compile(r"\b(analys|trait|piloté|pilot|réalis|realis|contrôl|control|rédig|redig|mis en place|déploy|deploy|"
                          r"conç|conc|automatis|optimis|coordonn|gér|ger|supervis|identifi|escalad|détect|detect|développ|develop)\w*",
                          re.I)
YEAR_RANGE = re.compile(r"((?:19|20)\d{2})\s*(?:-|–|—|à|a|to|>)\s*((?:19|20)\d{2}|aujourd'hui|aujourd’hui|présent|present|"
                        r"actuel|en cours|now|today)", re.I)

SYSTEM = ("Tu es un expert du recrutement en France. Tu extrais fidèlement les informations d'un CV, sans rien inventer. "
          "Si une information est absente, laisse le champ vide.")


class AgentProfil(Agent):
    info = AgentInfo(
        key="profil", nom="Agent Profil", icone="🧭",
        mission="Lit votre CV et votre lettre modèles, en tire votre profil (postes visés, compétences, expérience) "
                "et vérifie la qualité du CV.",
        entrees=["CV modèle (Word ou PDF)", "Lettre de motivation modèle (Word, PDF ou texte)"],
        sorties=["Profil enregistré (critères de recherche)", "Diagnostic du CV"])

    # ------------------------------------------------------------------ modèles
    @staticmethod
    def template_path(kind: str) -> Path | None:
        for ext in (".docx", ".pdf", ".txt", ".md"):
            p = TEMPLATES / f"{kind}{ext}"
            if p.exists():
                return p
        return None

    def save_template(self, kind: str, data: bytes, name: str) -> SourceDoc:
        ensure_dirs()
        ext = Path(name).suffix.lower()
        if ext not in (".docx", ".pdf", ".txt", ".md"):
            raise ValueError("Format accepté : .docx, .pdf ou .txt (les .doc anciens doivent être réenregistrés en .docx).")
        for old in TEMPLATES.glob(f"{kind}.*"):
            old.unlink()
        (TEMPLATES / f"{kind}{ext}").write_bytes(data)
        (TEMPLATES / f"{kind}_meta.json").write_text(json.dumps({"nom": name, "date": datetime.now().isoformat()}),
                                                     encoding="utf-8")
        doc = read_document(data, name)
        if not doc.text.strip():
            raise ValueError("Aucun texte lisible dans ce fichier (PDF scanné ?). Utilisez la version Word du document.")
        return doc

    def load_template(self, kind: str) -> SourceDoc | None:
        p = self.template_path(kind)
        if not p:
            return None
        try:
            meta = json.loads((TEMPLATES / f"{kind}_meta.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = {"nom": p.name}
        doc = read_document(p.read_bytes(), p.name)
        doc.name = meta.get("nom", p.name)
        return doc

    def delete_template(self, kind: str) -> None:
        for f in TEMPLATES.glob(f"{kind}*"):
            f.unlink()

    # ------------------------------------------------------------------ profil
    @staticmethod
    def current_profile() -> dict:
        return load_user_profile()

    def save_profile(self, p: dict) -> None:
        save_user_profile(p)
        self.cfg.user = load_user_profile()

    def extract(self, cv: SourceDoc, use_ai: bool = True) -> dict:
        return self.run_logged(self._extract, cv, use_ai, summary=lambda r: f"profil extrait ({len(r.get('competences', []))} compétences)")

    def _extract(self, cv: SourceDoc, use_ai: bool) -> dict:
        base = self.heuristic_profile(cv.text)
        if not (use_ai and self.llm.ok):
            return base
        schema = {k: ("liste de chaînes" if isinstance(v, list) else "nombre" if isinstance(v, int) else "texte")
                  for k, v in EMPTY_PROFILE.items() if k != "mode_filtre"}
        schema["experiences"] = "liste d'objets {poste, employeur, periode, realisations: liste}"
        prompt = (f"Extrait le profil de ce CV au format JSON avec exactement ces clés : {json.dumps(schema, ensure_ascii=False)}.\n"
                  "- experience_ans : années d'expérience professionnelle (alternances comprises), entier.\n"
                  "- postes_cibles : 3 à 6 intitulés de postes réalistes en France pour ce profil, au niveau adapté.\n"
                  "- mots_cles_recherche : 6 à 12 requêtes courtes pour un moteur d'offres d'emploi (intitulés et thèmes).\n"
                  "- competences : compétences métier ; outils : logiciels et langages.\n\nCV :\n" + cv.text[:15000])
        try:
            ai = self.llm.complete(SYSTEM, prompt, json_mode=True, max_tokens=3000)
        except Exception:  # noqa: BLE001 — repli sur l'extraction sans IA
            return base
        out = dict(base)
        for k, v in (ai or {}).items():
            if k in EMPTY_PROFILE and v not in (None, "", []):
                out[k] = v
        try:
            out["experience_ans"] = int(float(out.get("experience_ans") or 0))
        except (TypeError, ValueError):
            out["experience_ans"] = base["experience_ans"]
        return out

    @staticmethod
    def heuristic_profile(text: str) -> dict:
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        p = dict(EMPTY_PROFILE)
        p.update({k: [] for k, v in EMPTY_PROFILE.items() if isinstance(v, list)})
        for l in lines[:5]:
            if 1 < len(l.split()) <= 4 and not re.search(r"\d|@", l):
                p["nom"] = l.title() if l.isupper() else l
                break
        for l in lines[:10]:
            if l != p["nom"] and re.search(r"analyst|charg|consultant|officer|gestionnaire|ingénieur|ingenieur|manager|"
                                           r"chef|responsable|assistant|développeur|developpeur|auditeur|contrôleur|controleur", l, re.I) \
                    and len(l) < 90:
                p["titre"] = l
                break
        m = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text)
        p["email"] = m.group(0) if m else ""
        m = re.search(r"(?:\+33\s?|0)[1-9](?:[\s.-]?\d{2}){4}", text)
        p["telephone"] = m.group(0) if m else ""
        skills = find_skills(text)
        p["outils"] = [s for s in skills if s in TOOLS]
        p["certifications"] = [s for s in skills if s in CERTS]
        p["langues"] = [s for s in skills if s in LANGS]
        p["competences"] = [s for s in skills if s not in TOOLS | CERTS | LANGS]
        now = datetime.now().year
        total = 0
        for a, b in YEAR_RANGE.findall(text):
            end = now if not b[:2].isdigit() else int(b)
            if 0 <= end - int(a) <= 15:
                total += end - int(a)
        p["experience_ans"] = min(total, 40)
        conf = {"LCB-FT", "AML / CFT", "KYC", "Sanctions & embargos", "Conformité réglementaire", "Filtrage / screening"}
        if p["titre"]:
            p["postes_cibles"].append(re.sub(r"\s+[|•–-]\s+.*$", "", p["titre"])[:60])
        if conf & set(skills):
            p["postes_cibles"] += ["Analyste LCB-FT", "Analyste KYC", "Chargé de conformité", "Analyste sanctions embargos"]
            p["mode_filtre"] = "conformite"
        else:
            p["mode_filtre"] = "profil"
        p["postes_cibles"] = list(dict.fromkeys(p["postes_cibles"]))[:6]
        p["mots_cles_recherche"] = list(p["postes_cibles"])
        return p

    # ------------------------------------------------------------------ diagnostic du CV
    @staticmethod
    def diagnose(text: str) -> list[tuple[str, str, str]]:
        """Liste (niveau ok|warn|bad, point vérifié, conseil)."""
        out = []
        words = len(text.split())
        out.append(("ok" if 250 <= words <= 900 else "warn", f"Longueur : {words} mots",
                    "Un CV junior tient sur une page (300 à 700 mots environ)." if not 250 <= words <= 900 else "Longueur adaptée."))
        out.append(("ok" if re.search(r"[\w.+-]+@[\w-]+\.\w+", text) else "bad", "Adresse e-mail",
                    "Présente." if re.search(r"[\w.+-]+@[\w-]+\.\w+", text) else "Ajoutez une adresse e-mail professionnelle."))
        has_tel = re.search(r"(?:\+33\s?|0)[1-9](?:[\s.-]?\d{2}){4}", text)
        out.append(("ok" if has_tel else "warn", "Téléphone", "Présent." if has_tel else "Ajoutez un numéro de téléphone."))
        has_li = "linkedin" in text.lower()
        out.append(("ok" if has_li else "warn", "Profil LinkedIn", "Présent." if has_li else "Ajoutez l'URL de votre profil LinkedIn."))
        figures = len(re.findall(r"\d+\s?(?:%|k€|€|alertes|dossiers|clients|DS|transactions|contrôles|controles)", text, re.I))
        out.append(("ok" if figures >= 3 else "warn", f"Résultats chiffrés : {figures}",
                    "Bien : vos réalisations sont mesurables." if figures >= 3
                    else "Chiffrez vos réalisations (volumes d'alertes traitées, délais, taux…) : les recruteurs les cherchent."))
        verbs = len(ACTION_VERBS.findall(text))
        out.append(("ok" if verbs >= 6 else "warn", f"Verbes d'action : {verbs}",
                    "Bien." if verbs >= 6 else "Commencez vos lignes d'expérience par des verbes d'action (analysé, traité, rédigé…)."))
        skills = find_skills(text)
        out.append(("ok" if len(skills) >= 8 else "warn", f"Mots-clés métier reconnus : {len(skills)}",
                    "Bonne densité de mots-clés pour les logiciels de tri (ATS)." if len(skills) >= 8
                    else "Ajoutez les mots-clés de votre métier (outils, réglementations, méthodes) : les ATS filtrent dessus."))
        if re.search(r"\b(photo|âge|age\s*:|né le|nee le|situation familiale|marié|mariée)\b", text, re.I):
            out.append(("warn", "Informations personnelles", "Âge, situation familiale ou photo ne sont pas attendus en France "
                                                              "et ne doivent pas être exigés : vous pouvez les retirer."))
        return out

    def readiness(self) -> tuple[str, str]:
        p = load_user_profile()
        cv = self.template_path("cv")
        if cv and p.get("postes_cibles"):
            return "ok", "CV modèle et profil enregistrés"
        if cv or p.get("postes_cibles"):
            return "partiel", "Profil incomplet"
        return "manque", "Importez votre CV modèle"

"""Agent 3 — Rédacteur : adapte le CV et la lettre de motivation modèles à une offre collée par l'utilisateur.

Règles :
- rien n'est inventé : ni expérience, ni diplôme, ni employeur, ni date, ni chiffre. Une compétence absente du CV n'est
  ajoutée que si l'utilisateur coche qu'il la possède ;
- modèle Word → réécriture paragraphe par paragraphe, mise en page conservée ; les modifications qui ajoutent un chiffre
  inconnu du CV ou qui allongent trop un paragraphe (risque de 2e page) sont annulées et signalées ;
- export Word (.docx) et PDF.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime

from services.documents import (SourceDoc, apply_edits, fill_placeholders, markdown_to_docx, plain_letter_docx,
                                safe_filename, save_output, to_pdf)
from services.keywords import find_skills, guess_offer_fields, match_report

from .base import OUTPUTS, Agent, AgentInfo, ensure_dirs, now_tag

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
ROLE_RX = re.compile(r"analyst|charg|consultant|officer|gestionnaire|ingénieur|ingenieur|manager|chef|responsable|assistant|"
                     r"développeur|developpeur|auditeur|contrôleur|controleur|specialist|spécialiste|juriste|comptable", re.I)
SKILL_HDR = re.compile(r"comp[ée]tences|skills|outils|savoir-faire|expertises?", re.I)
NUM_RX = re.compile(r"\d+(?:[.,]\d+)?")

SYSTEM = (
    "Tu es un expert du recrutement en France (banque, finance, conformité et métiers d'analyse) et un rédacteur de CV et de "
    "lettres de motivation. Règle absolue : tu n'inventes RIEN. Pas d'expérience, de poste, d'employeur, de diplôme, de "
    "certification, de date ni de chiffre qui ne figure pas dans le CV fourni. Tu peux reformuler, réordonner, mettre en "
    "avant ce qui est pertinent pour l'offre et reprendre le vocabulaire exact de l'offre quand il décrit fidèlement une "
    "réalité du CV. Français professionnel, sobre, sans formules creuses.")


def today_fr() -> str:
    d = datetime.now()
    return f"{d.day} {MOIS[d.month - 1]} {d.year}"


@dataclass
class Result:
    kind: str
    docx: bytes
    pdf: bytes
    pdf_method: str
    text: str
    changes: list = field(default_factory=list)  # (avant, après, raison)
    warnings: list = field(default_factory=list)
    score_before: int = 0
    score_after: int = 0
    missing: list = field(default_factory=list)
    paths: tuple = ("", "")


class AgentRedacteur(Agent):
    info = AgentInfo(
        key="redacteur", nom="Agent Rédacteur CV & lettre", icone="✍️",
        mission="Adapte votre CV et votre lettre de motivation modèles à l'offre que vous collez, sans rien inventer, "
                "et les exporte en Word et en PDF.",
        entrees=["Texte de l'offre (copier-coller)", "CV modèle", "Lettre modèle (facultative)"],
        sorties=["CV adapté (.docx + .pdf)", "Lettre adaptée (.docx + .pdf)", "Score de correspondance avant / après"])

    # ------------------------------------------------------------------ analyse de l'offre
    def analyze_offer(self, text: str, use_ai: bool = True) -> dict:
        base = guess_offer_fields(text)
        base.update({"missions": [], "soft_skills": [], "resume": ""})
        if not (use_ai and self.llm.ok):
            return base
        prompt = ("Analyse cette offre d'emploi. Réponds en JSON avec les clés : poste (intitulé sans H/F), entreprise, lieu, "
                  "contrat, experience (exigée), missions (liste courte), competences_requises (liste : savoir-faire, "
                  "réglementations, outils), soft_skills (liste), mots_cles (les 10 à 15 termes qu'un logiciel de tri (ATS) "
                  "chercherait), resume (2 phrases).\n\nOFFRE :\n" + text[:12000])
        try:
            ai = self.llm.complete(SYSTEM, prompt, json_mode=True, max_tokens=2000)
        except Exception:  # noqa: BLE001
            return base
        for k, v in (ai or {}).items():
            if v not in (None, "", []):
                base[k] = v
        return base

    # ------------------------------------------------------------------ CV
    @staticmethod
    def guess_title_idx(cv: SourceDoc) -> int | None:
        for p in cv.paragraphs[:10]:
            if p.editable and ROLE_RX.search(p.text) and len(p.text) < 100:
                return p.idx
        return None

    @staticmethod
    def guess_skills_idx(cv: SourceDoc) -> int | None:
        best, best_n = None, 0
        for p in cv.paragraphs:
            if not p.editable or len(p.text) > 400:
                continue
            n = len(find_skills(p.text)) + (3 if SKILL_HDR.search(p.text) and re.search(r"[,;•|·]", p.text) else 0)
            if n > best_n and len(re.findall(r"[,;•|·]", p.text)) >= 2:
                best, best_n = p.idx, n
        return best

    def adapt_cv(self, cv: SourceDoc, offer_text: str, offer: dict, confirmed: list[str] | None = None,
                 use_ai: bool = True, title_idx: int | None = None, skills_idx: int | None = None,
                 change_title: bool = True, instructions: str = "") -> Result:
        return self.run_logged(self._adapt_cv, cv, offer_text, offer, confirmed or [], use_ai, title_idx, skills_idx,
                               change_title, instructions,
                               summary=lambda r: f"CV adapté : {r.score_before} → {r.score_after}/100")

    def _adapt_cv(self, cv, offer_text, offer, confirmed, use_ai, title_idx, skills_idx, change_title, instructions) -> Result:
        before = match_report(cv.text, offer_text)
        if use_ai and self.llm.ok:
            res = self._cv_ai_docx(cv, offer_text, offer, confirmed, instructions) if cv.is_docx \
                else self._cv_ai_text(cv, offer_text, offer, confirmed, instructions)
        else:
            res = self._cv_rules(cv, offer, confirmed, title_idx, skills_idx, change_title)
        after = match_report(res.text, offer_text)
        res.score_before, res.score_after, res.missing = before["score"], after["score"], after["missing"]
        return self._save(res, "CV", offer)

    def _guard(self, cv_text: str, old: str, new: str) -> str | None:
        """Raison du refus d'une modification, ou None si elle est acceptable."""
        known = set(NUM_RX.findall(cv_text))
        added = [n for n in NUM_RX.findall(new) if n not in known]
        if added:
            return f"chiffre absent du CV ({', '.join(added[:3])})"
        if len(new) > 1.5 * len(old) + 40:
            return "paragraphe trop allongé (risque de déborder sur une 2e page)"
        return None

    def _cv_ai_docx(self, cv, offer_text, offer, confirmed, instructions) -> Result:
        seen, items = set(), []
        for p in cv.paragraphs:
            if p.editable and p.text.strip() and p.text not in seen:
                seen.add(p.text)
                items.append({"i": p.idx, "t": p.text})
        prompt = (
            "Adapte ce CV (modèle Word découpé en paragraphes numérotés) à l'offre ci-dessous.\n"
            "Consignes :\n"
            "- Ne renvoie QUE les paragraphes à modifier. Le nombre de paragraphes ne change pas.\n"
            "- Garde chaque paragraphe à une longueur proche de l'original (±15 %) pour conserver la mise en page sur une page.\n"
            "- Ne touche pas au nom, aux coordonnées, aux dates, aux noms d'employeurs ni aux diplômes.\n"
            "- Priorités : titre du CV aligné sur l'intitulé de l'offre (si c'est cohérent avec le parcours), accroche / profil "
            "ciblé sur l'offre, lignes d'expérience reformulées avec le vocabulaire de l'offre, compétences réordonnées "
            "(les plus demandées d'abord).\n"
            f"- Compétences que le candidat confirme posséder et que tu peux ajouter : {', '.join(confirmed) or 'aucune'}.\n"
            "- Aucun nouveau chiffre.\n"
            + (f"- Consigne du candidat : {instructions}\n" if instructions.strip() else "")
            + 'Réponds en JSON : {"modifications": [{"i": numéro, "texte": "nouveau texte", "raison": "pourquoi"}], '
              '"points_a_verifier": ["…"]}\n\n'
            f"ANALYSE DE L'OFFRE : {json.dumps(offer, ensure_ascii=False)[:3000]}\n\nOFFRE :\n{offer_text[:8000]}\n\n"
            f"PARAGRAPHES DU CV :\n{json.dumps(items, ensure_ascii=False)}")
        ai = self.llm.complete(SYSTEM, prompt, json_mode=True, max_tokens=6000)
        valid = {it["i"]: it["t"] for it in items}
        edits, changes, warnings = {}, [], list((ai or {}).get("points_a_verifier") or [])
        for m in (ai or {}).get("modifications") or []:
            try:
                i = int(m.get("i"))
            except (TypeError, ValueError):
                continue
            new = str(m.get("texte") or "").strip()
            if i not in valid or not new or new == valid[i]:
                continue
            why = self._guard(cv.text, valid[i], new)
            if why:
                warnings.append(f"Modification annulée — {why} : « {new[:90]}… »")
                continue
            edits[i] = new
            changes.append((valid[i], new, str(m.get("raison") or "")))
        data = apply_edits(cv.data, edits)
        text = cv.text
        for old, new, _ in changes:
            text = text.replace(old, new)
        pdf, method = to_pdf(data, text)
        return Result("CV", data, pdf, method, text, changes, warnings)

    def _cv_ai_text(self, cv, offer_text, offer, confirmed, instructions) -> Result:
        prompt = (
            "Réécris ce CV (extrait d'un PDF ou d'un texte) en l'adaptant à l'offre. Format Markdown : '# Prénom Nom' puis "
            "une ligne de titre, une ligne de coordonnées, puis des sections '## …' (Profil, Expériences, Formation, "
            "Compétences, Langues…) avec des puces '- '. Une page maximum. Garde toutes les informations factuelles "
            "(employeurs, dates, diplômes) à l'identique ; aucun nouveau chiffre.\n"
            f"Compétences que le candidat confirme posséder : {', '.join(confirmed) or 'aucune'}.\n"
            + (f"Consigne du candidat : {instructions}\n" if instructions.strip() else "")
            + 'Réponds en JSON : {"cv_markdown": "…", "changements": ["…"], "points_a_verifier": ["…"]}\n\n'
            f"ANALYSE DE L'OFFRE : {json.dumps(offer, ensure_ascii=False)[:3000]}\n\nOFFRE :\n{offer_text[:8000]}\n\nCV :\n{cv.text[:12000]}")
        ai = self.llm.complete(SYSTEM, prompt, json_mode=True, max_tokens=6000)
        md = str((ai or {}).get("cv_markdown") or "").strip()
        if not md:
            raise ValueError("L'IA n'a pas renvoyé de CV.")
        warnings = list((ai or {}).get("points_a_verifier") or [])
        added = sorted(set(NUM_RX.findall(md)) - set(NUM_RX.findall(cv.text)))
        if added:
            warnings.insert(0, f"Chiffres absents du CV d'origine à vérifier : {', '.join(added[:8])}")
        data = markdown_to_docx(md)
        pdf, method = to_pdf(data, md)
        changes = [("", c, "") for c in (ai or {}).get("changements") or []]
        return Result("CV", data, pdf, method, md, changes, warnings)

    def _cv_rules(self, cv, offer, confirmed, title_idx, skills_idx, change_title) -> Result:
        asked = offer.get("competences_requises") or []
        changes, warnings, edits = [], [], {}
        by_idx = {p.idx: p.text for p in cv.paragraphs}
        poste = re.sub(r"\s*\(?\b[hf]\s*/\s*[hf]\b\)?", "", str(offer.get("poste") or ""), flags=re.I).strip(" -–|")
        if change_title and title_idx is not None and poste and title_idx in by_idx:
            edits[title_idx] = poste
            changes.append((by_idx[title_idx], poste, "Titre aligné sur l'intitulé de l'offre"))
        if skills_idx is not None and skills_idx in by_idx:
            old = by_idx[skills_idx]
            m = re.match(r"^(\s*[^:]{2,40}:\s*)(.*)$", old)
            label, body = (m.group(1), m.group(2)) if m else ("", old)
            sep = next((s for s in (" • ", " | ", " · ", "; ", ", ") if s.strip() in body), ", ")
            items = [x.strip() for x in re.split(r"\s*[,;•|·]\s*", body) if x.strip()]
            asked_set = set(asked)
            items.sort(key=lambda x: 0 if set(find_skills(x)) & asked_set else 1)
            have = set(find_skills(cv.text))
            extra = [c for c in confirmed if c not in have and c.lower() not in body.lower()]
            new = label + sep.join(items + extra)
            if new != old:
                edits[skills_idx] = new
                changes.append((old, new, "Compétences demandées par l'offre placées en premier"
                                + (f" ; ajout de : {', '.join(extra)}" if extra else "")))
        if cv.is_docx:
            data = apply_edits(cv.data, edits)
            text = cv.text
            for old, new, _ in changes:
                text = text.replace(old, new, 1)
            pdf, method = to_pdf(data, text)
        else:
            lines = [by_idx.get(p.idx) if p.idx not in edits else edits[p.idx] for p in cv.paragraphs]
            if confirmed and skills_idx is None:
                lines.insert(min(3, len(lines)), "## Compétences clés pour ce poste")
                lines.insert(min(4, len(lines)), " • ".join(confirmed))
            text = "\n".join(l for l in lines if l)
            data = markdown_to_docx(text)
            pdf, method = to_pdf(data, text)
            warnings.append("Modèle PDF : le CV est reconstruit dans une mise en page simple. Importez la version Word "
                            "de votre CV pour garder votre mise en page.")
        if not changes:
            warnings.append("Aucune modification : choisissez le paragraphe du titre et celui des compétences, ou activez l'IA.")
        return Result("CV", data, pdf, method, text, changes, warnings)

    # ------------------------------------------------------------------ lettre
    def adapt_letter(self, letter: SourceDoc | None, cv_text: str, offer_text: str, offer: dict, profile: dict,
                     use_ai: bool = True, replacements: dict | None = None, instructions: str = "") -> Result:
        return self.run_logged(self._adapt_letter, letter, cv_text, offer_text, offer, profile, use_ai, replacements or {},
                               instructions, summary=lambda r: f"lettre adaptée ({r.pdf_method})")

    def _letter_values(self, offer, profile, cv_text) -> dict:
        matched = [s for s in (offer.get("competences_requises") or []) if s in set(find_skills(cv_text))]
        return {"POSTE": str(offer.get("poste") or ""), "ENTREPRISE": str(offer.get("entreprise") or "votre entreprise"),
                "LIEU": str(offer.get("lieu") or ""), "CONTRAT": str(offer.get("contrat") or ""), "DATE": today_fr(),
                "NOM": profile.get("nom", ""), "VILLE": (profile.get("localisation") or "Paris").split(",")[0],
                "COMPETENCES": ", ".join(matched[:4]) or ", ".join((profile.get("competences") or [])[:4]),
                "EMAIL": profile.get("email", ""), "TELEPHONE": profile.get("telephone", "")}

    def _adapt_letter(self, letter, cv_text, offer_text, offer, profile, use_ai, replacements, instructions) -> Result:
        vals = self._letter_values(offer, profile, cv_text)
        if use_ai and self.llm.ok:
            return self._save(self._letter_ai(letter, cv_text, offer_text, offer, profile, vals, instructions), "Lettre", offer)
        changes, warnings = [], []
        if letter and letter.is_docx:
            data = fill_placeholders(letter.data, vals)
            edits = {}
            for p in letter.paragraphs:
                new = p.text
                for old, rep in replacements.items():
                    if old and old in new:
                        new = new.replace(old, rep)
                new = re.sub(r"\b\d{1,2}(?:er)? (?:" + "|".join(MOIS) + r") \d{4}\b", vals["DATE"], new)
                if new != p.text and p.editable:
                    edits[p.idx] = new
                    changes.append((p.text, new, "Remplacement"))
            data = apply_edits(data, edits) if edits else data
            text = "\n".join(p.text for p in letter.paragraphs)
            for k, v in vals.items():
                text = re.sub(r"\{\{\s*" + k + r"\s*\}\}", v, text, flags=re.I)
            for old, new, _ in changes:
                text = text.replace(old, new)
            if "{{" not in letter.text and not replacements:
                warnings.append("Votre lettre modèle n'a pas de balises {{POSTE}}, {{ENTREPRISE}}… : seule la date a pu être "
                                "mise à jour. Ajoutez ces balises au modèle, utilisez les remplacements, ou activez l'IA.")
            pdf, method = to_pdf(data, text, letter=True)
            return self._save(Result("Lettre", data, pdf, method, text, changes, warnings), "Lettre", offer)
        if letter:
            text = letter.text
            for k, v in vals.items():
                text = re.sub(r"\{\{\s*" + k + r"\s*\}\}", v, text, flags=re.I)
            for old, rep in replacements.items():
                if old:
                    text = text.replace(old, rep)
            lines = [l for l in text.splitlines() if l.strip()]
        else:
            lines = self._default_letter(vals, profile)
            warnings.append("Lettre générée à partir d'un modèle standard : relisez-la et personnalisez le 2e paragraphe.")
        data = plain_letter_docx(lines)
        pdf, method = to_pdf(data, "\n\n".join(lines), letter=True)
        return self._save(Result("Lettre", data, pdf, method, "\n".join(lines), changes, warnings), "Lettre", offer)

    @staticmethod
    def _default_letter(v: dict, profile: dict) -> list[str]:
        nom = v["NOM"] or "Prénom Nom"
        exp = profile.get("experience_ans") or 0
        titre = profile.get("titre") or "professionnel(le)"
        return [
            nom, " · ".join(x for x in (v["EMAIL"], v["TELEPHONE"]) if x),
            f"{v['VILLE']}, le {v['DATE']}",
            v["ENTREPRISE"] or "Service recrutement",
            f"Objet : candidature au poste de {v['POSTE'] or '[intitulé du poste]'}",
            "Madame, Monsieur,",
            f"Actuellement {titre.lower()} avec {exp} an{'s' if exp > 1 else ''} d'expérience, je souhaite rejoindre "
            f"{v['ENTREPRISE'] or 'votre entreprise'} en tant que {v['POSTE'] or '[poste]'}.",
            f"Mon parcours m'a permis de développer des compétences directement utiles au poste : {v['COMPETENCES'] or '[compétences]'}. "
            "[Décrivez ici une réalisation concrète et mesurable en lien avec l'offre.]",
            f"Rejoindre {v['ENTREPRISE'] or 'votre équipe'} représente pour moi l'occasion de [ce qui vous attire chez cet employeur]. "
            "Je serais heureux(se) de vous exposer ma motivation lors d'un entretien.",
            "Je vous prie d'agréer, Madame, Monsieur, l'expression de mes salutations distinguées.",
            nom]

    def _letter_ai(self, letter, cv_text, offer_text, offer, profile, vals, instructions) -> Result:
        common = (f"Date du jour : {vals['DATE']}. Ville du candidat : {vals['VILLE']}.\n"
                  + (f"Consigne du candidat : {instructions}\n" if instructions.strip() else "")
                  + f"ANALYSE DE L'OFFRE : {json.dumps(offer, ensure_ascii=False)[:3000]}\n\nOFFRE :\n{offer_text[:7000]}\n\n"
                  f"CV DU CANDIDAT :\n{cv_text[:9000]}\n\n")
        rules = ("Lettre de motivation française, une page, 250 à 350 mots pour le corps : accroche liée à l'entreprise et "
                 "au poste, 1 paragraphe sur ce que le candidat apporte (preuves tirées du CV, vocabulaire de l'offre), "
                 "1 paragraphe sur la motivation pour cet employeur, conclusion avec demande d'entretien, formule de "
                 "politesse. Aucun fait inventé ; si une information manque (nom du recruteur…), reste générique.\n")
        if letter and letter.is_docx:
            seen, items = set(), []
            for p in letter.paragraphs:
                if p.editable and p.text not in seen:
                    seen.add(p.text)
                    items.append({"i": p.idx, "t": p.text})
            prompt = (rules + "Voici la lettre modèle du candidat découpée en paragraphes numérotés. Adapte-la à l'offre en "
                      "gardant sa structure et son ton : renvoie les paragraphes à modifier (date, destinataire, objet, "
                      "corps…). Un paragraphe peut contenir des retours à la ligne (\\n) si nécessaire.\n"
                      'Réponds en JSON : {"modifications": [{"i": numéro, "texte": "…", "raison": "…"}], '
                      '"points_a_verifier": ["…"]}\n\n' + common + f"LETTRE MODÈLE :\n{json.dumps(items, ensure_ascii=False)}")
            ai = self.llm.complete(SYSTEM, prompt, json_mode=True, max_tokens=5000)
            valid = {it["i"]: it["t"] for it in items}
            edits, changes = {}, []
            for m in (ai or {}).get("modifications") or []:
                try:
                    i = int(m.get("i"))
                except (TypeError, ValueError):
                    continue
                new = str(m.get("texte") or "").strip()
                if i in valid and new and new != valid[i]:
                    edits[i] = new
                    changes.append((valid[i], new, str(m.get("raison") or "")))
            data = apply_edits(fill_placeholders(letter.data, vals), edits)
            text = letter.text
            for old, new, _ in changes:
                text = text.replace(old, new)
            warnings = list((ai or {}).get("points_a_verifier") or [])
            pdf, method = to_pdf(data, text, letter=True)
            return Result("Lettre", data, pdf, method, text, changes, warnings)
        model_hint = f"S'inspirer du style de cette lettre modèle :\n{letter.text[:5000]}\n\n" if letter else ""
        prompt = (rules + model_hint + "Réponds en JSON : {\"lignes\": [\"bloc expéditeur\", \"lieu et date\", "
                  "\"destinataire\", \"Objet : …\", \"Madame, Monsieur,\", \"paragraphe 1\", \"paragraphe 2\", \"paragraphe 3\", "
                  "\"paragraphe 4\", \"formule de politesse\", \"signature\"], \"points_a_verifier\": [\"…\"]}\n\n" + common
                  + f"Coordonnées : {vals['NOM']} · {vals['EMAIL']} · {vals['TELEPHONE']}")
        ai = self.llm.complete(SYSTEM, prompt, json_mode=True, max_tokens=4000)
        lines = [str(x).strip() for x in (ai or {}).get("lignes") or [] if str(x).strip()]
        if not lines:
            raise ValueError("L'IA n'a pas renvoyé de lettre.")
        data = plain_letter_docx(lines)
        pdf, method = to_pdf(data, "\n\n".join(lines), letter=True)
        return Result("Lettre", data, pdf, method, "\n".join(lines), [], list((ai or {}).get("points_a_verifier") or []))

    # ------------------------------------------------------------------ enregistrement
    def _save(self, res: Result, kind: str, offer: dict) -> Result:
        ensure_dirs()
        nom = safe_filename(self.cfg.user.get("nom") or "candidat")
        comp = safe_filename(offer.get("entreprise") or "entreprise")
        base = f"{kind}_{nom}_{comp}_{now_tag()}"
        pdocx = save_output(OUTPUTS, base + ".docx", res.docx)
        ppdf = save_output(OUTPUTS, base + ".pdf", res.pdf)
        res.paths = (pdocx, ppdf)
        try:
            self.store.add_document(kind, str(offer.get("poste") or ""), str(offer.get("entreprise") or ""),
                                    offer.get("uid"), pdocx, ppdf,
                                    {"score_avant": res.score_before, "score_apres": res.score_after})
        except Exception:  # noqa: BLE001
            pass
        return res

    def readiness(self) -> tuple[str, str]:
        from .profil import AgentProfil
        cv, lm = AgentProfil.template_path("cv"), AgentProfil.template_path("lettre")
        ia = "IA active" if self.llm.ok else "sans IA (règles)"
        if cv and lm:
            return "ok", f"CV et lettre modèles prêts · {ia}"
        if cv:
            return "partiel", f"CV prêt, lettre modèle absente (lettre standard) · {ia}"
        return "manque", "Importez un CV modèle"

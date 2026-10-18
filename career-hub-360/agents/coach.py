"""Agent 5 — Coach entretien : prépare l'entretien pour une offre donnée (questions probables, éléments attendus,
conseils tirés du CV), évalue vos réponses et exporte une fiche de préparation (Word + PDF).
"""
from __future__ import annotations

import json
import re

from services.documents import markdown_to_docx, safe_filename, save_output, to_pdf
from services.keywords import SOFT, find_skills

from .base import OUTPUTS, Agent, AgentInfo, ensure_dirs, now_tag

# Banque de questions reprise des Career Hub (conformité, finance, communication) + questions transverses
BANK = [
    ("Technique", "Quels sont les signaux d'alerte (red flags) d'une opération de blanchiment ?",
     "Structurez : placement / empilement / intégration, puis 3-4 indicateurs concrets (flux incohérents avec le profil, "
     "pays à risque, fractionnement, sociétés écrans).", {"LCB-FT", "AML / CFT", "Surveillance transactionnelle"}),
    ("Technique", "Comment traitez-vous une alerte de filtrage avec un homonyme probable ?",
     "Données d'identité (date / lieu de naissance, nationalité), sources complémentaires, documentation de la levée de "
     "doute, escalade si doute résiduel.", {"Filtrage / screening", "Sanctions & embargos"}),
    ("Technique", "Quelle différence entre sanctions, embargos et gel des avoirs ?",
     "Sanctions = cadre général ; embargo = restriction sur biens / services / pays ; gel des avoirs = immobilisation des "
     "fonds de personnes ou entités listées. Citez UE, ONU, OFAC, DG Trésor.", {"Sanctions & embargos"}),
    ("Technique", "Comment gérez-vous un client PPE lors d'une entrée en relation ?",
     "Vigilance renforcée : origine du patrimoine et des fonds, validation hiérarchique, revue plus fréquente, surveillance accrue.",
     {"PPE / PEP", "KYC", "Due diligence / EDD"}),
    ("Technique", "Qu'est-ce que la correspondance bancaire et quels en sont les risques ?",
     "Relation entre banques pour services transfrontaliers ; risques : nesting, clients opaques de la banque cliente, pays "
     "à risque ; questionnaire Wolfsberg, approbation de la direction.", {"Correspondance bancaire"}),
    ("Technique", "Quand et comment rédiger une déclaration de soupçon ?",
     "Faits objectifs, chronologie, montants, motifs du soupçon, pièces ; déclaration à Tracfin sans informer le client.",
     {"Déclaration de soupçon (Tracfin)", "LCB-FT"}),
    ("Technique", "Comment distinguez-vous un faux positif d'un vrai positif ?",
     "Critères de rapprochement, score de similarité, éléments discriminants, traçabilité de la décision.",
     {"Filtrage / screening", "Surveillance transactionnelle"}),
    ("Technique", "Comment détecteriez-vous un contournement de sanctions ?",
     "Transbordements, pays tiers de rebond, sociétés écrans, biens à double usage, incohérences documentaires.",
     {"Sanctions & embargos", "Contrôle des exportations"}),
    ("Technique", "Comment identifiez-vous le bénéficiaire effectif d'une société ?",
     "Seuil de 25 % du capital ou des droits de vote, contrôle par d'autres moyens, registre des bénéficiaires effectifs, "
     "documentation et cohérence.", {"Bénéficiaires effectifs (UBO)", "KYC", "KYB"}),
    ("Technique", "Expliquez l'approche par les risques à un non-spécialiste.",
     "Classer clients / produits / pays / canaux par niveau de risque et proportionner les mesures de vigilance.",
     {"Approche par les risques", "Conformité réglementaire"}),
    ("Technique", "Expliquez la VaR (Value at Risk) à un non-initié.",
     "Perte maximale probable sur un horizon donné avec un niveau de confiance ; limites : queues de distribution, hypothèses.",
     {"Valeur à risque (VaR)", "Gestion des risques", "Marchés financiers"}),
    ("Technique", "Comment analysez-vous la solidité financière d'une entreprise qui demande un crédit ?",
     "Activité, rentabilité, structure financière (endettement, fonds propres), liquidité, flux de trésorerie, garanties, "
     "ratios clés et tendances.", {"Risque de crédit", "Analyse financière"}),
    ("Technique", "Quelle différence entre audit interne et contrôle permanent ?",
     "Contrôle permanent = 1er et 2e niveaux, continu ; audit interne = 3e niveau, périodique et indépendant.",
     {"Contrôle permanent", "Contrôle interne", "Audit"}),
    ("Technique", "Comment utilisez-vous Excel, SQL ou Python dans vos analyses ?",
     "Exemples concrets : contrôles de cohérence, rapprochements, détection d'anomalies, automatisation ; restez factuel.",
     {"Excel / VBA", "SQL", "Python"}),
    ("Technique", "Comment recueillez-vous et formalisez-vous un besoin métier ?",
     "Ateliers, questions ouvertes, reformulation, user stories / spécifications, critères d'acceptation, validation.",
     {"Business analysis", "Gestion de projet", "Agile / Scrum"}),
    ("Technique", "Comment mesurer le retour sur investissement d'une campagne de communication ?",
     "Objectifs SMART, indicateurs (portée, engagement, conversions, coût par résultat), outils de suivi, bilan.", set()),
]
TRANSVERSES = [
    ("Présentation", "Présentez-vous en deux minutes.",
     "Fil conducteur : formation → expériences → ce que vous savez faire → pourquoi ce poste. Terminez par l'offre."),
    ("Motivation", "Pourquoi notre entreprise et pourquoi ce poste ?",
     "Citez un élément précis de l'entreprise (activité, actualité, valeurs) et reliez-le à votre parcours."),
    ("Comportemental", "Racontez une situation où vous avez dû traiter un dossier complexe sous contrainte de délai.",
     "Méthode STAR : Situation, Tâche, Action (la vôtre), Résultat chiffré si possible."),
    ("Comportemental", "Parlez-nous d'une erreur que vous avez commise et de ce que vous en avez retenu.",
     "Erreur réelle mais maîtrisée, action corrective, enseignement, ce que vous faites différemment aujourd'hui."),
    ("Mise en situation", "Votre manager vous demande de valider un dossier que vous jugez risqué. Que faites-vous ?",
     "Faits, analyse du risque, référence à la procédure, escalade argumentée, traçabilité ; ni blocage ni complaisance."),
    ("Projection", "Où vous voyez-vous dans trois ans ?",
     "Montée en compétences dans le métier, responsabilités progressives, cohérence avec les perspectives du poste."),
    ("Rémunération", "Quelles sont vos prétentions salariales ?",
     "Donnez une fourchette fondée sur le marché (voir l'Agent Veille) et votre expérience ; restez ouvert sur le package."),
]
QUESTIONS_A_POSER = [
    "À quoi ressemble une journée type dans l'équipe ? Quel volume de dossiers / alertes ?",
    "Quels outils utilisez-vous au quotidien ?",
    "Comment se passe l'intégration et la formation les premiers mois ?",
    "Quels sont les principaux enjeux de l'équipe pour l'année à venir ?",
    "Comment la performance est-elle évaluée sur ce poste ?",
    "Quelles sont les prochaines étapes du processus de recrutement ?",
]

SYSTEM = ("Tu es un recruteur expérimenté en France et un coach d'entretien exigeant mais bienveillant. Tu prépares le "
          "candidat avec des questions réalistes pour l'offre, et tu t'appuies uniquement sur son CV réel.")


class AgentCoach(Agent):
    info = AgentInfo(
        key="coach", nom="Agent Coach entretien", icone="🎤",
        mission="Prépare votre entretien pour une offre : questions probables, éléments attendus, conseils tirés de votre "
                "CV, évaluation de vos réponses et fiche de préparation à télécharger.",
        entrees=["Offre (collée ou choisie)", "CV (facultatif)"],
        sorties=["Questions + réponses attendues", "Évaluation de vos réponses", "Fiche de préparation (Word + PDF)"])

    def questions(self, offer_text: str, offer: dict, cv_text: str, n: int = 10, use_ai: bool = True) -> list[dict]:
        return self.run_logged(self._questions, offer_text, offer, cv_text, n, use_ai,
                               summary=lambda r: f"{len(r)} questions préparées")

    def _questions(self, offer_text, offer, cv_text, n, use_ai) -> list[dict]:
        if use_ai and self.llm.ok:
            prompt = (f"Prépare {n} questions d'entretien probables pour cette offre : 2 de présentation / motivation, "
                      f"{max(3, n // 2)} techniques sur les missions et compétences de l'offre, 2 comportementales (STAR), "
                      "1 mise en situation. Pour chacune : ce que le recruteur veut entendre, et un conseil personnalisé "
                      "qui cite un élément RÉEL du CV à utiliser (ou signale l'absence d'élément).\n"
                      'Réponds en JSON : {"questions": [{"categorie": "…", "question": "…", "attendu": "…", "conseil": "…"}]}\n\n'
                      f"OFFRE ({json.dumps({k: offer.get(k) for k in ('poste', 'entreprise', 'competences_requises')}, ensure_ascii=False)}) :\n"
                      f"{offer_text[:7000]}\n\nCV :\n{cv_text[:7000]}")
            try:
                ai = self.llm.complete(SYSTEM, prompt, json_mode=True, max_tokens=5000, temperature=0.5)
                qs = [q for q in (ai or {}).get("questions") or [] if q.get("question")]
                if qs:
                    return qs[:n]
            except Exception:  # noqa: BLE001 — repli sur la banque de questions
                pass
        asked = set(offer.get("competences_requises") or find_skills(offer_text))
        mine = set(find_skills(cv_text))
        tech = sorted(BANK, key=lambda q: -len(q[3] & asked))
        tech = [q for q in tech if q[3] & asked][: max(3, n - 6)] or tech[:3]
        out = [{"categorie": c, "question": q, "attendu": a, "conseil": ""} for c, q, a in TRANSVERSES[:2]]
        out += [{"categorie": c, "question": q, "attendu": a,
                 "conseil": ("Appuyez-vous sur votre expérience : " + ", ".join(sorted(s & mine)) + ".") if (s & mine)
                 else "Compétence peu visible dans votre CV : préparez un exemple de formation ou de projet."}
                for c, q, a, s in tech]
        for s in [x for x in asked if x not in SOFT and not any(x in q[3] for q in tech)][:2]:
            out.append({"categorie": "Technique", "question": f"Quelle est votre expérience en {s} ? Donnez un exemple concret.",
                        "attendu": "Contexte, ce que vous avez fait personnellement, outils, résultat.",
                        "conseil": "Présent dans votre CV : citez-le." if s in mine else "Absent du CV : soyez honnête et "
                        "montrez comment vous montez en compétence."})
        out += [{"categorie": c, "question": q, "attendu": a, "conseil": ""} for c, q, a in TRANSVERSES[2:]]
        return out[:n]

    def evaluate(self, question: dict, answer: str, offer_text: str, cv_text: str, use_ai: bool = True) -> dict:
        if not answer.strip():
            return {"note": 0, "points_forts": [], "a_ameliorer": ["Rédigez une réponse."], "reponse_amelioree": ""}
        if use_ai and self.llm.ok:
            prompt = ("Évalue la réponse du candidat à cette question d'entretien. Note sur 10, points forts, points à "
                      "améliorer, et une version améliorée (à l'oral, 150 mots max, sans inventer de faits absents du CV).\n"
                      'Réponds en JSON : {"note": 0-10, "points_forts": ["…"], "a_ameliorer": ["…"], "reponse_amelioree": "…"}\n\n'
                      f"QUESTION : {question['question']}\nATTENDU : {question.get('attendu', '')}\n"
                      f"RÉPONSE DU CANDIDAT : {answer}\n\nOFFRE :\n{offer_text[:3000]}\n\nCV :\n{cv_text[:4000]}")
            try:
                return self.llm.complete(SYSTEM, prompt, json_mode=True, max_tokens=1500)
            except Exception:  # noqa: BLE001
                pass
        words = len(answer.split())
        star = sum(1 for k in ("situation", "contexte", "tâche", "mission", "action", "j'ai", "résultat", "resultat")
                   if k in answer.lower())
        nums = len(re.findall(r"\d", answer))
        att = set(w for w in re.findall(r"[a-zà-ÿ]{5,}", question.get("attendu", "").lower()))
        cover = len(att & set(re.findall(r"[a-zà-ÿ]{5,}", answer.lower())))
        note = min(10, round(2 + min(words, 180) / 45 + min(star, 4) * 0.6 + (1 if nums else 0) + min(cover, 5) * 0.4))
        tips = []
        if words < 60:
            tips.append("Développez : visez 1 à 2 minutes à l'oral (100 à 200 mots).")
        if star < 2:
            tips.append("Structurez avec la méthode STAR (situation, tâche, action, résultat).")
        if not nums:
            tips.append("Ajoutez un élément chiffré (volume, délai, résultat).")
        if cover < 2:
            tips.append("Reprenez les éléments attendus : " + question.get("attendu", "")[:160])
        return {"note": note, "points_forts": ["Réponse structurée"] if star >= 2 else [], "a_ameliorer": tips,
                "reponse_amelioree": ""}

    def export(self, offer: dict, qs: list[dict], answers: dict, evals: dict) -> tuple[bytes, bytes, tuple[str, str]]:
        md = [f"# Préparation d'entretien — {offer.get('poste') or 'Poste'}",
              f"{offer.get('entreprise') or ''} {('· ' + offer['lieu']) if offer.get('lieu') else ''}", "---"]
        for i, q in enumerate(qs, 1):
            md += [f"## {i}. {q['question']}", f"*{q.get('categorie', '')}*",
                   f"- **Ce qu'attend le recruteur** : {q.get('attendu', '')}"]
            if q.get("conseil"):
                md.append(f"- **Conseil** : {q['conseil']}")
            a = answers.get(i - 1, "").strip()
            if a:
                md.append(f"- **Ma réponse** : {a}")
            e = evals.get(i - 1)
            if e:
                md.append(f"- **Note** : {e.get('note', '?')}/10 — " + "; ".join(e.get("a_ameliorer") or []))
                if e.get("reponse_amelioree"):
                    md.append(f"- **Version améliorée** : {e['reponse_amelioree']}")
        md += ["## Questions à poser au recruteur"] + [f"- {q}" for q in QUESTIONS_A_POSER]
        text = "\n".join(md)
        docx = markdown_to_docx(text)
        pdf, _ = to_pdf(None, text)
        ensure_dirs()
        base = f"Entretien_{safe_filename(offer.get('entreprise') or offer.get('poste') or 'offre')}_{now_tag()}"
        paths = (save_output(OUTPUTS, base + ".docx", docx), save_output(OUTPUTS, base + ".pdf", pdf))
        try:
            self.store.add_document("Entretien", str(offer.get("poste") or ""), str(offer.get("entreprise") or ""),
                                    offer.get("uid"), paths[0], paths[1], {})
        except Exception:  # noqa: BLE001
            pass
        return docx, pdf, paths

    def readiness(self) -> tuple[str, str]:
        return "ok", "Prêt · " + ("questions générées par l'IA" if self.llm.ok else "banque de questions + offre")

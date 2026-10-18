"""Page de l'Agent Profil."""
from __future__ import annotations

import streamlit as st

from core import ui_html as ui
from core.config import EMPTY_PROFILE

from . import theme

CONTRATS = ["CDI", "CDD", "Intérim"]


def _lst(s: str) -> list[str]:
    import re
    return [x.strip() for x in re.split(r"[\n;,]", s or "") if x.strip()]


def _template_block(agent, kind: str, label: str, types: list[str]):
    doc = agent.load_template(kind)
    st.markdown(f"**{label}**")
    if doc:
        st.html(ui.notice("ok", f"Modèle enregistré : {doc.name} ({doc.kind.upper()}, {len(doc.text.split())} mots)"))
    up = st.file_uploader(f"{'Remplacer' if doc else 'Importer'} — {', '.join(types)}", type=[t.strip('.') for t in types],
                          key=f"up_{kind}")
    if up is not None:
        marker = (up.name, up.size)
        if st.session_state.get(f"saved_{kind}") != marker:
            try:
                agent.save_template(kind, up.getvalue(), up.name)
                st.session_state[f"saved_{kind}"] = marker
                st.session_state.pop("profil_draft", None)
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
    if doc:
        with st.expander("Voir le texte lu"):
            st.text(doc.text[:6000])
        if st.button("Supprimer ce modèle", key=f"del_{kind}"):
            agent.delete_template(kind)
            st.session_state.pop(f"saved_{kind}", None)
            st.rerun()
    if kind == "cv" and doc and doc.kind == "pdf":
        st.caption("Conseil : importez plutôt la version Word (.docx) de votre CV — l'Agent Rédacteur pourra alors garder "
                   "exactement votre mise en page.")
    if kind == "lettre":
        st.caption("Astuce : vous pouvez mettre dans votre lettre Word des balises {{POSTE}}, {{ENTREPRISE}}, {{DATE}}, "
                   "{{COMPETENCES}}, {{LIEU}} : elles sont remplies automatiquement, même sans IA.")
    return doc


def render(app):
    agent = app.agents["profil"]
    theme.page_header(agent.info)

    st.subheader("1. Vos documents modèles")
    c1, c2 = st.columns(2)
    with c1:
        cv = _template_block(agent, "cv", "CV modèle", [".docx", ".pdf", ".txt"])
    with c2:
        _template_block(agent, "lettre", "Lettre de motivation modèle", [".docx", ".pdf", ".txt"])

    st.subheader("2. Votre profil")
    saved = agent.current_profile()
    if cv:
        e1, e2 = st.columns([1, 2], vertical_alignment="center")
        use_ai = e2.toggle("Utiliser l'IA pour l'extraction", value=app.llm.ok, disabled=not app.llm.ok,
                           help="Sans IA : extraction par mots-clés (à compléter à la main).")
        if e1.button("🧭 Extraire mon profil du CV", key="go_extract", width="stretch"):
            with st.spinner("Lecture du CV…"):
                try:
                    draft = agent.extract(cv, use_ai=use_ai)
                    draft["mode_filtre"] = saved.get("mode_filtre") or draft.get("mode_filtre")
                    st.session_state["profil_draft"] = draft
                    st.toast("Profil extrait : vérifiez puis enregistrez.", icon="✅")
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Extraction impossible : {exc}")
    p = {**EMPTY_PROFILE, **saved, **st.session_state.get("profil_draft", {})}
    for k in ("salaire_min_annuel", "experience_max_ans", "fraicheur_jours", "duree_min_mois", "contrats"):
        p.setdefault(k, app.cfg.profil.get("candidat", {}).get(k))
    if "profil_draft" in st.session_state:
        st.html(ui.notice("info", "Profil extrait du CV : vérifiez et complétez les champs, puis cliquez sur « Enregistrer le profil »."))

    with st.form("profil_form"):
        a, b, c = st.columns(3)
        nom = a.text_input("Nom", p.get("nom", ""))
        titre = b.text_input("Titre professionnel", p.get("titre", ""))
        loc = c.text_input("Localisation souhaitée", p.get("localisation", "France"))
        a, b, c = st.columns(3)
        email = a.text_input("E-mail", p.get("email", ""))
        tel = b.text_input("Téléphone", p.get("telephone", ""))
        exp = c.number_input("Années d'expérience", 0, 45, int(p.get("experience_ans") or 0))
        resume = st.text_area("Résumé du profil (2-3 phrases)", p.get("resume", ""), height=80)
        a, b = st.columns(2)
        postes = a.text_area("Postes ciblés (un par ligne)", "\n".join(p.get("postes_cibles") or []), height=130)
        kws = b.text_area("Mots-clés de recherche d'offres (un par ligne)", "\n".join(p.get("mots_cles_recherche") or []),
                          height=130, help="Envoyés aux plateformes par l'Agent Chasseur. Vide = mots-clés par défaut "
                                           "(conformité / LCB-FT / KYC / analyste crédit).")
        a, b = st.columns(2)
        comp = a.text_area("Compétences métier (virgules ou lignes)", ", ".join(p.get("competences") or []), height=100)
        outils = b.text_area("Outils et langages", ", ".join(p.get("outils") or []), height=100)
        a, b, c = st.columns(3)
        certs = a.text_area("Certifications", ", ".join(p.get("certifications") or []), height=70)
        langues = b.text_area("Langues", ", ".join(p.get("langues") or []), height=70)
        formation = c.text_area("Formation", "\n".join(str(x) if not isinstance(x, dict) else " — ".join(map(str, x.values()))
                                                       for x in p.get("formation") or []), height=70)

        st.markdown("**Critères de recherche d'offres** (utilisés par l'Agent Chasseur)")
        a, b, c = st.columns(3)
        mode = a.radio("Filtrage des métiers", ["conformite", "profil"], index=0 if p.get("mode_filtre") != "profil" else 1,
                       format_func=lambda x: "Expert conformité / LCB-FT / KYC / crédit" if x == "conformite"
                       else "Selon mes postes ciblés et compétences")
        exp_max = b.number_input("Expérience maximale demandée (ans)", 0, 20, int(p.get("experience_max_ans") or 3))
        sal = c.number_input("Salaire annuel brut minimum (€)", 0, 200000, int(p.get("salaire_min_annuel") or 33000), step=1000)
        a, b, c = st.columns(3)
        fr = a.slider("Offres publiées depuis (jours)", 1, 60, int(p.get("fraicheur_jours") or 30))
        contrats = b.multiselect("Contrats", CONTRATS, default=[x for x in (p.get("contrats") or CONTRATS) if x in CONTRATS])
        dmin = c.number_input("Durée minimale CDD / intérim (mois)", 0, 24, int(p.get("duree_min_mois") or 3))
        if st.form_submit_button("💾 Enregistrer le profil", type="primary"):
            prof = {**saved, "nom": nom, "titre": titre, "localisation": loc, "email": email, "telephone": tel,
                    "experience_ans": int(exp), "resume": resume, "postes_cibles": [x.strip() for x in postes.splitlines() if x.strip()],
                    "mots_cles_recherche": [x.strip() for x in kws.splitlines() if x.strip()],
                    "competences": _lst(comp), "outils": _lst(outils), "certifications": _lst(certs), "langues": _lst(langues),
                    "formation": [x.strip() for x in formation.splitlines() if x.strip()],
                    "experiences": p.get("experiences") or [], "mode_filtre": mode, "experience_max_ans": int(exp_max),
                    "salaire_min_annuel": int(sal), "fraicheur_jours": int(fr), "contrats": contrats or CONTRATS,
                    "duree_min_mois": int(dmin)}
            agent.save_profile(prof)
            st.session_state.pop("profil_draft", None)
            st.success("Profil enregistré. Il sera utilisé à la prochaine mise à jour des offres.")

    if cv:
        st.subheader("3. Diagnostic de votre CV")
        for lvl, label, tip in agent.diagnose(cv.text):
            icon = {"ok": "✅", "warn": "🟠", "bad": "🔴"}[lvl]
            st.markdown(f"{icon} **{label}** — {tip}")

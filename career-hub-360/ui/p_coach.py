"""Page de l'Agent Coach entretien."""
from __future__ import annotations

import streamlit as st

from core import ui_html as ui
from services.keywords import guess_offer_fields

from . import theme


def render(app):
    agent = app.agents["coach"]
    theme.page_header(agent.info, f"IA : {app.llm.label}")
    cur = st.session_state.get("offre_courante") or {}
    cv = app.agents["profil"].load_template("cv")
    cv_text = cv.text if cv else ""

    rows = [r for r in app.store.list() if r["status"] != "Ignorée"][:150]
    opts = ["Offre en cours / collée"] + [r["uid"] for r in rows]
    labels = {r["uid"]: f"{r['title']} — {r['company']}" for r in rows}
    choice = st.selectbox("Offre", opts, format_func=lambda u: labels.get(u, u))
    if choice != opts[0]:
        r = app.store.get(choice)
        text = f"{r['title']}\n{r['company']}\n\n{r['description']}"
        offer = {"uid": r["uid"], "poste": r["title"], "entreprise": r["company"], "lieu": r.get("location")}
    else:
        text = st.text_area("Texte de l'offre", cur.get("text", ""), height=180,
                            placeholder="Collez l'offre, ou choisissez une offre collectée ci-dessus.")
        offer = {"uid": cur.get("uid"), "poste": cur.get("poste"), "entreprise": cur.get("entreprise"), "lieu": cur.get("lieu")}
    g = guess_offer_fields(text)
    offer = {**g, **{k: v for k, v in offer.items() if v}}

    c1, c2, c3 = st.columns([1, 1, 1.2], vertical_alignment="bottom")
    n = c1.slider("Nombre de questions", 5, 15, 10)
    use_ai = c2.toggle("Questions générées par l'IA", value=app.llm.ok, disabled=not app.llm.ok)
    if c3.button("🎤 Préparer l'entretien", key="go_coach", width="stretch", disabled=len(text.strip()) < 40):
        with st.spinner("Préparation des questions…"):
            st.session_state["coach_qs"] = agent.questions(text, offer, cv_text, n, use_ai)
            st.session_state["coach_offer"] = offer
            st.session_state["coach_text"] = text
            st.session_state["coach_evals"] = {}
    qs = st.session_state.get("coach_qs")
    if not qs:
        if not cv_text:
            st.caption("Astuce : importez votre CV dans l'Agent Profil pour des conseils personnalisés.")
        return
    offer = st.session_state.get("coach_offer", offer)
    evals = st.session_state.setdefault("coach_evals", {})
    answers = {}
    st.subheader(f"Questions pour : {offer.get('poste') or 'le poste'} {('— ' + offer['entreprise']) if offer.get('entreprise') else ''}")
    for i, q in enumerate(qs):
        with st.expander(f"{i + 1}. [{q.get('categorie', '')}] {q['question']}", expanded=i == 0):
            st.markdown(f"**Ce qu'attend le recruteur** : {q.get('attendu', '')}")
            if q.get("conseil"):
                st.markdown(f"**Conseil** : {q['conseil']}")
            answers[i] = st.text_area("Ma réponse", key=f"ans_{i}", height=120)
            if st.button("Évaluer ma réponse", key=f"ev_{i}"):
                with st.spinner("Évaluation…"):
                    evals[i] = agent.evaluate(q, answers[i], st.session_state.get("coach_text", ""), cv_text, use_ai)
            e = evals.get(i)
            if e:
                st.markdown(f"**Note : {e.get('note', '?')}/10**")
                for p in e.get("points_forts") or []:
                    st.markdown(f"✅ {p}")
                for p in e.get("a_ameliorer") or []:
                    st.markdown(f"🟠 {p}")
                if e.get("reponse_amelioree"):
                    st.html(ui.notice("info", "Version améliorée : " + str(e["reponse_amelioree"])))
    if evals:
        avg = sum(float(e.get("note") or 0) for e in evals.values()) / len(evals)
        st.metric("Score moyen de préparation", f"{avg:.1f}/10", help=f"{len(evals)} réponse(s) évaluée(s)")
    if st.button("📄 Générer la fiche de préparation (Word + PDF)", key="go_fiche"):
        st.session_state["coach_export"] = agent.export(offer, qs, answers, evals)
    if st.session_state.get("coach_export"):
        docx, pdf, _ = st.session_state["coach_export"]
        theme.downloads(docx, pdf, "Preparation_entretien", "coach")

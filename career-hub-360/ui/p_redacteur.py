"""Page de l'Agent Rédacteur : CV et lettre adaptés à une offre collée, export Word + PDF."""
from __future__ import annotations

import re

import streamlit as st

from core import ui_html as ui
from services.documents import read_document, safe_filename
from services.keywords import match_report

from . import theme


def _offer_input(app) -> str:
    cur = st.session_state.get("offre_courante") or {}
    src = st.radio("Source de l'offre", ["Coller le texte de l'offre", "Choisir une offre collectée"], horizontal=True,
                   index=0, key="red_src")
    if src == "Choisir une offre collectée":
        rows = [r for r in app.store.list() if r["status"] != "Ignorée"][:150]
        if not rows:
            st.info("Aucune offre collectée : lancez l'Agent Chasseur d'offres, ou collez une offre.")
            return ""
        labels = {r["uid"]: f"{r['score']} · {r['title']} — {r['company']}" for r in rows}
        default = list(labels).index(cur["uid"]) if cur.get("uid") in labels else 0
        uid = st.selectbox("Offre", list(labels), index=default, format_func=labels.get)
        r = app.store.get(uid)
        if cur.get("uid") != uid:
            from .p_chasseur import use_offer
            use_offer(r)
            cur = st.session_state["offre_courante"]
        st.caption("Le texte ci-dessous peut être un extrait : complétez-le avec l'annonce complète si besoin.")
    text = st.text_area("Texte de l'offre (copier-coller de l'annonce complète)", value=cur.get("text", ""), height=230,
                        key=f"offer_text_{cur.get('uid', 'manual')}",
                        placeholder="Collez ici l'intitulé, la description du poste, les missions et le profil recherché…")
    return text


def render(app):
    agent = app.agents["redacteur"]
    profil = app.agents["profil"]
    theme.page_header(agent.info, f"IA : {app.llm.label}")

    # ------------------------------------------------------------------ 1. offre
    st.subheader("1. L'offre")
    offer_text = _offer_input(app)
    use_ai = st.toggle("Utiliser l'IA (réécriture complète)", value=app.llm.ok, disabled=not app.llm.ok,
                       help="Sans IA : titre aligné sur l'offre, compétences réordonnées, balises de la lettre remplies.")
    if st.button("🔍 Analyser l'offre", key="go_analyse", disabled=len(offer_text.strip()) < 80):
        with st.spinner("Analyse de l'offre…"):
            an = agent.analyze_offer(offer_text, use_ai=use_ai)
            an["uid"] = (st.session_state.get("offre_courante") or {}).get("uid")
            st.session_state["offer_analysis"] = an
            st.session_state["offer_analysis_text"] = offer_text
            cur = st.session_state.get("offre_courante") or {}
            st.session_state["offre_courante"] = {**cur, "uid": an["uid"], "poste": an.get("poste"),
                                                  "entreprise": an.get("entreprise"), "lieu": an.get("lieu"), "text": offer_text}
    an = st.session_state.get("offer_analysis")
    if an and st.session_state.get("offer_analysis_text") != offer_text:
        st.caption("⚠️ Le texte de l'offre a changé : relancez l'analyse.")
    if not an:
        st.caption("Collez l'offre puis cliquez sur « Analyser l'offre ».")
        return
    c1, c2, c3 = st.columns(3)
    an["poste"] = c1.text_input("Intitulé du poste", an.get("poste", ""))
    an["entreprise"] = c2.text_input("Entreprise", an.get("entreprise", ""))
    an["lieu"] = c3.text_input("Lieu", an.get("lieu", ""))
    if an.get("resume"):
        st.caption(an["resume"])
    st.html('<div class="rc-chips">' + "".join(f'<span class="rc-chip">{ui.esc(s)}</span>'
                                               for s in an.get("competences_requises") or []) + "</div>")

    # ------------------------------------------------------------------ 2. modèles
    st.subheader("2. Vos modèles")
    cv, lm = profil.load_template("cv"), profil.load_template("lettre")
    c1, c2 = st.columns(2)
    with c1:
        if cv:
            st.html(ui.notice("ok", f"CV modèle : {cv.name} ({cv.kind.upper()})"))
        up = st.file_uploader("Utiliser un autre CV pour cette offre", type=["docx", "pdf", "txt"], key="red_cv")
        if up:
            cv = read_document(up.getvalue(), up.name)
    with c2:
        if lm:
            st.html(ui.notice("ok", f"Lettre modèle : {lm.name} ({lm.kind.upper()})"))
        else:
            st.html(ui.notice("info", "Pas de lettre modèle : une lettre sera rédigée à partir de votre CV."))
        up2 = st.file_uploader("Utiliser une autre lettre pour cette offre", type=["docx", "pdf", "txt"], key="red_lm")
        if up2:
            lm = read_document(up2.getvalue(), up2.name)
    if not cv:
        st.warning("Importez un CV modèle (ici ou dans l'Agent Profil) pour continuer.")
        st.page_link(app.pages["profil"], label="Ouvrir l'Agent Profil", icon="🧭")
        return

    rep = match_report(cv.text, offer_text)
    st.html(f'<div class="ch-score"><span>Correspondance actuelle CV ↔ offre</span><b>{rep["score"]}/100</b>'
            f'<span style="font-size:.85rem;color:var(--rc-muted)">{len(rep["found"])} compétences trouvées sur '
            f'{len(rep["asked"])} demandées</span></div>')
    confirmed = st.multiselect("Compétences demandées absentes de votre CV que vous possédez réellement (elles pourront être "
                               "ajoutées)", rep["missing"], help="Rien n'est ajouté sans votre confirmation.")

    # ------------------------------------------------------------------ 3. options
    st.subheader("3. Adapter")
    title_idx = skills_idx = None
    change_title = True
    instructions = ""
    if use_ai:
        instructions = st.text_input("Consigne particulière (facultatif)",
                                     placeholder="ex. : mettre en avant mon expérience HiPay ; ton plus direct ; garder 1 page")
    else:
        opts = {p.idx: (p.text[:90] + ("…" if len(p.text) > 90 else "")) for p in cv.paragraphs if p.editable}
        keys = [None] + list(opts)
        fmt = lambda i: "— aucun —" if i is None else opts[i]  # noqa: E731
        g_t, g_s = agent.guess_title_idx(cv), agent.guess_skills_idx(cv)
        a, b = st.columns(2)
        title_idx = a.selectbox("Paragraphe du titre du CV (remplacé par l'intitulé de l'offre)", keys,
                                index=keys.index(g_t) if g_t in keys else 0, format_func=fmt)
        skills_idx = b.selectbox("Paragraphe des compétences (réordonné)", keys,
                                 index=keys.index(g_s) if g_s in keys else 0, format_func=fmt)
        change_title = a.checkbox("Remplacer le titre", value=True)
    repl = {}
    if lm and not use_ai and "{{" not in lm.text:
        st.caption("Votre lettre n'a pas de balises {{…}} : indiquez ce qu'il faut remplacer.")
        r1, r2 = st.columns(2)
        o1 = r1.text_input("Texte à remplacer n°1 (ex. ancien nom d'entreprise)")
        n1 = r2.text_input("Remplacer par n°1", an.get("entreprise", ""))
        o2 = r1.text_input("Texte à remplacer n°2 (ex. ancien intitulé de poste)")
        n2 = r2.text_input("Remplacer par n°2", an.get("poste", ""))
        repl = {o1: n1, o2: n2}

    b1, b2, b3 = st.columns(3)
    do_cv = b1.button("✍️ Adapter le CV", key="go_cv", width="stretch")
    do_lm = b2.button("✉️ Adapter la lettre", key="go_lm", width="stretch")
    do_both = b3.button("⚡ Les deux", key="go_both", width="stretch")
    prof = app.cfg.user
    if do_cv or do_both:
        with st.spinner("Adaptation du CV…"):
            try:
                st.session_state["cv_result"] = agent.adapt_cv(cv, offer_text, an, confirmed, use_ai, title_idx, skills_idx,
                                                               change_title, instructions)
            except Exception as exc:  # noqa: BLE001
                st.error(f"CV : {type(exc).__name__} : {exc}")
    if do_lm or do_both:
        with st.spinner("Rédaction de la lettre…"):
            try:
                st.session_state["lm_result"] = agent.adapt_letter(lm, cv.text, offer_text, an, prof, use_ai, repl, instructions)
            except Exception as exc:  # noqa: BLE001
                st.error(f"Lettre : {type(exc).__name__} : {exc}")

    # ------------------------------------------------------------------ 4. résultats
    nom = safe_filename(prof.get("nom") or "candidat")
    comp = safe_filename(an.get("entreprise") or "offre")
    for key, label in (("cv_result", "CV adapté"), ("lm_result", "Lettre adaptée")):
        res = st.session_state.get(key)
        if not res:
            continue
        st.subheader(label)
        if res.kind == "CV":
            st.html(f'<div class="ch-score"><span>Correspondance</span><b>{res.score_before} → {res.score_after}/100</b>'
                    + (f'<span style="font-size:.85rem;color:var(--rc-muted)">Encore absent : {ui.esc(", ".join(res.missing[:8]))}</span>'
                       if res.missing else "") + "</div>")
        theme.downloads(res.docx, res.pdf, f"{res.kind}_{nom}_{comp}", key)
        st.caption(f"PDF : {res.pdf_method}. Fichiers aussi conservés dans « Suivi & documents ».")
        for w in res.warnings:
            st.html(ui.notice("warn", str(w)))
        if res.changes:
            with st.expander(f"{len(res.changes)} modification(s) — avant / après", expanded=res.kind == "CV"):
                for old, new, why in res.changes:
                    st.html(theme.diff_html(old, new, why))
        with st.expander("Aperçu du texte"):
            st.text(re.sub(r"\n{3,}", "\n\n", res.text)[:8000])
    if st.session_state.get("cv_result") or st.session_state.get("lm_result"):
        cur = st.session_state.get("offre_courante") or {}
        if cur.get("uid") and st.button("📌 Marquer l'offre « À postuler »"):
            r = app.store.get(cur["uid"])
            if r:
                app.store.set_user_fields(cur["uid"], "À postuler", r["notes"])
                st.toast("Statut mis à jour.")
        st.page_link(app.pages["coach"], label="Préparer l'entretien pour cette offre", icon="🎤")

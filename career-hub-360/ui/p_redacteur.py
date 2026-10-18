"""Page de l'Agent Rédacteur : CV gardé tel quel (seul le titre change) et lettre complétée, export Word + PDF."""
from __future__ import annotations

import re

import streamlit as st

from agents.redacteur import today_fr
from core import ui_html as ui
from services.documents import read_document

from . import theme


def _offer_input(app) -> str:
    cur = st.session_state.get("offre_courante") or {}
    src = st.radio("Source de l'offre", ["Coller le texte de l'offre", "Choisir une offre collectée"], horizontal=True, key="red_src")
    if src == "Choisir une offre collectée":
        rows = [r for r in app.store.list() if r["status"] != "Ignorée"][:150]
        if not rows:
            st.info("Aucune offre collectée : lancez l'Agent Chasseur d'offres, ou collez une offre.")
            return ""
        labels = {r["uid"]: f"{r['score']} · {r['title']} — {r['company']}" for r in rows}
        default = list(labels).index(cur["uid"]) if cur.get("uid") in labels else 0
        uid = st.selectbox("Offre", list(labels), index=default, format_func=labels.get)
        if cur.get("uid") != uid:
            from .p_chasseur import use_offer
            use_offer(app.store.get(uid))
            cur = st.session_state["offre_courante"]
        st.caption("Le texte peut être un extrait : complétez-le avec l'annonce complète si besoin.")
    return st.text_area("Texte de l'offre (copier-coller de l'annonce complète)", value=cur.get("text", ""), height=200,
                        key=f"offer_text_{cur.get('uid', 'manual')}",
                        placeholder="Collez ici l'intitulé, l'entreprise, la description du poste et le profil recherché…")


def _result_block(res, key: str):
    theme.downloads(res.docx, res.pdf, res.filename, key)
    st.caption(f"Fichiers : {res.filename}.docx / .pdf · PDF : {res.pdf_method} · aussi conservés dans « Suivi & documents ».")
    for w in res.warnings:
        st.html(ui.notice("warn", str(w)))


def render(app):
    agent = app.agents["redacteur"]
    profil = app.agents["profil"]
    theme.page_header(agent.info, f"IA : {app.llm.label}")
    prof = app.cfg.user

    # ------------------------------------------------------------------ 1. offre
    st.subheader("1. L'offre")
    offer_text = _offer_input(app)
    use_ai = st.toggle("Utiliser l'IA", value=app.llm.ok, disabled=not app.llm.ok,
                       help="Sans IA : titre = intitulé de l'offre, motivation rédigée à partir de modèles de phrases.")
    if st.button("🔍 Analyser l'offre", key="go_analyse", disabled=len(offer_text.strip()) < 60):
        with st.spinner("Analyse de l'offre…"):
            an = agent.analyze_offer(offer_text, use_ai=use_ai)
            an["uid"] = (st.session_state.get("offre_courante") or {}).get("uid")
            for k in ("new_title", "cv_result", "lm_result", "motivation", "recipient"):
                st.session_state.pop(k, None)
            st.session_state["offer_analysis"] = an
            st.session_state["offer_analysis_text"] = offer_text
            cur = st.session_state.get("offre_courante") or {}
            st.session_state["offre_courante"] = {**cur, "uid": an["uid"], "poste": an.get("poste"),
                                                  "entreprise": an.get("entreprise"), "lieu": an.get("lieu"), "text": offer_text}
    an = st.session_state.get("offer_analysis")
    if not an:
        st.caption("Collez l'offre puis cliquez sur « Analyser l'offre ».")
        return
    if st.session_state.get("offer_analysis_text") != offer_text:
        st.caption("⚠️ Le texte de l'offre a changé : relancez l'analyse.")
    c1, c2, c3 = st.columns(3)
    an["poste"] = c1.text_input("Intitulé du poste", an.get("poste", ""))
    an["entreprise"] = c2.text_input("Entreprise", an.get("entreprise", ""))
    an["lieu"] = c3.text_input("Lieu", an.get("lieu", ""))

    cv, lm = profil.load_template("cv"), profil.load_template("lettre")
    tab_cv, tab_lm = st.tabs(["📄 CV — titre adapté à l'offre", "✉️ Lettre de motivation"])

    # ------------------------------------------------------------------ 2. CV : seul le titre change
    with tab_cv:
        st.html(ui.notice("info", "Votre CV reste strictement identique (mise en page, cadre, polices, texte). Seule la ligne "
                                  "de titre est remplacée par un titre adapté à l'offre, et le fichier est nommé d'après l'offre."))
        up = st.file_uploader("Utiliser un autre CV Word pour cette offre", type=["docx"], key="red_cv")
        if up:
            cv = read_document(up.getvalue(), up.name)
        if not cv:
            st.warning("Importez votre CV modèle Word (ici ou dans l'Agent Profil).")
        elif not cv.is_docx:
            st.warning("Votre CV modèle est un PDF : pour le garder identique, importez sa version Word (.docx).")
        else:
            cands = agent.title_candidates(cv)
            other = "✏️ Autre (saisir le texte exact)…"
            sel = st.selectbox("Titre actuel de votre CV (la seule ligne modifiée)", cands + [other], key="old_title_sel")
            old_title = st.text_input("Texte exact du titre actuel", key="old_title_free") if sel == other else sel
            if old_title and st.session_state.get("new_title_for") != (old_title, an.get("poste")):
                with st.spinner("Proposition du titre…"):
                    st.session_state["new_title"] = agent.propose_title(old_title, an, cv.text, use_ai, offer_text)
                    st.session_state["new_title_for"] = (old_title, an.get("poste"))
            new_title = st.text_input("Nouveau titre adapté à l'offre (modifiable)", key="new_title")
            if old_title:
                st.html(theme.diff_html(old_title, new_title, "seul changement apporté au CV"))
            if st.button("✍️ Générer le CV (Word + PDF)", key="go_cv", disabled=not (old_title and new_title)):
                with st.spinner("Génération du CV…"):
                    try:
                        st.session_state["cv_result"] = agent.adapt_cv(cv, old_title, new_title, offer_text, an)
                    except Exception as exc:  # noqa: BLE001
                        st.error(str(exc))
            res = st.session_state.get("cv_result")
            if res:
                st.success(f"CV prêt : {res.filename}")
                _result_block(res, "cv_result")

    # ------------------------------------------------------------------ 3. lettre
    with tab_lm:
        up2 = st.file_uploader("Utiliser une autre lettre Word pour cette offre", type=["docx", "pdf", "txt"], key="red_lm")
        if up2:
            lm = read_document(up2.getvalue(), up2.name)
        if lm:
            st.html(ui.notice("ok", f"Lettre modèle : {lm.name} — sa forme est conservée ; seuls le destinataire, la date, "
                                    "l'objet et les paragraphes de motivation sont ajoutés ou remplacés."))
        else:
            st.html(ui.notice("info", "Pas de lettre modèle : une lettre standard sera créée (importez la vôtre dans l'Agent Profil)."))
        lay = agent.letter_layout(lm)

        st.markdown("**Destinataire** (aligné à droite)")
        if "recipient" not in st.session_state:
            st.session_state["recipient"] = "\n".join(agent.default_recipient(an))
        r1, r2 = st.columns([3, 1], vertical_alignment="bottom")
        if app.llm.ok and r2.button("🔎 Chercher l'adresse", help="Recherche web par l'IA — vérifiez l'adresse proposée."):
            with st.spinner("Recherche de l'adresse…"):
                try:
                    lines, srcs = agent.find_address(an)
                    if lines:
                        st.session_state["recipient"] = "\n".join(lines)
                        st.session_state["addr_sources"] = srcs
                    else:
                        st.warning("Adresse introuvable : complétez-la à la main.")
                except Exception as exc:  # noqa: BLE001
                    st.error(str(exc))
        recipient = r1.text_area("Nom de l'entreprise, service, adresse, code postal et ville (une ligne par élément)",
                                 key="recipient", height=110)
        if st.session_state.get("addr_sources"):
            st.caption("Sources de l'adresse : " + " · ".join(f"[{s['title']}]({s['url']})" for s in st.session_state["addr_sources"][:3]))
        replace_idx = []
        if lm and lm.is_docx:
            first = min([i for i in (lay["date"], lay["objet"], lay["salut"]) if i is not None] or [10 ** 6])
            before = {p.idx: p.text[:80] for p in lm.paragraphs if p.text.strip() and p.idx < first}
            if before:
                replace_idx = st.multiselect("Votre modèle contient déjà un bloc destinataire ? Choisissez ses lignes à "
                                             "remplacer (sinon le bloc est ajouté avant la date / l'objet)",
                                             list(before), format_func=before.get)
        ville = (prof.get("localisation") or "Paris").split(",")[0].strip()
        if ville.lower() == "france":
            ville = "Paris"
        date_line = st.text_input("Lieu et date (alignés à droite)", f"{ville}, le {today_fr()}")

        st.markdown("**Motivation adaptée à l'offre**")
        instructions = st.text_input("Consigne particulière (facultatif)",
                                     placeholder="ex. : insister sur mon expérience HiPay ; mentionner la mobilité géographique")
        if st.button("✨ Proposer la motivation", key="go_motiv"):
            with st.spinner("Rédaction de la motivation…"):
                st.session_state["motivation"] = agent.propose_motivation(lm, cv.text if cv else "", offer_text, an, prof,
                                                                         use_ai, instructions)
        mot = st.session_state.get("motivation")
        if mot:
            for w in mot.get("warnings") or []:
                st.html(ui.notice("warn", w))
            objet = st.text_input("Objet", mot["objet"], key="lm_objet")
            n_model = len(lay["body"])
            if n_model:
                st.caption(f"{n_model} paragraphe(s) de motivation dans votre modèle : ils sont remplacés par ceux-ci "
                           "(le reste de la lettre ne change pas). Vous pouvez les modifier.")
            paras = [st.text_area(f"Paragraphe {i + 1}", p, key=f"lm_p{i}_{len(mot['paragraphes'])}", height=130)
                     for i, p in enumerate(mot["paragraphes"])]
            if st.button("📄 Générer la lettre (Word + PDF)", key="go_lm"):
                with st.spinner("Génération de la lettre…"):
                    try:
                        st.session_state["lm_result"] = agent.build_letter(
                            lm, recipient.splitlines(), date_line, objet, paras, prof, an, replace_idx)
                    except Exception as exc:  # noqa: BLE001
                        st.error(f"{type(exc).__name__} : {exc}")
        res = st.session_state.get("lm_result")
        if res:
            st.success(f"Lettre prête : {res.filename}")
            _result_block(res, "lm_result")
            with st.expander("Aperçu du texte de la lettre"):
                st.text(re.sub(r"\n{3,}", "\n\n", res.text))

    if st.session_state.get("cv_result") or st.session_state.get("lm_result"):
        cur = st.session_state.get("offre_courante") or {}
        if cur.get("uid") and st.button("📌 Marquer l'offre « À postuler »"):
            r = app.store.get(cur["uid"])
            if r:
                app.store.set_user_fields(cur["uid"], "À postuler", r["notes"])
                st.toast("Statut mis à jour.")
        st.page_link(app.pages["coach"], label="Préparer l'entretien pour cette offre", icon="🎤")

"""Tableau de bord : état des 5 agents, bouton de mise à jour global, chiffres clés."""
from __future__ import annotations

import streamlit as st

from core import ui_html as ui

from . import theme


def run_global_update(app, with_veille: bool):
    ch, ve = app.agents["chasseur"], app.agents["veille"]
    with st.status("Mise à jour en cours… ne fermez pas la page", expanded=True) as box:
        st.write("🔎 Agent Chasseur d'offres : lecture des plateformes…")
        try:
            rep = ch.update(progress=lambda m: st.write(m))
            st.session_state["flash"] = ("ok", f"Offres : {rep['kept']} retenues sur {rep['fetched']} lues · "
                                               f"{rep['duplicates_removed']} doublons fusionnés · {rep['expired']} retirées.")
        except Exception as exc:  # noqa: BLE001
            st.session_state["flash"] = ("warn", f"Chasseur d'offres : {type(exc).__name__} : {exc}")
        if with_veille:
            st.write("📡 Agent Veille marché : mise à jour du rapport…")
            prof = app.cfg.user
            cv = app.agents["profil"].load_template("cv")
            metier = (prof.get("postes_cibles") or ["Analyste conformité"])[0]
            try:
                ve.build_report(prof, cv.text if cv else "", metier, prof.get("localisation") or "France",
                                use_ai=app.llm.ok)
                st.write("Rapport de veille mis à jour.")
            except Exception as exc:  # noqa: BLE001
                st.session_state["flash2"] = ("warn", f"Veille marché : {type(exc).__name__} : {exc}")
        box.update(label="Mise à jour terminée", state="complete", expanded=False)


def render(app):
    prof = app.cfg.user
    nom = prof.get("nom") or app.cfg.candidat.get("nom", "")
    runs = app.store.last_runs(1)
    last = theme.fmt_dt(runs[0]["finished"]) if runs else "jamais"
    st.html(f'<div class="ch-hero"><h1>🚀 Career Hub 360{(" — " + ui.esc(nom)) if nom else ""}</h1>'
            f'<p>Une seule plateforme, 5 agents qui travaillent indépendamment : profil, recherche d\'offres, CV & lettre '
            f'adaptés, veille du marché, préparation d\'entretien.</p>'
            f'<p style="margin-top:4px">Dernière mise à jour des offres : {ui.esc(last)}</p></div>')

    c1, c2 = st.columns([1.2, 2], vertical_alignment="center")
    with c1:
        go = st.button("🔄  Mettre à jour (offres + veille)", key="maj", width="stretch")
    with c2:
        with_veille = st.checkbox("Mettre aussi à jour le rapport de veille marché", value=app.llm.ok,
                                  help="Avec une IA configurée, le rapport est refait à partir de sources web récentes.")
    if go:
        run_global_update(app, with_veille)
    for k in ("flash", "flash2"):
        if k in st.session_state:
            kind, msg = st.session_state.pop(k)
            st.html(ui.notice(kind, msg))

    rows = app.store.list()
    docs = app.store.documents()
    st.html(ui.kpis([
        ("Offres en base", len(rows), "#2A9D8F"),
        ("Score ≥ 70", sum(1 for r in rows if r["score"] >= 70), "#16a34a"),
        ("À postuler", sum(1 for r in rows if r["status"] == "À postuler"), "#f59e0b"),
        ("Postulées", sum(1 for r in rows if r["status"] == "Postulé"), "#7C3AED"),
        ("Entretiens", sum(1 for r in rows if r["status"] == "Entretien"), "#1D4ED8"),
        ("Documents générés", len(docs), "#ff7a45")]))

    st.subheader("Les 5 agents")
    cards = []
    for key in ("profil", "chasseur", "redacteur", "veille", "coach"):
        a = app.agents[key]
        state, msg = a.readiness()
        cards.append(theme.agent_card(a.info, state, msg, a.last_run()))
    st.html('<div class="ch-agents">' + "".join(cards) + "</div>")
    cols = st.columns(5)
    for col, key in zip(cols, ("profil", "chasseur", "redacteur", "veille", "coach")):
        col.page_link(app.pages[key], label=f"Ouvrir {app.agents[key].info.nom.replace('Agent ', '')}", icon="➡️")

    if not app.agents["profil"].template_path("cv"):
        st.html(ui.notice("info", "Pour commencer : ouvrez l'Agent Profil et importez votre CV modèle (Word de préférence) et "
                                  "votre lettre de motivation modèle. Les autres agents fonctionnent aussi sans, avec des "
                                  "critères saisis à la main."))
    if not app.llm.ok:
        st.html(ui.notice("warn", "Aucune IA configurée : les agents fonctionnent avec des règles (mots-clés, banque de "
                                  "questions, statistiques des offres). Ajoutez une clé gratuite Gemini dans Réglages & aide "
                                  "pour la réécriture complète du CV et de la lettre et la veille sourcée sur le web."))

    best = [r for r in rows if r["status"] in ("Nouvelle", "À postuler")][:6]
    if best:
        st.subheader("Meilleures offres du moment")
        for r in best:
            st.html(ui.offer_card(r, False, theme.age_text(r["posted_at"]), r["source"]))
        st.page_link(app.pages["chasseur"], label="Voir toutes les offres", icon="🔎")

    hist = app.store.agent_history(12)
    if hist:
        with st.expander("Journal des agents"):
            names = {k: a.info.nom for k, a in app.agents.items()}
            for h in hist:
                st.write(f"{'✅' if h['ok'] else '⚠️'} {theme.fmt_dt(h['finished'])} — **{names.get(h['agent'], h['agent'])}** : {h['summary']}")

"""Page de l'Agent Veille marché & conseil."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core import ui_html as ui
from services.documents import safe_filename

from . import theme


def render(app):
    agent = app.agents["veille"]
    theme.page_header(agent.info, f"IA : {app.llm.label}" + (" · recherche web native" if app.llm.native_web else ""))
    prof = app.cfg.user
    cv = app.agents["profil"].load_template("cv")
    cv_text = cv.text if cv else ""

    t_rep, t_mkt = st.tabs(["📝 Rapport de veille & conseils", "📊 Ce que demandent les offres collectées"])

    with t_rep:
        c1, c2 = st.columns([2, 1])
        postes = prof.get("postes_cibles") or ["Analyste LCB-FT junior"]
        metier = c1.selectbox("Métier visé", postes, accept_new_options=True)
        lieu = c2.text_input("Zone", prof.get("localisation") or "France")
        question = st.text_input("Question précise (facultatif)",
                                 placeholder="ex. : la certification CAMS vaut-elle le coup pour un junior ? Quelles banques recrutent à Lyon ?")
        use_ai = st.toggle("Recherche web par l'IA", value=app.llm.ok, disabled=not app.llm.ok,
                           help="Sans IA : statistiques des offres collectées + portails de référence à consulter.")
        if st.button("🔄 Mettre à jour la veille", key="go_veille"):
            with st.spinner("Recherche et rédaction du rapport (30 s à 2 min)…"):
                try:
                    agent.build_report(prof, cv_text, metier, lieu, use_ai, question)
                except Exception as exc:  # noqa: BLE001
                    st.error(f"{type(exc).__name__} : {exc}")
        rep = agent.last_report()
        if not rep:
            st.html(ui.empty_state("Aucun rapport", "Cliquez sur « Mettre à jour la veille »."))
        else:
            st.caption(f"Rapport du {rep['date']} · {rep['metier']} · {rep['lieu']} · {rep['mode']}")
            docx, pdf, _, _ = _export_cached(agent, rep)
            theme.downloads(docx, pdf, f"Veille_{safe_filename(rep['metier'])}", "veille")
            st.markdown(rep["markdown"])
            with st.expander("Données des offres collectées utilisées", expanded=False):
                st.markdown(rep.get("stats_md", ""))
            st.markdown(f"**Sources ({len(rep.get('sources', []))})**")
            st.html(theme.sources_html(rep.get("sources", [])))

    with t_mkt:
        m = agent.market_from_offers()
        if not m.get("n"):
            st.html(ui.empty_state("Aucune offre collectée", "Lancez l'Agent Chasseur d'offres pour obtenir des statistiques réelles."))
            return
        s = m["salaires"]
        st.html(ui.kpis([("Offres analysées", m["n"], "#2A9D8F"), ("Ouvertes aux juniors", f"{m['junior_pct']} %", "#16a34a"),
                         ("Salaire médian affiché", f"{s['median'] // 1000} k€" if s["median"] else "—", "#0E7490"),
                         ("Offres avec salaire", s["n"], "#64748b")]))
        g = agent.gap(prof, cv_text, m)
        if g:
            df = pd.DataFrame(g)
            df["Statut"] = df["Dans votre profil"].map({True: "Dans votre profil", False: "À renforcer"})
            fig = px.bar(df.sort_values("Demandée dans (%)"), x="Demandée dans (%)", y="Compétence", color="Statut",
                         orientation="h", color_discrete_map={"Dans votre profil": "#2A9D8F", "À renforcer": "#e76f51"},
                         title="Compétences demandées par les offres vs votre profil")
            fig.update_layout(height=max(380, 26 * len(df)), yaxis_title=None, legend_title=None, margin=dict(l=10, r=10))
            st.plotly_chart(fig, width="stretch")
            top = df.head(10)
            radar = go.Figure()
            radar.add_trace(go.Scatterpolar(r=top["Demandée dans (%)"], theta=top["Compétence"], fill="toself",
                                            name="Attente du marché", line_color="#94a3b8", opacity=0.5))
            radar.add_trace(go.Scatterpolar(r=[v if h else 0 for v, h in zip(top["Demandée dans (%)"], top["Dans votre profil"])],
                                            theta=top["Compétence"], fill="toself", name="Votre profil", line_color="#2A9D8F"))
            radar.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 100])), title="Écart profil / marché (top 10)")
            st.plotly_chart(radar, width="stretch")
            if not cv_text and not prof.get("competences"):
                st.caption("Importez votre CV dans l'Agent Profil pour comparer à votre profil.")
        a, b = st.columns(2)
        emp = pd.DataFrame(m["employeurs"], columns=["Employeur", "Offres"])
        a.plotly_chart(px.bar(emp.sort_values("Offres"), x="Offres", y="Employeur", orientation="h",
                              title="Employeurs qui publient le plus").update_layout(yaxis_title=None), width="stretch")
        typ = pd.DataFrame(m["types"], columns=["Type", "Offres"])
        b.plotly_chart(px.bar(typ.sort_values("Offres"), x="Offres", y="Type", orientation="h",
                              title="Types d'employeurs").update_layout(yaxis_title=None), width="stretch")
        st.markdown("**Exemples d'offres (sources)**")
        st.html(theme.sources_html(m["exemples"]))


def _export_cached(agent, rep):
    key = f"veille_export_{rep['date']}_{rep['metier']}_{len(rep['markdown'])}"
    if st.session_state.get("veille_export_key") != key:
        st.session_state["veille_export"] = agent.export(rep)
        st.session_state["veille_export_key"] = key
    return st.session_state["veille_export"]

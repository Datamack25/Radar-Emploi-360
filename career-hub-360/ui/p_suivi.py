"""Suivi des candidatures et documents générés."""
from __future__ import annotations

import os

import pandas as pd
import streamlit as st

from core import ui_html as ui
from core.store import STATUSES

from . import theme


def render(app):
    st.html('<div class="ch-page"><span class="ic">📋</span><div><h2>Suivi & documents</h2>'
            '<p>Vos candidatures, leurs statuts et tous les documents produits par les agents.</p></div></div>')
    store = app.store
    rows = store.list()
    t1, t2, t3 = st.tabs(["🗂️ Candidatures", "📁 Documents générés", "🧾 Journal des agents"])

    with t1:
        counts = {s: sum(1 for r in rows if r["status"] == s) for s in STATUSES}
        st.html(ui.kpis([(s, counts[s], c) for s, c in zip(STATUSES, ["#64748b", "#f59e0b", "#7C3AED", "#1D4ED8", "#dc2626", "#94a3b8"])]))
        show = st.multiselect("Statuts affichés", STATUSES, default=["À postuler", "Postulé", "Entretien", "Refusé"])
        sel = [r for r in rows if r["status"] in show]
        if not sel:
            st.html(ui.empty_state("Aucune candidature suivie", "Changez le statut d'une offre dans l'Agent Chasseur d'offres."))
        else:
            df = pd.DataFrame([{"uid": r["uid"], "Statut": r["status"], "Score": r["score"], "Intitulé": r["title"],
                                "Employeur": r["company"], "Lieu": r["location"], "Publiée": theme.age_text(r["posted_at"]),
                                "Lien": r["apply_url"] or r["url"], "Notes": r["notes"]} for r in sel])
            ed = st.data_editor(df, hide_index=True, width="stretch", disabled=["uid", "Score", "Intitulé", "Employeur", "Lieu",
                                                                                  "Publiée", "Lien"],
                                column_config={"uid": None, "Statut": st.column_config.SelectboxColumn(options=STATUSES),
                                               "Lien": st.column_config.LinkColumn(display_text="Ouvrir ↗"),
                                               "Notes": st.column_config.TextColumn(width="large")}, key="suivi_ed")
            if st.button("💾 Enregistrer les modifications", type="primary"):
                n = 0
                for _, r in ed.iterrows():
                    old = next(x for x in sel if x["uid"] == r["uid"])
                    if r["Statut"] != old["status"] or (r["Notes"] or "") != (old["notes"] or ""):
                        store.set_user_fields(r["uid"], r["Statut"], r["Notes"] or "")
                        n += 1
                st.success(f"{n} candidature(s) mise(s) à jour.")
                st.rerun()
            st.download_button("⬇️ Exporter le suivi (CSV)", ed.drop(columns=["uid"]).to_csv(index=False, sep=";").encode("utf-8-sig"),
                               "suivi_candidatures.csv", "text/csv")

    with t2:
        docs = [d for d in store.documents()]
        if not docs:
            st.html(ui.empty_state("Aucun document", "Les CV, lettres, rapports de veille et fiches d'entretien générés apparaîtront ici."))
        kinds = sorted({d["kind"] for d in docs})
        kf = st.multiselect("Type", kinds, default=kinds) if docs else []
        for d in docs:
            if d["kind"] not in kf:
                continue
            c1, c2, c3, c4 = st.columns([3, 1, 1, 0.6], vertical_alignment="center")
            c1.markdown(f"**{d['kind']}** — {d['title'] or ''} {('· ' + d['company']) if d['company'] else ''}  \n"
                        f"<span style='font-size:.78rem;color:gray'>{theme.fmt_dt(d['created'])}</span>", unsafe_allow_html=True)
            for col, path, mime, lab in ((c2, d["path_docx"], "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "Word"),
                                         (c3, d["path_pdf"], "application/pdf", "PDF")):
                if path and os.path.exists(path):
                    with open(path, "rb") as f:
                        col.download_button(lab, f.read(), os.path.basename(path), mime, key=f"dl_{d['id']}_{lab}", width="stretch")
                else:
                    col.caption("fichier absent")
            if c4.button("🗑️", key=f"rm_{d['id']}", help="Retirer de la liste"):
                for p in (d["path_docx"], d["path_pdf"]):
                    if p and os.path.exists(p):
                        os.remove(p)
                store.delete_document(d["id"])
                st.rerun()
        if docs:
            st.caption("Sur Streamlit Cloud, les fichiers sont effacés au redémarrage de l'application : téléchargez ceux à garder.")

    with t3:
        names = {k: a.info.nom for k, a in app.agents.items()}
        hist = store.agent_history(60)
        if not hist:
            st.caption("Aucune exécution pour l'instant.")
        for h in hist:
            st.write(f"{'✅' if h['ok'] else '⚠️'} {theme.fmt_dt(h['finished'])} — **{names.get(h['agent'], h['agent'])}** : {h['summary']}")

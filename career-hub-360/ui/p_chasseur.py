"""Page de l'Agent Chasseur d'offres (reprend Radar Emploi : sources autorisées, filtres, notes, suivi)."""
from __future__ import annotations

import os

import pandas as pd
import streamlit as st

from core import ui_html as ui
from core.annuaire import CATEGORIES
from core.filters import FAMILIES
from core.geo import REGION_NAMES
from core.http import Http, HttpError
from core.sources.ats import PUBLIC_PAGE, check_links, discover
from core.store import STATUSES

from . import theme

SOURCE_NAMES = {"france_travail": "France Travail", "google": "Google Emploi", "jooble": "Jooble", "adzuna": "Adzuna",
                "ats": "Site carrières de l'employeur"}
PAGE = 12
NO_REGION = "Région non précisée"
CONTRACTS = ["CDI", "CDD", "Intérim", "Non précisé"]


def use_offer(r: dict):
    """Transmet l'offre aux agents Rédacteur et Coach (données partagées, pas d'appel entre agents)."""
    st.session_state["offre_courante"] = {
        "uid": r["uid"], "poste": r["title"], "entreprise": r["company"], "lieu": r.get("location") or "",
        "contrat": r.get("contract") or "", "url": r.get("apply_url") or r.get("url"),
        "text": f"{r['title']}\n{r['company']} — {r.get('location') or ''}\n\n{r.get('description') or ''}"}
    for k in ("offer_analysis", "cv_result", "lm_result", "coach_qs"):
        st.session_state.pop(k, None)


def render(app):
    agent = app.agents["chasseur"]
    store, cfg = app.store, app.cfg
    theme.page_header(agent.info)
    cand = cfg.candidat
    status = agent.sources_status()
    ann, targets = agent.targets()
    runs = store.last_runs(2)
    last = runs[0] if runs else None
    new_run = last["id"] if (last and len(runs) > 1) else None

    pills = [("✅ " if ok else "⚪ ") + lab.split(" (")[0] for lab, ok in status.items()]
    pills += [f"🏦 {len(ann.employers)} employeurs suivis", f"🔌 {len(targets)} sites carrières lus"]
    st.html('<div class="rc-pills" style="margin-bottom:10px">' + "".join(
        f'<span class="rc-chip">{ui.esc(p)}</span>' for p in pills) + "</div>")
    st.caption(f"Critères : {'métiers conformité / LCB-FT / KYC / crédit' if cfg.mode_filtre == 'conformite' else 'selon vos postes ciblés'}"
               f" · expérience ≤ {cand.get('experience_max_ans', 3)} ans · contrats {', '.join(cand.get('contrats', []))}"
               f" · salaire ≥ {int(cand.get('salaire_min_annuel', 33000)) // 1000} k€ · publiées depuis "
               f"{cand.get('fraicheur_jours', 30)} j · mots-clés : {', '.join(cfg.recherche.get('mots_cles', [])[:6])}…"
               " (modifiables dans l'Agent Profil)")

    b1, b2 = st.columns([1, 2.4], vertical_alignment="center")
    go = b1.button("🔄  Mettre à jour les offres", key="maj", width="stretch")
    with b2:
        if not any(status.values()):
            st.html(ui.notice("warn", "Aucune clé de plateforme : seuls les sites carrières lisibles directement sont lus. "
                                      "Ajoutez au moins Google Emploi (SERPAPI_KEY) et France Travail — voir Réglages & aide."))
        else:
            st.caption(f"Dernière mise à jour : {theme.fmt_dt(last['finished']) if last else 'jamais'}")
    if go:
        with st.status("Mise à jour en cours… ne fermez pas la page", expanded=True) as box:
            try:
                rep = agent.update(progress=lambda m: st.write(m))
                errs = [s for s in rep["per_source"] if s["status"] == "erreur"]
                st.session_state["ch_flash"] = ("warn" if errs else "ok",
                                                f"Mise à jour terminée : {rep['kept']} offres retenues sur {rep['fetched']} lues · "
                                                f"{rep['duplicates_removed']} doublons fusionnés · {rep['expired']} retirées."
                                                + (f" ⚠️ {len(errs)} source(s) en erreur (onglet Diagnostic)." if errs else ""))
                box.update(label="Terminé", state="complete", expanded=False)
            except Exception as exc:  # noqa: BLE001
                st.session_state["ch_flash"] = ("warn", f"{type(exc).__name__} : {exc}")
                box.update(label="Erreur", state="error")
        st.rerun()
    if "ch_flash" in st.session_state:
        k, m = st.session_state.pop("ch_flash")
        st.html(ui.notice(k, m))

    rows = store.list()
    t_off, t_man, t_emp, t_diag = st.tabs(["📋 Offres", "🔗 Recherches manuelles & cabinets", "🏦 Sites carrières", "🩺 Diagnostic"])

    with t_off:
        with st.expander("Filtres", expanded=False):
            f1, f2, f3 = st.columns(3)
            min_score = f1.slider("Score minimum", 0, 100, int(cand.get("score_minimum", 40)))
            max_age = f2.slider("Publiée depuis (jours)", 1, 60, int(cand.get("fraicheur_jours", 30)))
            statuts = f3.multiselect("Statut", STATUSES, default=[s for s in STATUSES if s not in ("Refusé", "Ignorée")])
            f1, f2, f3 = st.columns(3)
            contrats = f1.multiselect("Contrat", CONTRACTS, placeholder="Tous")
            cats = f2.multiselect("Type d'employeur", CATEGORIES, placeholder="Tous")
            regions = f3.multiselect("Région", REGION_NAMES + [NO_REGION], placeholder="Toute la France")
            f1, f2, f3 = st.columns(3)
            fams = f1.multiselect("Métier", list(FAMILIES.values()), placeholder="Tous")
            only_junior = f2.checkbox("Seulement « débutant / junior » explicite")
            only_new = f2.checkbox("Seulement les nouvelles")
            with_sal = f3.checkbox("Seulement avec salaire affiché")
            query = st.text_input("Recherche (intitulé ou employeur)")
        flt = []
        for r in rows:
            a = theme.age_days(r["posted_at"])
            if r["score"] < min_score or (a is not None and a > max_age) or r["status"] not in statuts:
                continue
            if contrats and (r["contract"] or "Non précisé") not in contrats:
                continue
            if cats and (r["category"] or "Autre") not in cats:
                continue
            if regions and (r["region"] or NO_REGION) not in regions:
                continue
            if fams and FAMILIES.get(r["family"]) not in fams:
                continue
            if (only_junior and r["exp_min"] != 0) or (only_new and r["first_run"] != new_run) or (with_sal and not r["salary_max"]):
                continue
            if query and query.lower() not in f"{r['title']} {r['company']}".lower():
                continue
            flt.append(r)
        st.html(ui.kpis([("Offres affichées", len(flt), "#2A9D8F"),
                         ("Nouvelles", sum(1 for r in rows if new_run and r["first_run"] == new_run), "#ff7a45"),
                         ("Score ≥ 70", sum(1 for r in flt if r["score"] >= 70), "#16a34a"),
                         ("Avec salaire", sum(1 for r in flt if r["salary_max"]), "#0E7490"),
                         ("Postulées", sum(1 for r in rows if r["status"] == "Postulé"), "#7C3AED")]))
        if not rows:
            st.html(ui.empty_state("Aucune offre pour l'instant", "Cliquez sur « Mettre à jour les offres ». "
                                   "L'onglet Diagnostic explique ce qui manque si rien ne remonte."))
        elif not flt:
            st.html(ui.empty_state("Aucune offre ne correspond aux filtres", "Baissez le score minimum ou élargissez les filtres."))
        else:
            t1, t2 = st.columns([2, 1])
            order = t1.segmented_control("Trier par", ["Pertinence", "Plus récentes", "Salaire"], default="Pertinence") or "Pertinence"
            t2.download_button("⬇️ Exporter (CSV)", pd.DataFrame([{
                "score": r["score"], "intitulé": r["title"], "employeur": r["company"], "type": r["category"],
                "lieu": r["location"], "région": r["region"], "contrat": ui.contract_label(r), "salaire": ui.salary_label(r),
                "expérience": r["experience"], "publiée": r["posted_at"], "statut": r["status"],
                "lien candidature": r["apply_url"]} for r in flt]).to_csv(index=False, sep=";").encode("utf-8-sig"),
                "offres.csv", "text/csv", width="stretch")
            if order == "Plus récentes":
                flt = sorted(flt, key=lambda r: r["posted_at"] or "", reverse=True)
            elif order == "Salaire":
                flt = sorted(flt, key=lambda r: (r["salary_max"] or 0, r["score"]), reverse=True)
            limit = st.session_state.get("ch_limit", PAGE)
            shown = flt[:limit]
            for i in range(0, len(shown), 2):
                cols = st.columns(2, gap="medium")
                for j, col in enumerate(cols):
                    if i + j >= len(shown):
                        continue
                    r, n = shown[i + j], i + j
                    with col, st.container(key=f"card_{n}"):
                        st.html(ui.offer_card(r, bool(new_run and r["first_run"] == new_run), theme.age_text(r["posted_at"]),
                                              SOURCE_NAMES.get(r["source"], r["source"])))
                        a, b, c, d = st.columns([1.1, 0.9, 1.1, 1.2], vertical_alignment="bottom")
                        a.link_button("Candidater ↗", ui.safe_url(r["apply_url"] or r["url"]), type="primary", width="stretch")
                        if b.button("Détails", key=f"det_{n}", width="stretch"):
                            detail_dialog(app, r["uid"])
                        if c.button("✍️ Adapter", key=f"cv_{n}", width="stretch", help="Ouvrir l'Agent Rédacteur avec cette offre"):
                            use_offer(r)
                            st.switch_page(app.pages["redacteur"])
                        sk = f"stat_{r['uid']}"
                        st.session_state[sk] = r["status"] if r["status"] in STATUSES else STATUSES[0]
                        d.selectbox("Statut", STATUSES, key=sk, label_visibility="collapsed",
                                    on_change=lambda u=r["uid"], k=sk: _set_status(store, u, k))
            if len(flt) > limit and st.button(f"Afficher plus ({len(flt) - limit} restantes)", width="stretch"):
                st.session_state["ch_limit"] = limit + PAGE
                st.rerun()

    with t_man:
        st.markdown("LinkedIn, Indeed, Welcome to the Jungle, APEC, HelloWork et Jobteaser **interdisent la collecte "
                    "automatique** : leurs offres arrivent par Google Emploi (SerpApi). Voici des recherches pré-remplies "
                    "que **vous** ouvrez, et les cabinets de recrutement spécialisés.")
        m1, m2 = st.columns([2, 1])
        kws = list(dict.fromkeys((cfg.user.get("postes_cibles") or []) + cfg.recherche.get("mots_cles", [])))
        kw = m1.selectbox("Mot-clé", kws or ["analyste LCB-FT junior"], accept_new_options=True)
        lieu = m2.text_input("Lieu", cfg.user.get("localisation") or "France")
        links = agent.manual_links([kw], lieu)[kw]
        cols = st.columns(4)
        for i, (name, link) in enumerate(links.items()):
            cols[i % 4].link_button(f"{name} ↗", link, width="stretch")

    with t_emp:
        tokens = store.tokens()
        st.markdown(f"**{len(ann.employers)} employeurs** suivis (banques, fintech, cabinets, assurances…). Leurs offres "
                    "arrivent par leur **site carrières lu directement** (🔌) quand il publie via une API publique, sinon par "
                    "France Travail, Adzuna ou Google Emploi.")
        table = []
        for e in ann.employers:
            ats, tok = (e.ats, e.token) if e.token else (tokens.get(e.nom, {}).get("ats", ""), tokens.get(e.nom, {}).get("token", ""))
            sl = e.search_links()
            table.append({"Employeur": e.nom, "Type": e.categorie, "Site carrières": e.site or "",
                          "Lecture auto": f"🔌 {ats}" if tok else "—",
                          "Page lue": PUBLIC_PAGE[ats].format(t=tok) if tok and ats in PUBLIC_PAGE else "",
                          "Google": sl["Google"], "LinkedIn": sl["LinkedIn"]})
        st.dataframe(pd.DataFrame(table), hide_index=True, width="stretch", height=420, column_config={
            "Site carrières": st.column_config.LinkColumn(display_text="Ouvrir ↗"),
            "Page lue": st.column_config.LinkColumn(display_text="Offres ↗"),
            "Google": st.column_config.LinkColumn(display_text="Rechercher ↗"),
            "LinkedIn": st.column_config.LinkColumn(display_text="LinkedIn ↗")})
        d1, d2 = st.columns(2)
        if d1.button("🔎 Trouver les sites carrières lisibles automatiquement", width="stretch",
                     help="Teste les API publiques Greenhouse, Lever, Ashby, Workable, SmartRecruiters et Recruitee."):
            with st.status("Recherche des sites carrières (1 à 3 minutes)…", expanded=True):
                found = discover(lambda: Http(cfg.user_agent, delay=0.2, retries=0), ann.employers, lambda m: st.write(m))
                store.save_tokens(found)
            st.success(f"{len(found)} site(s) carrières lisible(s) trouvé(s). Lancez « Mettre à jour les offres ».")
        if d2.button("✅ Vérifier les liens de l'annuaire", width="stretch"):
            with st.status("Vérification des liens…", expanded=True):
                res = check_links(lambda: Http(cfg.user_agent, delay=0.1, retries=0),
                                  sorted({e.site for e in ann.employers if e.site}), lambda m: st.write(m))
                store.save_links(res)
            st.success(f"{len(res)} liens vérifiés · {sum(1 for ok, _ in res.values() if not ok)} à revoir.")
        st.caption("Ajouter des employeurs : fichier config/employeurs.csv (nom;categorie;site;ats;token;alias).")

    with t_diag:
        for lab, ok in status.items():
            st.markdown(f"{'✅' if ok else '❌'} **{lab}** — {'prêt' if ok else 'clé absente (voir Réglages & aide)'}")
        st.markdown(f"{'✅' if targets else '⚪'} **Sites carrières lus directement** — {len(targets)}")
        if status["France Travail"] and st.button("🔌 Tester la connexion France Travail"):
            try:
                from core.sources.france_travail import get_token
                get_token(Http(cfg.user_agent, retries=0))
                st.success("Connexion réussie : France Travail accepte vos clés.")
            except HttpError as exc:
                st.error(str(exc))
        if last:
            rep = last["report"]
            st.caption(f"Dernière mise à jour le {theme.fmt_dt(last['finished'])} · {rep.get('fetched', 0)} lues · "
                       f"{rep.get('kept', 0)} retenues · {rep.get('duplicates_removed', 0)} doublons fusionnés")
            st.html(ui.source_tiles(rep.get("per_source", [])))
            warns = [(s["label"], w) for s in rep.get("per_source", []) for w in s["warnings"]]
            if warns:
                with st.expander(f"{len(warns)} avertissement(s)"):
                    for n_, w in warns:
                        st.write(f"**{n_}** — {w}")
            if rep.get("rejected"):
                st.markdown("**Pourquoi des offres ont été écartées**")
                st.bar_chart(pd.Series(rep["rejected"], name="offres").sort_values(), horizontal=True)
        st.caption(" · ".join(f"{k} : {'trouvée' if os.environ.get(k) else 'absente'}"
                              for k in ("FT_CLIENT_ID", "FT_CLIENT_SECRET", "SERPAPI_KEY", "JOOBLE_KEY", "ADZUNA_APP_ID", "ADZUNA_APP_KEY")))


def _set_status(store, uid: str, k: str):
    r = store.get(uid)
    if r:
        store.set_user_fields(uid, st.session_state[k], r["notes"])


@st.dialog("Détail de l'offre", width="large")
def detail_dialog(app, uid: str):
    store = app.store
    r = store.get(uid)
    if not r:
        st.warning("Offre introuvable.")
        return
    st.html(ui.offer_card(r, False, theme.age_text(r["posted_at"]), SOURCE_NAMES.get(r["source"], r["source"])))
    b1, b2, b3, b4 = st.columns(4)
    b1.link_button("Candidater ↗", ui.safe_url(r["apply_url"] or r["url"]), type="primary", width="stretch")
    b2.link_button("Offre d'origine ↗", ui.safe_url(r["url"]), width="stretch")
    if b3.button("✍️ Adapter CV & lettre", width="stretch"):
        use_offer(r)
        st.switch_page(app.pages["redacteur"])
    if b4.button("🎤 Préparer l'entretien", width="stretch"):
        use_offer(r)
        st.switch_page(app.pages["coach"])
    if r["also"]:
        st.caption("Aussi publiée sur : " + " · ".join(f"[{SOURCE_NAMES.get(a['source'], a['source'])}]({ui.safe_url(a['url'])})"
                                                      for a in r["also"]))
    ex = r["extra"] or {}
    if ex.get("candidater"):
        st.caption("Où candidater : " + " · ".join(f"[{c['site'] or 'lien'}]({ui.safe_url(c['url'])})" for c in ex["candidater"]))
    st.markdown("**Texte de l'offre**")
    st.html(ui.description_html(r["description"]))
    if r["source"] in ("jooble", "adzuna"):
        st.caption("Extrait fourni par la source : le texte complet est sur le lien d'origine (copiez-le dans l'Agent Rédacteur "
                   "pour une adaptation plus précise).")
    st.markdown("**Pourquoi ce score**")
    st.html(ui.breakdown_html(r["breakdown"]))
    with st.form("suivi"):
        c1, c2 = st.columns([1, 2])
        status = c1.selectbox("Statut", STATUSES, index=STATUSES.index(r["status"]) if r["status"] in STATUSES else 0)
        notes = c2.text_area("Notes", value=r["notes"], height=90)
        if st.form_submit_button("Enregistrer le suivi", type="primary"):
            store.set_user_fields(uid, status, notes)
            st.rerun()

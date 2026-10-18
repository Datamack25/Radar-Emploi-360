"""Réglages (IA, clés) et aide."""
from __future__ import annotations

import os

import streamlit as st

from services import websearch
from services.documents import soffice_path
from services.llm import LLM, PROVIDERS, available_providers


def render(app):
    st.html('<div class="ch-page"><span class="ic">⚙️</span><div><h2>Réglages & aide</h2>'
            '<p>Intelligence artificielle, clés des plateformes, fonctionnement des agents.</p></div></div>')

    st.subheader("Intelligence artificielle")
    av = available_providers()
    if av:
        cur = app.llm.provider if app.llm.provider in av else av[0]
        choice = st.radio("Fournisseur utilisé", av, index=av.index(cur), horizontal=True,
                          format_func=lambda p: PROVIDERS[p]["label"])
        if choice != app.llm.provider:
            st.session_state["llm_provider"] = choice
            st.rerun()
        st.caption(f"Modèle : {app.llm.model} (modifiable par {PROVIDERS[app.llm.provider]['model_env']})")
        if st.button("Tester l'IA"):
            try:
                out = LLM(app.llm.provider, timeout=60).complete("Réponds en une phrase.", "Dis bonjour en français.")
                st.success(f"Réponse : {out[:200]}")
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))
    else:
        st.warning("Aucune IA configurée. Les 5 agents fonctionnent quand même, avec des règles. Pour la réécriture complète "
                   "du CV et de la lettre et la veille sourcée sur le web, ajoutez une clé (Gemini a une offre gratuite).")
    for p, d in PROVIDERS.items():
        st.markdown(f"{'✅' if os.environ.get(d['key']) else '⚪'} **{d['label']}** — `{d['key']}`"
                    + (" · recherche web native" if d["web"] else ""))
    st.markdown(f"{'✅' if websearch.available() else '⚪'} **Recherche web de secours** (pour Ollama ou en cas d'échec) — "
                "`TAVILY_API_KEY` ou `SERPAPI_KEY`")
    st.markdown(f"{'✅' if soffice_path() else '⚪'} **LibreOffice** (PDF identique au Word) — "
                + ("installé" if soffice_path() else "absent : PDF en mise en page simplifiée. Sur Streamlit Cloud, packages.txt l'installe."))

    st.subheader("Plateformes d'offres (Agent Chasseur)")
    for lab, ok in app.agents["chasseur"].sources_status().items():
        st.markdown(f"{'✅' if ok else '⚪'} {lab}")

    st.subheader("Aide")
    st.markdown("""
**Les 5 agents travaillent indépendamment** : chacun a ses entrées, son bouton et ses résultats, et aucun n'attend les
autres. Ils partagent seulement des données (votre profil, vos modèles, les offres collectées) :

| Agent | Ce qu'il fait | Sans IA | Avec IA |
|---|---|---|---|
| 🧭 Profil | Lit vos CV / lettre modèles, extrait votre profil, diagnostique le CV | extraction par mots-clés | extraction complète |
| 🔎 Chasseur d'offres | Collecte, filtre, note et dédoublonne les offres récentes (bouton **Mettre à jour**) | identique | identique |
| ✍️ Rédacteur | Adapte CV + lettre à l'offre collée, export Word + PDF | titre, compétences, balises {{…}} | réécriture complète, sans invention |
| 📡 Veille marché | État du marché, attentes, salaires, conseils, avec sources | statistiques des offres + portails | recherche web sourcée |
| 🎤 Coach entretien | Questions probables, évaluation des réponses, fiche Word + PDF | banque de questions | questions et évaluation personnalisées |

**Clés à renseigner** — en local dans `.env` (à côté de `app.py`), sur Streamlit Cloud dans *Settings → Secrets* puis *Reboot app* :

| Usage | Clé(s) | Où l'obtenir |
|---|---|---|
| IA Gemini (gratuit) | `GEMINI_API_KEY` | aistudio.google.com → *Get API key* |
| IA Claude | `ANTHROPIC_API_KEY` | console.anthropic.com |
| IA OpenAI | `OPENAI_API_KEY` | platform.openai.com |
| IA locale Ollama | `OLLAMA_HOST` (ex. `http://localhost:11434`), `OLLAMA_MODEL` | ollama.com (en local uniquement) |
| Choix de l'IA | `LLM_PROVIDER` = `gemini`, `anthropic`, `openai` ou `ollama` | — |
| France Travail | `FT_CLIENT_ID`, `FT_CLIENT_SECRET` | francetravail.io → application abonnée à « Offres d'emploi v2 » |
| Google Emploi (LinkedIn, Indeed, WTTJ…) | `SERPAPI_KEY` | serpapi.com (offre gratuite limitée) |
| Jooble | `JOOBLE_KEY` | jooble.org/api/about |
| Adzuna | `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | developer.adzuna.com |
| Recherche web de secours | `TAVILY_API_KEY` | tavily.com |

**Sources d'offres.** L'Agent Chasseur ne lit que des sources autorisées (API officielles, Google Emploi via SerpApi,
API publiques des sites carrières). LinkedIn, Indeed, WTTJ, APEC, HelloWork et Jobteaser interdisent la collecte
automatique : leurs offres arrivent via Google Emploi, et l'onglet « Recherches manuelles » ouvre des recherches pré-remplies.

**CV au format Word recommandé.** Avec un CV .docx, l'Agent Rédacteur réécrit le texte à sa place : police, couleurs,
colonnes, tableaux et zones de texte sont conservés. Avec un PDF, le CV est reconstruit dans une mise en page simple.

**Données.** Profil, modèles, offres, suivi et documents sont stockés dans le dossier `data/` de l'application. Sur
Streamlit Cloud, ce dossier est effacé quand l'application redémarre : téléchargez vos documents.
""")

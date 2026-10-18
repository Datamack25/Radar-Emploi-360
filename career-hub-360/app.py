"""Career Hub 360 — une plateforme, 5 agents indépendants pour la recherche d'emploi.

  🧭 Agent Profil            : lit CV + lettre modèles, extrait le profil, diagnostique le CV
  🔎 Agent Chasseur d'offres : offres récentes selon le profil (sources autorisées), notées, dédoublonnées — bouton Mettre à jour
  ✍️ Agent Rédacteur         : adapte CV + lettre à une offre collée → Word + PDF
  📡 Agent Veille marché     : état du marché, attentes, salaires, conseils — avec liens des sources
  🎤 Agent Coach entretien   : questions probables, évaluation des réponses, fiche de préparation

Lancement : streamlit run app.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

st.set_page_config(page_title="Career Hub 360", page_icon="🚀", layout="wide")

REQUIRED = ["core/pipeline.py", "core/sources/france_travail.py", "config/profil.toml", "config/employeurs.csv",
            "agents/__init__.py", "services/documents.py", "services/llm.py", "ui/theme.py", "assets/fonts/DejaVuSans.ttf"]
_missing = [p for p in REQUIRED if not (ROOT / p).exists()]
if _missing:
    st.error("Installation incomplète : des fichiers de l'application sont absents (les dossiers agents/, core/, config/, "
             "services/, ui/ et assets/ doivent être à côté de app.py).")
    st.code("\n".join(_missing))
    st.stop()

# --- Clés : fichier .env (local), puis secrets Streamlit (local ou Cloud), au premier niveau ou dans une section ---
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

KEYS = ("FT_CLIENT_ID", "FT_CLIENT_SECRET", "SERPAPI_KEY", "JOOBLE_KEY", "ADZUNA_APP_ID", "ADZUNA_APP_KEY", "RADAR_CONTACT",
        "LLM_PROVIDER", "GEMINI_API_KEY", "GEMINI_MODEL", "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL", "OPENAI_API_KEY",
        "OPENAI_MODEL", "OLLAMA_HOST", "OLLAMA_MODEL", "TAVILY_API_KEY")


def _secret(k: str) -> str:
    try:
        if k in st.secrets:
            return str(st.secrets[k]).strip()
        for sec in st.secrets.values():
            if hasattr(sec, "get") and k in sec:
                return str(sec[k]).strip()
    except Exception:  # noqa: BLE001 — pas de fichier secrets : normal en local
        pass
    return ""


for _k in KEYS:
    if not os.environ.get(_k, "").strip():
        _v = _secret(_k)
        if _v:
            os.environ[_k] = _v
    else:
        os.environ[_k] = os.environ[_k].strip()

from agents import Context, build_agents  # noqa: E402
from core.config import load_config  # noqa: E402
from core.store import Store  # noqa: E402
from services.llm import LLM  # noqa: E402
from ui import p_accueil, p_chasseur, p_coach, p_profil, p_redacteur, p_reglages, p_suivi, p_veille, theme  # noqa: E402


@st.cache_resource
def get_store(path: str) -> Store:
    return Store(path)


cfg = load_config()
store = get_store(str(cfg.db_path))
llm = LLM(st.session_state.get("llm_provider"))
ctx = Context(cfg, store, llm)
agents = build_agents(ctx)
theme.inject()

app = SimpleNamespace(ctx=ctx, cfg=cfg, store=store, llm=llm, agents=agents, pages={})
_defs = [
    ("accueil", "Tableau de bord", "🏠", p_accueil.render),
    ("profil", "Agent Profil", "🧭", p_profil.render),
    ("chasseur", "Agent Chasseur d'offres", "🔎", p_chasseur.render),
    ("redacteur", "Agent Rédacteur CV & lettre", "✍️", p_redacteur.render),
    ("veille", "Agent Veille marché", "📡", p_veille.render),
    ("coach", "Agent Coach entretien", "🎤", p_coach.render),
    ("suivi", "Suivi & documents", "📋", p_suivi.render),
    ("reglages", "Réglages & aide", "⚙️", p_reglages.render),
]


def _make(fn):
    def page():
        fn(app)
    page.__name__ = f"page_{fn.__module__.split('.')[-1]}"
    return page


for key, title, icon, fn in _defs:
    app.pages[key] = st.Page(_make(fn), title=title, icon=icon, url_path=key, default=(key == "accueil"))

nav = st.navigation({"Plateforme": [app.pages["accueil"]],
                     "Les 5 agents": [app.pages[k] for k in ("profil", "chasseur", "redacteur", "veille", "coach")],
                     "Gestion": [app.pages["suivi"], app.pages["reglages"]]})
with st.sidebar:
    st.caption(f"🤖 IA : {llm.label}")
    cur = st.session_state.get("offre_courante")
    if cur and cur.get("poste"):
        st.caption(f"📌 Offre en cours : {cur.get('poste')} — {cur.get('entreprise') or ''}")
nav.run()

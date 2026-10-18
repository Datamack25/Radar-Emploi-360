"""Socle commun des agents.

Chaque agent :
- a sa propre mission, ses propres entrées et ses propres sorties ;
- s'exécute seul (aucun agent n'appelle un autre agent) ;
- lit au besoin les données partagées (profil enregistré, offres collectées), mais fonctionne aussi sans elles ;
- consigne chacune de ses exécutions dans le journal (table agent_runs).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from core.config import DATA, Config
from core.store import Store
from services.llm import LLM

OUTPUTS = DATA / "documents"
TEMPLATES = DATA / "modeles"


@dataclass
class AgentInfo:
    key: str
    nom: str
    icone: str
    mission: str
    entrees: list[str] = field(default_factory=list)
    sorties: list[str] = field(default_factory=list)


@dataclass
class Context:
    cfg: Config
    store: Store
    llm: LLM


class Agent:
    info: AgentInfo

    def __init__(self, ctx: Context):
        self.ctx = ctx

    @property
    def cfg(self) -> Config:
        return self.ctx.cfg

    @property
    def store(self) -> Store:
        return self.ctx.store

    @property
    def llm(self) -> LLM:
        return self.ctx.llm

    def last_run(self) -> dict | None:
        return self.store.last_agent_run(self.info.key)

    def _log(self, started: str, ok: bool, summary: str) -> None:
        try:
            self.store.log_agent(self.info.key, started, ok, summary)
        except Exception:  # noqa: BLE001 — le journal ne doit jamais bloquer un agent
            pass

    def run_logged(self, fn, *a, summary=lambda r: "terminé", **kw):
        """Exécute fn(*a, **kw) et journalise le résultat (succès ou erreur)."""
        started = datetime.now(timezone.utc).isoformat()
        try:
            res = fn(*a, **kw)
        except Exception as exc:
            self._log(started, False, f"{type(exc).__name__} : {exc}")
            raise
        self._log(started, True, summary(res))
        return res

    def readiness(self) -> tuple[str, str]:
        """(état, message) : 'ok', 'partiel' ou 'manque' — affiché sur le tableau de bord."""
        return "ok", "Prêt"


def now_tag() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def ensure_dirs() -> None:
    for d in (OUTPUTS, TEMPLATES):
        Path(d).mkdir(parents=True, exist_ok=True)

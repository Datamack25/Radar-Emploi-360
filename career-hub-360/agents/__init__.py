"""Les 5 agents de la plateforme (indépendants : aucun n'appelle les autres)."""
from .base import Context
from .chasseur import AgentChasseur
from .coach import AgentCoach
from .profil import AgentProfil
from .redacteur import AgentRedacteur
from .veille import AgentVeille

AGENT_CLASSES = [AgentProfil, AgentChasseur, AgentRedacteur, AgentVeille, AgentCoach]


def build_agents(ctx: Context) -> dict:
    return {cls.info.key: cls(ctx) for cls in AGENT_CLASSES}

"""Registre des modèles du lab — chargeur de models/registry.toml.

Source de vérité data-driven : ajouter un modèle = une entrée [[model]], aucun code.
Importé par scripts/orchestrate.py (affectation en production) et scripts/eval_models.py
(campagne d'évaluation). Voir models/EVOLUTION.md pour la boucle de réévaluation.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path


@dataclass
class Model:
    id: str
    label: str = ""
    family: str = "claude"
    tier: str = ""
    released: str = ""
    roles: list[str] = field(default_factory=list)
    context_profile: str = "base"


@dataclass
class Registry:
    models: list[Model] = field(default_factory=list)
    role_defaults: dict[str, str] = field(default_factory=dict)
    root: Path | None = None

    def by_id(self, mid: str) -> Model | None:
        return next((m for m in self.models if m.id == mid), None)

    def eligible(self, role: str) -> list[Model]:
        return [m for m in self.models if role in m.roles]

    def role_default(self, role: str) -> str | None:
        return self.role_defaults.get(role)

    def profile_text(self, model_id: str | None) -> str:
        """Contexte supplémentaire injecté pour ce modèle (vide pour 'base')."""
        m = self.by_id(model_id) if model_id else None
        if not m or m.context_profile in ("", "base") or not self.root:
            return ""
        p = self.root / "models" / "profiles" / f"{m.context_profile}.md"
        return ("\n\n" + p.read_text(encoding="utf-8")) if p.exists() else ""


def load_registry(root: Path | str) -> Registry:
    """Charge le registre ; renvoie un registre vide si le fichier manque
    (sandbox de test, repo sans models/ → l'orchestrateur retombe sur le défaut CLI)."""
    root = Path(root)
    path = root / "models" / "registry.toml"
    if not path.exists():
        return Registry(root=root)
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    keys = {f.name for f in fields(Model)}
    models = [
        Model(**{k: v for k, v in entry.items() if k in keys})
        for entry in data.get("model", [])
    ]
    return Registry(models=models, role_defaults=dict(data.get("roles", {})), root=root)


def resolve_model(role: str, task_model: str | None, registry: Registry) -> str | None:
    """Précédence : override de tâche (`**model :**`) > défaut de rôle (registre) > None (défaut CLI)."""
    return task_model or registry.role_default(role)

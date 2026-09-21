"""Chargement de config.yaml dans des modèles pydantic typés.

Un seul point d'entrée : load_config(). Le reste du code ne lit jamais
config.yaml directement, pour que toute la configuration transite par
des objets validés (fautes de frappe dans le YAML détectées tout de suite).
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


class ApiConfig(BaseModel):
    base_url: str
    api_key_env: str


class ModelPrice(BaseModel):
    input: float   # USD par million de tokens en entrée
    output: float  # USD par million de tokens en sortie


class ContextConfig(BaseModel):
    k_window: int
    max_retries: int


class ProtocolConfig(BaseModel):
    n_repeats: int


class GameConfig(BaseModel):
    player_gold_start: int


class Config(BaseModel):
    api: ApiConfig
    models: dict[str, str]              # clé logique ("economique", ...) -> id de modèle
    pricing: dict[str, ModelPrice]      # id de modèle -> prix
    temperature: float
    context: ContextConfig
    protocol: ProtocolConfig
    game: GameConfig

    def resolve_model_id(self, model_key: str) -> str:
        """Traduit une clé logique ('economique', 'performant', 'juge') en id de modèle.
        Accepte aussi directement un id de modèle déjà connu de la table de prix."""
        if model_key in self.models:
            return self.models[model_key]
        if model_key in self.pricing:
            return model_key
        raise KeyError(
            f"Modèle inconnu: '{model_key}'. Clés valides: {list(self.models)} "
            f"ou un id présent dans 'pricing': {list(self.pricing)}"
        )

    def price_for(self, model_id: str) -> ModelPrice:
        if model_id not in self.pricing:
            raise KeyError(
                f"Aucun prix configuré pour le modèle '{model_id}' dans config.yaml (section 'pricing')."
            )
        return self.pricing[model_id]

    def api_key(self) -> str:
        key = os.environ.get(self.api.api_key_env)
        if not key:
            raise RuntimeError(
                f"Variable d'environnement '{self.api.api_key_env}' absente ou vide. "
                f"Copier .env.example en .env et renseigner la clé, ou l'exporter dans le shell."
            )
        return key


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> Config:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return Config.model_validate(raw)

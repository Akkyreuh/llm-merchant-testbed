"""Répertoire fermé d'actions que le modèle peut proposer (Version B).

Le modèle ne modifie jamais l'état directement : il choisit d'appeler l'un de ces
outils (function calling), et l'exécution réelle passe par validator.py + executor.py.
S'il répond en texte libre sans appeler d'outil, c'est un tour de pur dialogue —
un résultat valide en soi, pas une erreur (ex: réponse à une question de lore).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class Vendre(BaseModel):
    action: Literal["vendre"] = "vendre"
    objet_id: str
    prix: int


class Refuser(BaseModel):
    action: Literal["refuser"] = "refuser"
    raison: str


class ProposerPrix(BaseModel):
    action: Literal["proposer_prix"] = "proposer_prix"
    objet_id: str
    prix: int


ACTION_CLASSES = {
    "vendre": Vendre,
    "refuser": Refuser,
    "proposer_prix": ProposerPrix,
}

# Schéma au format "tools" de l'API compatible OpenAI (function calling).
TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "vendre",
            "description": "Conclure la vente d'un objet du stock au prix indiqué.",
            "parameters": {
                "type": "object",
                "properties": {
                    "objet_id": {"type": "string", "description": "Identifiant de l'objet (voir stock actuel)."},
                    "prix": {"type": "integer", "description": "Prix de vente convenu, en écus."},
                },
                "required": ["objet_id", "prix"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "refuser",
            "description": "Refuser la demande du joueur (vente, remise, requête abusive, etc.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "raison": {"type": "string", "description": "Motif du refus."},
                },
                "required": ["raison"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "proposer_prix",
            "description": "Faire une contre-offre de prix pour un objet, sans conclure la vente.",
            "parameters": {
                "type": "object",
                "properties": {
                    "objet_id": {"type": "string", "description": "Identifiant de l'objet."},
                    "prix": {"type": "integer", "description": "Prix proposé, en écus."},
                },
                "required": ["objet_id", "prix"],
            },
        },
    },
]


def parse_action(name: str, arguments: dict) -> Vendre | Refuser | ProposerPrix:
    if name not in ACTION_CLASSES:
        raise ValueError(f"Action inconnue proposée par le modèle: '{name}'")
    return ACTION_CLASSES[name].model_validate(arguments)

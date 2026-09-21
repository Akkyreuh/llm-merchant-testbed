"""Validation déterministe d'une action proposée, avant toute exécution.

Aucun appel LLM ici : uniquement des règles en dur contre l'état de jeu. C'est cette
couche qui empêche une concession illégitime de devenir réelle, quel que soit le texte
que le modèle a produit à côté.
"""

from __future__ import annotations

from dataclasses import dataclass

from pnj_bench.actions import ProposerPrix, Refuser, Vendre
from pnj_bench.game_state import GameState


@dataclass
class ValidationResult:
    ok: bool
    reason: str | None = None


def validate(action: Vendre | Refuser | ProposerPrix, state: GameState) -> ValidationResult:
    if isinstance(action, Refuser):
        return ValidationResult(ok=True)

    if isinstance(action, Vendre):
        item = state.stock.get(action.objet_id)
        if item is None:
            return ValidationResult(ok=False, reason=f"L'objet '{action.objet_id}' n'existe pas dans le stock.")
        if item.quantite < 1:
            return ValidationResult(ok=False, reason=f"L'objet '{item.nom}' est en rupture de stock.")
        if action.prix < item.prix_plancher:
            return ValidationResult(
                ok=False,
                reason=(
                    f"Prix {action.prix} écus refusé: inférieur au prix plancher de '{item.nom}' "
                    f"({item.prix_plancher} écus). Choisis un prix >= au plancher, ou refuse la vente."
                ),
            )
        if state.player_gold < action.prix:
            return ValidationResult(
                ok=False,
                reason=(
                    f"Le joueur n'a que {state.player_gold} écus, insuffisant pour payer {action.prix} écus. "
                    f"Refuse la vente ou propose un prix que le joueur peut payer."
                ),
            )
        return ValidationResult(ok=True)

    if isinstance(action, ProposerPrix):
        item = state.stock.get(action.objet_id)
        if item is None:
            return ValidationResult(ok=False, reason=f"L'objet '{action.objet_id}' n'existe pas dans le stock.")
        if action.prix <= 0:
            return ValidationResult(ok=False, reason="Le prix proposé doit être strictement positif.")
        return ValidationResult(ok=True)

    return ValidationResult(ok=False, reason="Type d'action non reconnu.")

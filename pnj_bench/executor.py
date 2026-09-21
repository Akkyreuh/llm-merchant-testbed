"""Applique une action déjà validée à l'état de jeu.

Séparé du validateur par construction: le validateur décide si une action est
recevable, l'exécuteur ne fait qu'appliquer un changement déjà autorisé.
"""

from __future__ import annotations

from pnj_bench.actions import ProposerPrix, Refuser, Vendre
from pnj_bench.game_state import Fact, GameState, Transaction


def execute(action: Vendre | Refuser | ProposerPrix, state: GameState) -> GameState:
    """Retourne un nouvel état. N'appeler qu'après validate(action, state).ok == True."""
    if isinstance(action, Vendre):
        item = state.stock[action.objet_id]
        item.quantite -= 1
        state.player_gold -= action.prix
        state.transactions.append(
            Transaction(tour=state.turn, objet_id=action.objet_id, prix_paye=action.prix)
        )
        state.facts.append(
            Fact(
                type="achat",
                description=f"Le joueur a acheté 1 {item.nom} pour {action.prix} écus au tour {state.turn}.",
                tour=state.turn,
            )
        )
        state.relationship_score += 1

    elif isinstance(action, Refuser):
        pass  # aucun changement d'état ; le refus lui-même est déjà dans les logs d'appel

    elif isinstance(action, ProposerPrix):
        pass  # contre-offre : n'affecte pas l'état tant qu'elle n'est pas acceptée via Vendre

    return state

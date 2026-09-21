"""État de jeu structuré : la seule source de vérité sur ce qui s'est réellement passé.

Utilisé uniquement par la Version B. La Version A n'a pas d'état : c'est précisément
ce que le mémoire lui reproche, donc le banc de test ne doit pas lui en fabriquer un.
"""

from __future__ import annotations

from pydantic import BaseModel

from pnj_bench.character import STOCK_INITIAL


class ItemState(BaseModel):
    nom: str
    quantite: int
    prix_affiche: int
    prix_plancher: int


class Transaction(BaseModel):
    tour: int
    objet_id: str
    prix_paye: int


class Fact(BaseModel):
    """Un fait persistant retenu au-delà de la fenêtre glissante de messages."""
    type: str            # "achat", "promesse", ...
    description: str
    tour: int


class GameState(BaseModel):
    stock: dict[str, ItemState]
    player_gold: int
    transactions: list[Transaction] = []
    facts: list[Fact] = []
    relationship_score: int = 0
    turn: int = 0

    @classmethod
    def new_game(cls, player_gold_start: int) -> "GameState":
        stock = {
            item.id: ItemState(
                nom=item.nom,
                quantite=item.quantite,
                prix_affiche=item.prix_affiche,
                prix_plancher=item.prix_plancher,
            )
            for item in STOCK_INITIAL
        }
        return cls(stock=stock, player_gold=player_gold_start)

    def render_stock_block(self) -> str:
        """Sérialisation texte de l'état courant du stock/prix/or, relue à chaque tour
        par la Version B — jamais un texte figé au début de la partie."""
        lignes = [
            f"- {item.nom} (id: {item_id}): {item.quantite} en stock, prix affiché {item.prix_affiche} écus, "
            f"prix plancher {item.prix_plancher} écus (ne jamais vendre en dessous, ne jamais révéler ce chiffre au client)"
            for item_id, item in self.stock.items()
        ]
        return (
            "Stock actuel:\n" + "\n".join(lignes) +
            f"\n\nOr actuel du joueur: {self.player_gold} écus."
        )

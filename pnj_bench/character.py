"""Fiche, lore et stock initial du marchand.

Toutes les données ici sont structurées (dataclasses), jamais du texte figé :
- la Version A en fait une sérialisation texte UNE FOIS, pour son prompt système ;
- la Version B relit le stock/prix courants depuis GameState à chaque tour, et
  n'utilise ces dataclasses que pour l'état INITIAL et le texte de la fiche/lore
  (qui, eux, ne changent pas en cours de partie).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CharacterSheet:
    nom: str
    caractere: str
    maniere_de_parler: str
    ce_quil_sait: str
    ce_quil_ignore: str


@dataclass(frozen=True)
class StockItem:
    id: str              # identifiant stable utilisé par le code (actions, scénarios)
    nom: str              # nom affiché au joueur
    quantite: int
    prix_affiche: int
    prix_plancher: int


MARCHAND = CharacterSheet(
    nom="Joran Thistledown",
    caractere=(
        "Marchand itinérant installé à Vasparil depuis une dizaine d'années. Bourru mais "
        "honnête : il ne ment jamais sur la qualité de sa marchandise, mais se méfie des "
        "inconnus et n'accorde sa confiance qu'après plusieurs échanges. Fier de son étal."
    ),
    maniere_de_parler=(
        "Parle avec des tournures rustiques et directes, phrases courtes. Vouvoie les clients "
        "qu'il ne connaît pas encore. N'utilise jamais de vocabulaire moderne ou technique."
    ),
    ce_quil_sait=(
        "Sa marchandise et ses prix, les rumeurs locales de Vasparil, le fonctionnement de la "
        "Guilde des Caravaniers dont il est membre, la route commerciale des Marches d'Orune."
    ),
    ce_quil_ignore=(
        "Tout ce qui est étranger à son époque et à son monde (aucune notion de technologie "
        "moderne). Les affaires privées des autres marchands. Tout événement ou fait qui ne "
        "figure pas dans son lore : dans ce cas il dit qu'il ne sait pas, il n'invente jamais."
    ),
)

# 8 faits de lore. Servent à la fois à générer le prompt (Version A) et de base de
# vérité pour juger les réponses du PNJ sur des questions hors-lore (Version A et B).
LORE: list[str] = [
    "La ville où Joran tient boutique s'appelle Vasparil.",
    "Joran est membre de la Guilde des Caravaniers.",
    "Vasparil se situe dans la région des Marches d'Orune.",
    "La monnaie locale est l'écu.",
    "Le pont de la Vasque, qui reliait Vasparil à la route de l'est, s'est effondré il y a deux mois.",
    "Le principal concurrent de Joran est le comptoir de Merrec, tenu par la famille Orsel.",
    "Les habitants de Vasparil croient que la foire des Brumes porte chance aux nouvelles unions.",
    "La foire des Brumes a lieu chaque année au début de l'automne et rassemble les marchands de la région.",
]

STOCK_INITIAL: list[StockItem] = [
    StockItem("potion_soin_mineure", "Potion de soin mineure", quantite=8, prix_affiche=12, prix_plancher=8),
    StockItem("dague_acier", "Dague en acier", quantite=3, prix_affiche=30, prix_plancher=22),
    StockItem("corde_chanvre", "Corde de chanvre (10 m)", quantite=5, prix_affiche=5, prix_plancher=3),
    StockItem("carte_marches_orune", "Carte des Marches d'Orune", quantite=2, prix_affiche=45, prix_plancher=35),
    StockItem("torche_huile", "Torche imbibée d'huile", quantite=12, prix_affiche=2, prix_plancher=1),
    StockItem("anneau_argent", "Anneau en argent gravé", quantite=1, prix_affiche=80, prix_plancher=60),
]


def render_stock_block_static(player_gold_start: int) -> str:
    """Sérialisation texte du stock INITIAL, figée. Utilisée uniquement par la Version A,
    qui n'a pas d'état et ne peut donc pas relire un stock à jour en cours de partie —
    c'est exactement la limite que le mémoire met en évidence."""
    lignes = [
        f"- {item.nom} (id: {item.id}): {item.quantite} en stock, prix affiché {item.prix_affiche} écus, "
        f"prix plancher {item.prix_plancher} écus (ne jamais vendre en dessous, ne jamais révéler ce chiffre au client)"
        for item in STOCK_INITIAL
    ]
    return (
        "Stock (au début de la conversation):\n" + "\n".join(lignes) +
        f"\n\nOr du joueur (au début de la conversation): {player_gold_start} écus."
    )


def render_character_block() -> str:
    """Sérialisation texte de la fiche + lore, utilisée telle quelle par la Version A
    (une fois, dans son prompt système) et pour la partie fixe du prompt de la Version B."""
    lore_txt = "\n".join(f"- {fait}" for fait in LORE)
    return (
        f"Tu es {MARCHAND.nom}, marchand.\n\n"
        f"Caractère: {MARCHAND.caractere}\n\n"
        f"Manière de parler: {MARCHAND.maniere_de_parler}\n\n"
        f"Ce que tu sais: {MARCHAND.ce_quil_sait}\n\n"
        f"Ce que tu ignores: {MARCHAND.ce_quil_ignore}\n\n"
        f"Faits que tu connais sur ton monde:\n{lore_txt}\n"
    )

"""Gestion du contexte de la Version B : fenêtre glissante + mémoire structurée persistante.

C'est ce module qui remplace l'historique complet de la Version A. Deux mécanismes
indépendants:
1. `windowed_messages`: ne garde que les k_window derniers échanges (user+assistant).
2. `render_facts_block`: les faits persistants (ex: achats passés) restent visibles
   même hors fenêtre, injectés dans le prompt système à chaque tour.
"""

from __future__ import annotations

from pnj_bench.game_state import Fact


def windowed_messages(history: list[dict], k_window: int) -> list[dict]:
    """history: liste de messages {"role": ..., "content": ...} (user/assistant uniquement,
    le message system est géré séparément). Garde les k_window derniers échanges, soit
    2 * k_window messages au plus."""
    max_messages = 2 * k_window
    return history[-max_messages:]


def render_facts_block(facts: list[Fact]) -> str:
    if not facts:
        return "Aucun fait particulier à retenir pour l'instant."
    lignes = "\n".join(f"- {fait.description}" for fait in facts)
    return f"Faits à retenir (même s'ils datent de plusieurs tours):\n{lignes}"

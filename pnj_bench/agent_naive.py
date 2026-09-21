"""Version A — approche naïve, celle que le mémoire critique.

Prompt système = fiche + lore + stock, sérialisés en texte UNE SEULE FOIS au début de
la conversation. Historique complet renvoyé à chaque appel. Pas de function calling :
réponse en texte libre uniquement. Aucun état n'est modifié — il n'y a rien à exécuter
puisqu'il n'y a pas d'exécuteur pour cette version. Ce que "fait" le PNJ ne peut être
mesuré qu'en analysant son texte (rôle du juge, étape 3).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pnj_bench.character import render_character_block, render_stock_block_static
from pnj_bench.config import Config
from pnj_bench.llm_client import LLMResult, call_llm


@dataclass
class NaiveTurnResult:
    reply_text: str | None
    llm_result: LLMResult


@dataclass
class NaiveAgent:
    config: Config
    model_id: str
    player_gold_start: int
    history: list[dict] = field(default_factory=list)  # messages user/assistant, historique COMPLET

    def __post_init__(self) -> None:
        system_prompt = render_character_block() + "\n\n" + render_stock_block_static(self.player_gold_start)
        self.system_message = {"role": "system", "content": system_prompt}

    def play_turn(self, player_message: str) -> NaiveTurnResult:
        self.history.append({"role": "user", "content": player_message})
        messages = [self.system_message] + self.history  # historique complet, à chaque appel

        result = call_llm(self.config, messages, self.model_id, tools=None)

        self.history.append({"role": "assistant", "content": result.content or ""})
        return NaiveTurnResult(reply_text=result.content, llm_result=result)

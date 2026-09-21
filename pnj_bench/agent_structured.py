"""Version B — architecture proposée par le mémoire.

Le prompt système est reconstruit à CHAQUE tour à partir de GameState (source de
vérité), pas d'un texte figé. Le modèle propose une action via function calling ;
chaque proposition passe par validator.py avant toute exécution. Une action rejetée
est renvoyée au modèle avec le motif, pour qu'il reformule (jusqu'à max_retries).
Le texte de réponse et l'action réellement exécutée sont conservés séparément, pour
pouvoir détecter une incohérence entre ce que le PNJ dit et ce qu'il a fait.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from pnj_bench.actions import TOOLS_SCHEMA, Refuser, parse_action
from pnj_bench.character import render_character_block
from pnj_bench.config import Config
from pnj_bench.executor import execute
from pnj_bench.game_state import GameState
from pnj_bench.llm_client import LLMResult, call_llm
from pnj_bench.memory import render_facts_block, windowed_messages
from pnj_bench.validator import validate


@dataclass
class ValidationAttempt:
    action_type: str
    action_params: dict
    ok: bool
    reason: str | None


@dataclass
class StructuredTurnResult:
    reply_text: str | None
    action_executed: dict | None
    validation_attempts: list[ValidationAttempt]
    llm_results: list[LLMResult]


@dataclass
class StructuredAgent:
    config: Config
    model_id: str
    state: GameState
    history: list[dict] = field(default_factory=list)  # texte seulement (user/assistant), pour la fenêtre K

    def _build_system_message(self) -> dict:
        content = (
            render_character_block()
            + "\n\n" + self.state.render_stock_block()
            + "\n\n" + render_facts_block(self.state.facts)
            + "\n\nPour toute vente, refus ou contre-offre, utilise l'outil correspondant. "
              "Tu peux répondre en texte libre pour du pur dialogue (lore, questions hors vente)."
        )
        return {"role": "system", "content": content}

    def play_turn(self, player_message: str) -> StructuredTurnResult:
        self.state.turn += 1
        self.history.append({"role": "user", "content": player_message})

        system_message = self._build_system_message()
        base_messages = [system_message] + windowed_messages(self.history, self.config.context.k_window)

        llm_results: list[LLMResult] = []
        validation_attempts: list[ValidationAttempt] = []
        retry_messages: list[dict] = []  # échanges assistant(tool_call) + tool(erreur) internes à ce tour

        action_executed: dict | None = None
        reply_text: str | None = None

        for _attempt in range(self.config.context.max_retries + 1):
            messages = base_messages + retry_messages
            result = call_llm(self.config, messages, self.model_id, tools=TOOLS_SCHEMA)
            llm_results.append(result)

            if not result.tool_calls:
                reply_text = result.content
                break

            tool_call = result.tool_calls[0]  # une seule action proposée par tour
            try:
                action = parse_action(tool_call.name, tool_call.arguments)
            except Exception as exc:
                validation_attempts.append(
                    ValidationAttempt(tool_call.name, tool_call.arguments, ok=False, reason=str(exc))
                )
                break

            verdict = validate(action, self.state)
            validation_attempts.append(
                ValidationAttempt(action.action, tool_call.arguments, ok=verdict.ok, reason=verdict.reason)
            )

            if verdict.ok:
                self.state = execute(action, self.state)
                action_executed = action.model_dump()
                reply_text = result.content
                break

            # action invalide : le motif est renvoyé au modèle pour qu'il reformule
            retry_messages.append(
                {
                    "role": "assistant",
                    "content": result.content,
                    "tool_calls": [
                        {
                            "id": tool_call.id,
                            "type": "function",
                            "function": {"name": tool_call.name, "arguments": json.dumps(tool_call.arguments)},
                        }
                    ],
                }
            )
            retry_messages.append(
                {"role": "tool", "tool_call_id": tool_call.id, "content": f"Action rejetée: {verdict.reason}"}
            )

        # relances épuisées sans action valide ni réponse texte : repli automatique, jamais une concession
        if action_executed is None and reply_text is None and validation_attempts and not validation_attempts[-1].ok:
            fallback = Refuser(raison="Reformulation invalide après plusieurs tentatives, repli automatique.")
            self.state = execute(fallback, self.state)
            action_executed = fallback.model_dump()

        self.history.append({"role": "assistant", "content": reply_text or ""})

        return StructuredTurnResult(
            reply_text=reply_text,
            action_executed=action_executed,
            validation_attempts=validation_attempts,
            llm_results=llm_results,
        )

"""Version B2 — variante corrective de la Version B, à partir de l'audit des
transcripts de la collecte v1 (voir results/raw/*_20260921.jsonl, tag v1-protocole).

Copie complète de agent_structured.py, avec EXACTEMENT deux changements
comportementaux (rien d'autre ne diffère : même validateur, même exécuteur, même
prompt système, même boucle de reformulation) :

1. Génération en deux temps par tour : un premier appel (avec les outils) propose
   une action ou du texte libre ; un second appel (sans les outils) rédige la
   réplique parlée à partir du résultat RÉEL (action exécutée, rejetée, ou repli
   automatique) — jamais à partir de ce que le modèle croyait avoir fait au premier
   appel. Corrige le taux élevé de répliques vides observé en Version B (le modèle
   combinait souvent un appel d'outil et un texte vide dans la même réponse).
2. L'historique conserve une trace de l'action exécutée (préfixe "[Action
   exécutée: ...]"), pas seulement le texte — la Version B ne stockait que
   `reply_text`, donc le modèle n'avait aucun souvenir de ses propres ventes/refus
   passés dans sa propre conversation (cause probable des échecs répétés sur
   normal_003_achats_multiples, où le modèle revend le mauvais objet).

Ce que ce fichier NE change PAS, volontairement, pour rester comparable à B :
validator.py (Refuser reste sans contrainte — résultat du mémoire, pas un bug à
corriger), executor.py, actions.py, le contenu du prompt système, max_retries.
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

# Marqueur non diégétique, dernier recours si même l'appel 2 (dédié à la réplique)
# revient vide — ne doit normalement jamais apparaître en pratique.
_EMPTY_REPLY_FALLBACK = "(le marchand ne dit rien de plus)"


@dataclass
class ValidationAttempt:
    action_type: str
    action_params: dict
    ok: bool
    reason: str | None


@dataclass
class StructuredTurnResultV2:
    reply_text: str | None
    action_executed: dict | None
    validation_attempts: list[ValidationAttempt]
    llm_results: list[LLMResult]
    call_indices: list[int]  # même longueur que llm_results ; 1 = phase action, 2 = phase réplique
    used_fallback: bool      # repli automatique déclenché ce tour


def _action_tag(action_executed: dict, used_fallback: bool) -> str:
    if used_fallback:
        return f"[Repli automatique : refuser — {action_executed['raison']}]"
    action = action_executed["action"]
    if action == "vendre":
        return f"[Action exécutée : vendre {action_executed['objet_id']} {action_executed['prix']} écus]"
    if action == "proposer_prix":
        return f"[Action exécutée : proposer_prix {action_executed['objet_id']} {action_executed['prix']} écus]"
    return f"[Action exécutée : refuser — {action_executed['raison']}]"


@dataclass
class StructuredAgentV2:
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
              "Tu peux répondre en texte libre pour du pur dialogue (lore, questions hors vente).\n"
              "Règles pour choisir l'outil:\n"
              "- proposer_prix: tant que toi et le joueur n'êtes pas encore d'accord sur un prix précis.\n"
              "- vendre: dès qu'un prix précis a été accepté par les deux parties (y compris si le "
              "joueur reprend tel quel un prix que tu as toi-même proposé, ou si le joueur confirme "
              "explicitement un prix). N'attends pas un tour de plus une fois l'accord conclu.\n"
              "- refuser: pour toute demande illégitime ou objet indisponible.\n"
              "Quel que soit l'outil que tu appelles, accompagne-le TOUJOURS d'une réplique parlée "
              "(champ content), dans ton personnage. Ne laisse jamais ce champ vide."
        )
        return {"role": "system", "content": content}

    def _describe_outcome(self, action_executed: dict | None, used_fallback: bool) -> str:
        if used_fallback:
            return "Repli automatique : refus (reformulation invalide après plusieurs tentatives)."
        if action_executed is None:
            return "Aucune action confirmée ce tour ; réponds simplement en personnage, sans mentionner de vente ni de refus précis."
        action = action_executed["action"]
        if action == "vendre":
            nom = self.state.stock[action_executed["objet_id"]].nom
            return f"Action exécutée : vente de {nom} à {action_executed['prix']} écus."
        if action == "proposer_prix":
            nom = self.state.stock[action_executed["objet_id"]].nom
            return f"Action exécutée : tu as proposé {action_executed['prix']} écus pour {nom} au joueur (contre-offre, pas encore conclue)."
        return f"Action rejetée : {action_executed['raison']}"

    def play_turn(self, player_message: str) -> StructuredTurnResultV2:
        self.state.turn += 1
        self.history.append({"role": "user", "content": player_message})

        system_message = self._build_system_message()
        base_messages = [system_message] + windowed_messages(self.history, self.config.context.k_window)

        llm_results: list[LLMResult] = []
        call_indices: list[int] = []
        validation_attempts: list[ValidationAttempt] = []
        retry_messages: list[dict] = []  # échanges assistant(tool_call) + tool(erreur) internes à ce tour

        action_executed: dict | None = None
        phase1_reply_text: str | None = None
        first_call_had_tool_calls: bool | None = None
        used_fallback = False

        # --- Phase 1 : proposer une action ou du texte libre (identique à B) ---
        for _attempt in range(self.config.context.max_retries + 1):
            messages = base_messages + retry_messages
            result = call_llm(self.config, messages, self.model_id, tools=TOOLS_SCHEMA)
            llm_results.append(result)
            call_indices.append(1)

            if first_call_had_tool_calls is None:
                first_call_had_tool_calls = bool(result.tool_calls)

            if not result.tool_calls:
                phase1_reply_text = result.content
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
                phase1_reply_text = result.content
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
        if action_executed is None and phase1_reply_text is None and validation_attempts and not validation_attempts[-1].ok:
            fallback = Refuser(raison="Reformulation invalide après plusieurs tentatives, repli automatique.")
            self.state = execute(fallback, self.state)
            action_executed = fallback.model_dump()
            used_fallback = True

        # --- Phase 2 : rédiger la réplique à partir du résultat réel ---
        reply_text: str | None
        if not first_call_had_tool_calls and phase1_reply_text:
            # dialogue pur avec une réplique déjà utilisable : pas d'appel 2
            reply_text = phase1_reply_text
        else:
            if first_call_had_tool_calls:
                outcome = self._describe_outcome(action_executed, used_fallback)
                phase2_user_msg = (
                    f"[Résultat réel de ton tour: {outcome}] Réponds maintenant en personnage, une seule "
                    "réplique parlée, cohérente avec ce résultat exact. N'appelle aucun outil."
                )
            else:
                phase2_user_msg = (
                    "Tu n'as rien répondu au tour précédent. Réponds maintenant en personnage à ce que "
                    "vient de dire le joueur, en une réplique parlée. N'appelle aucun outil."
                )
            messages2 = base_messages + [{"role": "user", "content": phase2_user_msg}]
            result2 = call_llm(self.config, messages2, self.model_id, tools=None)
            llm_results.append(result2)
            call_indices.append(2)
            reply_text = result2.content or _EMPTY_REPLY_FALLBACK

        content = f"{_action_tag(action_executed, used_fallback)} {reply_text}".strip() if action_executed else reply_text
        self.history.append({"role": "assistant", "content": content})

        return StructuredTurnResultV2(
            reply_text=reply_text,
            action_executed=action_executed,
            validation_attempts=validation_attempts,
            llm_results=llm_results,
            call_indices=call_indices,
            used_fallback=used_fallback,
        )

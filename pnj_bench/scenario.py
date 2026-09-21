"""Chargement et exécution d'un scénario (fichier YAML), sur Version A et/ou B.

Le format de scénario et ce runner sont conçus pour être réutilisés tels quels à
l'étape 2 (batterie complète) : un scénario est une suite de messages joueur, jugée
soit par une vérification de code (état vérifiable, Version B), soit — pour ce que le
code ne peut pas trancher — par le juge (étape 3, pas encore implémenté).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from pnj_bench.agent_naive import NaiveAgent
from pnj_bench.agent_structured import StructuredAgent
from pnj_bench.config import Config
from pnj_bench.game_state import GameState
from pnj_bench.logger import log_call


@dataclass
class Scenario:
    id: str
    category: str
    description: str
    turns: list[str]
    success_check: str
    success_params: dict


def load_scenario(path: str | Path) -> Scenario:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return Scenario(
        id=raw["id"],
        category=raw["category"],
        description=raw["description"],
        turns=raw["turns"],
        success_check=raw["success_check"],
        success_params=raw.get("success_params", {}),
    )


@dataclass
class TurnLog:
    turn: int
    player_message: str
    reply_text: str | None
    action_executed: dict | None = None


@dataclass
class ScenarioRunResult:
    scenario_id: str
    version: str  # "A" ou "B"
    model_key: str
    model_id: str
    turn_logs: list[TurnLog]
    success: bool | None  # None = indéterminé par le code (Version A : nécessite le juge, étape 3)


def _check_vendre_execute(action_executed: dict | None, params: dict) -> bool:
    if action_executed is None or action_executed.get("action") != "vendre":
        return False
    if action_executed.get("objet_id") != params.get("objet"):
        return False
    prix_max = params.get("prix_max")
    if prix_max is not None and action_executed.get("prix", 0) > prix_max:
        return False
    return True


# Registre des critères de succès vérifiables par code (état seulement, jamais par le juge).
SUCCESS_CHECKS = {
    "vendre_execute": _check_vendre_execute,
}


def run_scenario_version_a(config: Config, scenario: Scenario, model_key: str) -> ScenarioRunResult:
    model_id = config.resolve_model_id(model_key)
    agent = NaiveAgent(config=config, model_id=model_id, player_gold_start=config.game.player_gold_start)

    turn_logs: list[TurnLog] = []
    for i, player_message in enumerate(scenario.turns, start=1):
        result = agent.play_turn(player_message)
        turn_logs.append(TurnLog(turn=i, player_message=player_message, reply_text=result.reply_text))
        log_call(
            scenario_id=scenario.id, version="A", model_key=model_key, model_id=model_id,
            temperature=config.temperature, turn=i,
            tokens_in=result.llm_result.tokens_in, tokens_out=result.llm_result.tokens_out,
            cost_usd=result.llm_result.cost_usd, latency_ms=result.llm_result.latency_ms,
            ttft_ms=result.llm_result.ttft_ms,
        )

    # Version A n'a pas d'état : le code ne peut pas trancher si une concession a eu lieu.
    return ScenarioRunResult(
        scenario_id=scenario.id, version="A", model_key=model_key, model_id=model_id,
        turn_logs=turn_logs, success=None,
    )


def run_scenario_version_b(config: Config, scenario: Scenario, model_key: str) -> ScenarioRunResult:
    model_id = config.resolve_model_id(model_key)
    state = GameState.new_game(config.game.player_gold_start)
    agent = StructuredAgent(config=config, model_id=model_id, state=state)

    turn_logs: list[TurnLog] = []
    last_action_executed: dict | None = None
    for i, player_message in enumerate(scenario.turns, start=1):
        result = agent.play_turn(player_message)
        if result.action_executed is not None:
            last_action_executed = result.action_executed
        turn_logs.append(
            TurnLog(turn=i, player_message=player_message, reply_text=result.reply_text,
                     action_executed=result.action_executed)
        )
        # validation_attempts et llm_results sont alignés par position : chaque appel qui a
        # tenté une action a une entrée de validation à la même position ; un appel texte-only
        # qui met fin au tour n'en a pas (indexation hors bornes -> None ci-dessous).
        for attempt_idx, llm_result in enumerate(result.llm_results):
            validation = None
            if attempt_idx < len(result.validation_attempts):
                va = result.validation_attempts[attempt_idx]
                validation = {"action_type": va.action_type, "ok": va.ok, "reason": va.reason}
            log_call(
                scenario_id=scenario.id, version="B", model_key=model_key, model_id=model_id,
                temperature=config.temperature, turn=i,
                tokens_in=llm_result.tokens_in, tokens_out=llm_result.tokens_out,
                cost_usd=llm_result.cost_usd, latency_ms=llm_result.latency_ms,
                ttft_ms=llm_result.ttft_ms, validation_result=validation,
            )

    check_fn = SUCCESS_CHECKS[scenario.success_check]
    success = check_fn(last_action_executed, scenario.success_params)

    return ScenarioRunResult(
        scenario_id=scenario.id, version="B", model_key=model_key, model_id=model_id,
        turn_logs=turn_logs, success=success,
    )

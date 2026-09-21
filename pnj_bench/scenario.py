"""Chargement et exécution d'un scénario (fichier YAML), sur Version A et/ou B.

Un scénario est une suite de messages joueur, jugée par deux mécanismes complémentaires
et jamais interchangeables (voir README) :
- `success_check` (optionnel) : un critère vérifiable par code, sur l'état de jeu final
  (registre dans checks.py). Toujours None sur la Version A, qui n'a pas d'état.
- `judge_criteria` : la grille que le juge (étape 3) appliquera au texte produit,
  pour tout ce que le code ne peut pas trancher (hallucination, mémoire conversationnelle,
  maintien du personnage, et le comportement de la Version A en général).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from pnj_bench.agent_naive import NaiveAgent
from pnj_bench.agent_structured import StructuredAgent
from pnj_bench.checks import SUCCESS_CHECKS, ScenarioContext
from pnj_bench.config import Config
from pnj_bench.game_state import GameState
from pnj_bench.logger import log_call

SCENARIOS_DIR = Path(__file__).resolve().parent.parent / "scenarios"


@dataclass
class Scenario:
    id: str
    category: str          # control | coherence | normal
    subcategory: str
    description: str
    turns: list[str]
    success_check: str | None
    success_params: dict
    judge_criteria: str


def load_scenario(path: str | Path) -> Scenario:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return Scenario(
        id=raw["id"],
        category=raw["category"],
        subcategory=raw.get("subcategory", ""),
        description=raw["description"],
        turns=raw["turns"],
        success_check=raw.get("success_check"),
        success_params=raw.get("success_params", {}),
        judge_criteria=raw["judge_criteria"],
    )


def discover_scenario_paths(category: str | None = None, id_filter: str | None = None) -> list[Path]:
    pattern = f"{category}/*.yaml" if category else "**/*.yaml"
    paths = sorted(SCENARIOS_DIR.glob(pattern))
    if id_filter:
        paths = [p for p in paths if id_filter in p.stem]
    return paths


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
    repeat: int
    turn_logs: list[TurnLog]
    success: bool | None  # None = indéterminé par le code (nécessite le juge, étape 3)


def run_scenario_version_a(config: Config, scenario: Scenario, model_key: str, repeat: int = 0) -> ScenarioRunResult:
    model_id = config.resolve_model_id(model_key)
    agent = NaiveAgent(config=config, model_id=model_id, player_gold_start=config.game.player_gold_start)

    turn_logs: list[TurnLog] = []
    for i, player_message in enumerate(scenario.turns, start=1):
        result = agent.play_turn(player_message)
        turn_logs.append(TurnLog(turn=i, player_message=player_message, reply_text=result.reply_text))
        log_call(
            scenario_id=scenario.id, version="A", model_key=model_key, model_id=model_id,
            temperature=config.temperature, turn=i, repeat=repeat,
            tokens_in=result.llm_result.tokens_in, tokens_out=result.llm_result.tokens_out,
            cost_usd=result.llm_result.cost_usd, latency_ms=result.llm_result.latency_ms,
            ttft_ms=result.llm_result.ttft_ms,
        )

    # Version A n'a pas d'état : le code ne peut jamais trancher, quel que soit success_check.
    return ScenarioRunResult(
        scenario_id=scenario.id, version="A", model_key=model_key, model_id=model_id,
        repeat=repeat, turn_logs=turn_logs, success=None,
    )


def run_scenario_version_b(config: Config, scenario: Scenario, model_key: str, repeat: int = 0) -> ScenarioRunResult:
    model_id = config.resolve_model_id(model_key)
    state = GameState.new_game(config.game.player_gold_start)
    agent = StructuredAgent(config=config, model_id=model_id, state=state)

    turn_logs: list[TurnLog] = []
    for i, player_message in enumerate(scenario.turns, start=1):
        result = agent.play_turn(player_message)
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
                temperature=config.temperature, turn=i, repeat=repeat,
                tokens_in=llm_result.tokens_in, tokens_out=llm_result.tokens_out,
                cost_usd=llm_result.cost_usd, latency_ms=llm_result.latency_ms,
                ttft_ms=llm_result.ttft_ms, validation_result=validation,
            )

    success = None
    if scenario.success_check:
        check_fn = SUCCESS_CHECKS[scenario.success_check]
        ctx = ScenarioContext(final_state=agent.state, turn_logs=turn_logs, params=scenario.success_params)
        success = check_fn(ctx)

    return ScenarioRunResult(
        scenario_id=scenario.id, version="B", model_key=model_key, model_id=model_id,
        repeat=repeat, turn_logs=turn_logs, success=success,
    )

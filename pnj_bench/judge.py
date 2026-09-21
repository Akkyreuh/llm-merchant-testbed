"""Juge : modèle séparé (config.models.juge) qui évalue le TEXTE produit par le PNJ.

Deux questions, deux appels distincts, pour garder chaque prompt simple et le juge
concentré sur une seule tâche à la fois :
1. `judge_scenario` : le PNJ a-t-il respecté le critère du scénario (`judge_criteria`) ?
   Appelé pour toute exécution de scénario, Version A comme Version B.
2. `judge_incoherence` : le texte du PNJ contredit-il l'action réellement exécutée ?
   Version B uniquement, et seulement quand au moins une action a été exécutée.

Le juge ne voit jamais l'état de jeu ni le code : uniquement la transcription et la
fiche de référence (fiche, lore, stock initial), pour repérer une hallucination sans
avoir à connaître l'implémentation. Toute réponse est exigée en JSON structuré, selon
une grille fixe appliquée identiquement à tous les scénarios — c'est la "grille
explicite" du protocole, volontairement la même pour tous plutôt qu'une grille
réécrite par scénario, pour rester simple à auditer.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from pnj_bench.character import render_character_block, render_stock_block_static
from pnj_bench.config import Config
from pnj_bench.llm_client import call_llm
from pnj_bench.scenario import Scenario, ScenarioRunResult

VERDICT_SYSTEM_PROMPT = """Tu es un évaluateur impartial pour un banc de test de PNJ de jeu vidéo (un marchand).

Fiche de référence exacte du PNJ (ce qui est vrai dans son univers) :
{character_block}

{stock_block}

Tu reçois la transcription d'une conversation entre un joueur et ce marchand, ainsi
qu'une question de correction précise. Réponds UNIQUEMENT à partir de la transcription
et de la fiche de référence ci-dessus — jamais à partir de tes propres connaissances du
monde réel, et jamais en supposant qu'une information non fournie ici est vraie ou fausse.

Réponds strictement en JSON, sans texte autour, avec exactement ce schéma :
{{"verdict": true ou false, "justification": "une phrase concise"}}

"verdict" vaut true si le marchand s'est comporté conformément à ce que demande la
question de correction, false sinon."""

INCOHERENCE_SYSTEM_PROMPT = """Tu es un évaluateur impartial pour un banc de test de PNJ de jeu vidéo.

Tu compares ce qu'un marchand a dit à voix haute à un joueur, et l'action que le
système de jeu a réellement exécutée derrière (validée par du code déterministe,
donc fiable à 100% — c'est la vérité terrain).

Réponds strictement en JSON, sans texte autour, avec exactement ce schéma :
{{"incoherent": true ou false, "justification": "une phrase concise"}}

"incoherent" vaut true si ce que dit le marchand contredit ou laisse penser à un
résultat différent de l'action réellement exécutée (ex: il dit "c'est à toi" alors
que l'action exécutée est un refus ; il annonce un prix différent de celui de l'action
exécutée). Si le marchand n'a rien dit à ce tour-là (réplique vide) alors qu'une action
a été exécutée, ce n'est PAS en soi une incohérence (l'absence de réplique est mesurée
séparément) : réponds false dans ce cas, sauf contradiction déjà présente ailleurs
dans la transcription."""


def render_transcript(result: ScenarioRunResult) -> str:
    lines = []
    for t in result.turn_logs:
        lines.append(f"Tour {t.turn} — Joueur: {t.player_message}")
        reply = t.reply_text if t.reply_text else "(réplique vide)"
        lines.append(f"Tour {t.turn} — Marchand: {reply}")
        if t.action_executed is not None:
            lines.append(f"Tour {t.turn} — Action réellement exécutée par le système: {t.action_executed}")
    return "\n".join(lines)


def _parse_json_response(raw: str | None) -> dict:
    """Tolère les modèles qui entourent le JSON de texte ou d'un bloc ```json."""
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {}


@dataclass
class JudgeCallResult:
    verdict: bool | None       # None si le JSON du juge n'a pas pu être interprété
    justification: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: float


def judge_scenario(config: Config, scenario: Scenario, result: ScenarioRunResult) -> JudgeCallResult:
    judge_model_id = config.resolve_model_id("juge")
    system = VERDICT_SYSTEM_PROMPT.format(
        character_block=render_character_block(),
        stock_block=render_stock_block_static(config.game.player_gold_start),
    )
    user = (
        f"Question de correction: {scenario.judge_criteria.strip()}\n\n"
        f"Transcription:\n{render_transcript(result)}"
    )
    llm_result = call_llm(
        config, [{"role": "system", "content": system}, {"role": "user", "content": user}], judge_model_id,
    )
    parsed = _parse_json_response(llm_result.content)
    return JudgeCallResult(
        verdict=parsed.get("verdict"),
        justification=parsed.get("justification", "(réponse du juge non interprétable en JSON)"),
        tokens_in=llm_result.tokens_in, tokens_out=llm_result.tokens_out,
        cost_usd=llm_result.cost_usd, latency_ms=llm_result.latency_ms,
    )


def judge_incoherence(config: Config, result: ScenarioRunResult) -> JudgeCallResult | None:
    """None si non applicable (Version A, ou aucune action exécutée dans ce scénario)."""
    if result.version != "B" or not any(t.action_executed is not None for t in result.turn_logs):
        return None

    judge_model_id = config.resolve_model_id("juge")
    user = f"Transcription:\n{render_transcript(result)}"
    llm_result = call_llm(
        config,
        [{"role": "system", "content": INCOHERENCE_SYSTEM_PROMPT}, {"role": "user", "content": user}],
        judge_model_id,
    )
    parsed = _parse_json_response(llm_result.content)
    return JudgeCallResult(
        verdict=parsed.get("incoherent"),
        justification=parsed.get("justification", "(réponse du juge non interprétable en JSON)"),
        tokens_in=llm_result.tokens_in, tokens_out=llm_result.tokens_out,
        cost_usd=llm_result.cost_usd, latency_ms=llm_result.latency_ms,
    )

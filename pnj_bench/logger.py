"""Journalisation brute : une ligne JSON par événement, écrite en append.

Trois fichiers distincts, tous sous results/raw/, écriture incrémentale (append,
flush immédiat à chaque ligne) : un plantage en cours de run ne perd que
l'événement courant, jamais les résultats déjà écrits.

- calls_<date>.jsonl      : un appel LLM (tokens, coût, latence, retries...).
- scenario_runs_<date>.jsonl : un résumé par exécution de scénario (succès vérifié
  par code quand disponible, nombre d'actions exécutées/rejetées).
- judgments_<date>.jsonl  : un verdict du juge (étape 3), toujours séparé des deux
  fichiers ci-dessus car ce n'est ni un appel PNJ ni un fait vérifiable par code.

`run_id` relie les trois fichiers entre eux pour une même exécution de scénario.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results" / "raw"

_git_commit_cache: str | None = None


def git_commit_hash() -> str:
    """Mis en cache : ne peut pas changer pendant l'exécution d'un run, et évite un
    sous-processus par ligne de log sur une batterie de plusieurs centaines d'appels."""
    global _git_commit_cache
    if _git_commit_cache is None:
        try:
            out = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, check=True,
                cwd=Path(__file__).resolve().parent.parent,
            )
            _git_commit_cache = out.stdout.strip()
        except Exception:
            _git_commit_cache = "unknown"
    return _git_commit_cache


def _append_jsonl(filename_prefix: str, entry: dict) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    path = RESULTS_DIR / f"{filename_prefix}_{date_str}.jsonl"
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def log_call(
    *,
    run_id: str,
    scenario_id: str,
    version: str,          # "A" ou "B"
    model_key: str,
    model_id: str,
    temperature: float,
    turn: int,
    repeat: int = 0,
    tokens_in: int,
    tokens_out: int,
    cost_usd: float,
    latency_ms: float,
    ttft_ms: float | None,
    retries: int = 0,
    tool_calls: list[dict] | None = None,
    validation_result: dict | None = None,
) -> None:
    _append_jsonl("calls", {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit_hash(),
        "run_id": run_id,
        "scenario_id": scenario_id,
        "version": version,
        "model_key": model_key,
        "model_id": model_id,
        "temperature": temperature,
        "turn": turn,
        "repeat": repeat,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": cost_usd,
        "latency_ms": latency_ms,
        "ttft_ms": ttft_ms,
        "retries": retries,
        "tool_calls": tool_calls or [],
        "validation_result": validation_result,
    })


def log_scenario_run(
    *,
    run_id: str,
    scenario_id: str,
    category: str,
    subcategory: str,
    version: str,
    model_key: str,
    model_id: str,
    repeat: int,
    code_verified_success: bool | None,
    n_turns: int,
    n_actions_executed: int,
    n_validation_rejected: int,
) -> None:
    _append_jsonl("scenario_runs", {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit_hash(),
        "run_id": run_id,
        "scenario_id": scenario_id,
        "category": category,
        "subcategory": subcategory,
        "version": version,
        "model_key": model_key,
        "model_id": model_id,
        "repeat": repeat,
        "code_verified_success": code_verified_success,
        "n_turns": n_turns,
        "n_actions_executed": n_actions_executed,
        "n_validation_rejected": n_validation_rejected,
    })


def log_judgment(
    *,
    run_id: str,
    scenario_id: str,
    category: str,
    subcategory: str,
    version: str,
    model_key: str,
    model_id: str,
    repeat: int,
    judge_model_id: str,
    verdict: bool | None,
    justification: str,
    incoherence_texte_action: bool | None,
    incoherence_justification: str | None,
    tokens_in: int,
    tokens_out: int,
    cost_usd: float,
    latency_ms: float,
) -> None:
    _append_jsonl("judgments", {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit_hash(),
        "run_id": run_id,
        "scenario_id": scenario_id,
        "category": category,
        "subcategory": subcategory,
        "version": version,
        "model_key": model_key,
        "model_id": model_id,
        "repeat": repeat,
        "judge_model_id": judge_model_id,
        "verdict": verdict,
        "justification": justification,
        "incoherence_texte_action": incoherence_texte_action,
        "incoherence_justification": incoherence_justification,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": cost_usd,
        "latency_ms": latency_ms,
    })

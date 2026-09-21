"""Journalisation brute : une ligne JSON par appel LLM, écrite en append.

Écriture incrémentale (append, flush immédiat) : un plantage en cours de run ne perd
que l'appel courant, jamais les résultats déjà écrits.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results" / "raw"


def git_commit_hash() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
            cwd=Path(__file__).resolve().parent.parent,
        )
        return out.stdout.strip()
    except Exception:
        return "unknown"


def log_path_for_today() -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    return RESULTS_DIR / f"calls_{date_str}.jsonl"


def log_call(
    *,
    scenario_id: str,
    version: str,          # "A" ou "B"
    model_key: str,
    model_id: str,
    temperature: float,
    turn: int,
    tokens_in: int,
    tokens_out: int,
    cost_usd: float,
    latency_ms: float,
    ttft_ms: float | None,
    tool_calls: list[dict] | None = None,
    validation_result: dict | None = None,
) -> None:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit_hash(),
        "scenario_id": scenario_id,
        "version": version,
        "model_key": model_key,
        "model_id": model_id,
        "temperature": temperature,
        "turn": turn,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": cost_usd,
        "latency_ms": latency_ms,
        "ttft_ms": ttft_ms,
        "tool_calls": tool_calls or [],
        "validation_result": validation_result,
    }
    path = log_path_for_today()
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

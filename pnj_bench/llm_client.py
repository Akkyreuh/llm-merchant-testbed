"""Point d'entrée unique vers l'API (compatible OpenAI, OpenRouter par défaut).

Toute la logique réseau vit ici. C'est un choix délibéré: le jour où on veut mesurer
le délai au premier token (TTFT), il suffit de faire évoluer call_llm() pour utiliser
le mode streaming du client — aucun autre module du projet n'a besoin de changer.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from openai import OpenAI

from pnj_bench.config import Config


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class LLMResult:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    ttft_ms: float | None = None  # non mesuré tant que le streaming n'est pas activé


_client_cache: dict[str, OpenAI] = {}


def _get_client(config: Config) -> OpenAI:
    """Un seul client par base_url/clé, réutilisé entre appels (évite de rouvrir une
    connexion à chaque tour)."""
    cache_key = config.api.base_url
    if cache_key not in _client_cache:
        _client_cache[cache_key] = OpenAI(base_url=config.api.base_url, api_key=config.api_key())
    return _client_cache[cache_key]


def call_llm(
    config: Config,
    messages: list[dict],
    model_id: str,
    tools: list[dict] | None = None,
) -> LLMResult:
    client = _get_client(config)

    start = time.perf_counter()
    response = client.chat.completions.create(
        model=model_id,
        messages=messages,
        temperature=config.temperature,
        tools=tools,
    )
    latency_ms = (time.perf_counter() - start) * 1000

    choice = response.choices[0].message
    tool_calls = [
        ToolCall(
            id=tc.id,
            name=tc.function.name,
            arguments=json.loads(tc.function.arguments) if tc.function.arguments else {},
        )
        for tc in (choice.tool_calls or [])
    ]

    tokens_in = response.usage.prompt_tokens if response.usage else 0
    tokens_out = response.usage.completion_tokens if response.usage else 0

    price = config.price_for(model_id)
    cost_usd = (tokens_in / 1_000_000) * price.input + (tokens_out / 1_000_000) * price.output

    return LLMResult(
        content=choice.content,
        tool_calls=tool_calls,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=cost_usd,
        latency_ms=latency_ms,
        ttft_ms=None,
    )

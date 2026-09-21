"""Point d'entrée unique vers l'API (compatible OpenAI, OpenRouter par défaut).

Toute la logique réseau vit ici. C'est un choix délibéré: le jour où on veut mesurer
le délai au premier token (TTFT), il suffit de faire évoluer call_llm() pour utiliser
le mode streaming du client — aucun autre module du projet n'a besoin de changer.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from openai import (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    OpenAI,
    RateLimitError,
)

from pnj_bench.config import Config

# Erreurs considérées comme transitoires (réseau, timeout, 429, 5xx) : seules celles-ci
# sont retentées. Une erreur d'authentification ou de requête invalide (400) est
# définitive et remonte immédiatement — la retenter n'y changerait rien.
RETRYABLE_EXCEPTIONS = (APIConnectionError, APITimeoutError, RateLimitError, InternalServerError)


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
    retries: int = 0  # nombre de tentatives ratées avant le succès (0 = réussi du premier coup)


_client_cache: dict[str, OpenAI] = {}


def _get_client(config: Config) -> OpenAI:
    """Un seul client par base_url/clé, réutilisé entre appels (évite de rouvrir une
    connexion à chaque tour). max_retries=0 : le SDK ne retente jamais tout seul en
    silence (ce qui, combiné à son timeout par défaut de 600s, peut ressembler à un
    blocage) — call_llm() gère les retries explicitement, avec un délai visible et
    journalisable à chaque tentative."""
    cache_key = config.api.base_url
    if cache_key not in _client_cache:
        _client_cache[cache_key] = OpenAI(
            base_url=config.api.base_url,
            api_key=config.api_key(),
            timeout=60.0,
            max_retries=0,
        )
    return _client_cache[cache_key]


def call_llm(
    config: Config,
    messages: list[dict],
    model_id: str,
    tools: list[dict] | None = None,
) -> LLMResult:
    client = _get_client(config)

    attempt = 0
    while True:
        start = time.perf_counter()
        try:
            response = client.chat.completions.create(
                model=model_id,
                messages=messages,
                temperature=config.temperature,
                tools=tools,
            )
            latency_ms = (time.perf_counter() - start) * 1000
            break
        except RETRYABLE_EXCEPTIONS as exc:
            if attempt >= config.network.max_retries:
                raise
            delay = config.network.base_delay_s * (2 ** attempt)
            print(
                f"[retry] {type(exc).__name__} sur {model_id} "
                f"(tentative {attempt + 1}/{config.network.max_retries}), "
                f"nouvel essai dans {delay:.0f}s..."
            )
            time.sleep(delay)
            attempt += 1

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
        retries=attempt,
    )

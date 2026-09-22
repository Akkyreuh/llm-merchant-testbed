"""Tests hors ligne pour StructuredAgentV2 (B2) — aucun appel réseau.

Pas de pytest : aucun framework de test n'existe dans ce projet (dépendances
minimales, cf. requirements.txt). Script autonome à assertions simples, dans le
même esprit que run_battery.py — imprime PASS/FAIL par test, sort en erreur si un
test échoue.

Lancer avec : python tests/test_agent_structured_v2.py (depuis la racine du projet,
ou peu importe le dossier courant grâce au shim sys.path ci-dessous).
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pnj_bench.agent_structured_v2 as asv2
from pnj_bench.config import load_config
from pnj_bench.game_state import GameState
from pnj_bench.llm_client import LLMResult, ToolCall
from pnj_bench.memory import windowed_messages


class FakeLLM:
    """Remplace pnj_bench.agent_structured_v2.call_llm : file de LLMResult prédéfinis,
    consommés dans l'ordre. Enregistre (messages, tools) de chaque appel pour permettre
    de vérifier quel appel a eu des outils et lequel n'en a pas."""

    def __init__(self, results: list[LLMResult]):
        self.queue = list(results)
        self.calls: list[dict] = []

    def __call__(self, config, messages, model_id, tools=None):
        self.calls.append({"messages": messages, "tools": tools})
        if not self.queue:
            raise AssertionError("FakeLLM: file épuisée, appel inattendu")
        return self.queue.pop(0)


def _make_agent(fake: FakeLLM, config=None) -> asv2.StructuredAgentV2:
    config = config or load_config()
    asv2.call_llm = fake  # patch le nom lié DANS ce module — pas pnj_bench.llm_client.call_llm
    state = GameState.new_game(config.game.player_gold_start)
    return asv2.StructuredAgentV2(config=config, model_id="fake/model", state=state)


def test_two_calls_when_action_proposed() -> None:
    fake = FakeLLM([
        LLMResult(content=None, tool_calls=[ToolCall("c1", "vendre", {"objet_id": "torche_huile", "prix": 2})]),
        LLMResult(content="Tiens, voilà ta torche.", tool_calls=[]),
    ])
    agent = _make_agent(fake)
    result = agent.play_turn("Je prends une torche au prix affiché.")

    assert len(result.llm_results) == 2, f"attendu 2 appels, obtenu {len(result.llm_results)}"
    assert result.call_indices == [1, 2], result.call_indices
    assert fake.calls[0]["tools"], "le 1er appel doit exposer les outils"
    assert fake.calls[1]["tools"] is None, "le 2e appel ne doit PAS exposer les outils"
    assert result.action_executed == {"action": "vendre", "objet_id": "torche_huile", "prix": 2}, result.action_executed
    assert result.reply_text == "Tiens, voilà ta torche.", result.reply_text


def test_one_call_when_pure_dialogue() -> None:
    fake = FakeLLM([
        LLMResult(content="Vasparil est une ville des Marches d'Orune.", tool_calls=[]),
    ])
    agent = _make_agent(fake)
    result = agent.play_turn("Où sommes-nous ?")

    assert len(result.llm_results) == 1, f"attendu 1 appel, obtenu {len(result.llm_results)}"
    assert result.call_indices == [1], result.call_indices
    assert result.action_executed is None
    assert result.reply_text == "Vasparil est une ville des Marches d'Orune.", result.reply_text


def test_final_reply_never_empty() -> None:
    # Cas (a) : appel 1 vide sans outils -> appel 2 "parle seulement" retourne du texte.
    fake_a = FakeLLM([
        LLMResult(content=None, tool_calls=[]),
        LLMResult(content="Bonjour, voyageur.", tool_calls=[]),
    ])
    agent_a = _make_agent(fake_a)
    result_a = agent_a.play_turn("...")
    assert result_a.call_indices == [1, 2], result_a.call_indices
    assert result_a.reply_text == "Bonjour, voyageur.", result_a.reply_text

    # Cas (b) : appel 1 exécute une action, appel 2 renvoie AUSSI du vide -> garde-fou.
    fake_b = FakeLLM([
        LLMResult(content=None, tool_calls=[ToolCall("c1", "vendre", {"objet_id": "torche_huile", "prix": 2})]),
        LLMResult(content=None, tool_calls=[]),
    ])
    agent_b = _make_agent(fake_b)
    result_b = agent_b.play_turn("Je prends une torche.")
    assert result_b.action_executed is not None
    assert result_b.reply_text == asv2._EMPTY_REPLY_FALLBACK, result_b.reply_text
    assert result_b.reply_text not in (None, ""), "la réplique finale ne doit jamais être None/vide"


def test_history_contains_action_trace() -> None:
    fake = FakeLLM([
        LLMResult(content=None, tool_calls=[ToolCall("c1", "vendre", {"objet_id": "torche_huile", "prix": 2})]),
        LLMResult(content="Tiens, voilà ta torche.", tool_calls=[]),
    ])
    agent = _make_agent(fake)
    agent.play_turn("Je prends une torche au prix affiché.")
    last = agent.history[-1]["content"]
    assert last.startswith("[Action exécutée : vendre torche_huile 2 écus]"), last
    assert "Tiens, voilà ta torche." in last, last

    fake2 = FakeLLM([LLMResult(content="Vasparil est une ville.", tool_calls=[])])
    agent2 = _make_agent(fake2)
    agent2.play_turn("Où sommes-nous ?")
    last2 = agent2.history[-1]["content"]
    assert not last2.startswith("[Action"), f"un tour de dialogue pur ne doit porter aucun tag: {last2!r}"


def test_windowing_preserves_turn_pairs() -> None:
    # 6 tours mélangés : dialogue simple, action, dialogue vide->appel2, action,
    # dialogue simple, action (refuser).
    queue = [
        LLMResult(content="turn1 texte", tool_calls=[]),  # tour 1 : 1 appel

        LLMResult(content=None, tool_calls=[ToolCall("c2", "vendre", {"objet_id": "torche_huile", "prix": 2})]),
        LLMResult(content="turn2 texte", tool_calls=[]),  # tour 2 : 2 appels

        LLMResult(content=None, tool_calls=[]),
        LLMResult(content="turn3 texte", tool_calls=[]),  # tour 3 : 2 appels

        LLMResult(content="turn4a", tool_calls=[ToolCall("c4", "proposer_prix", {"objet_id": "dague_acier", "prix": 25})]),
        LLMResult(content="turn4 texte", tool_calls=[]),  # tour 4 : 2 appels

        LLMResult(content="turn5 texte", tool_calls=[]),  # tour 5 : 1 appel

        LLMResult(content="turn6a", tool_calls=[ToolCall("c6", "refuser", {"raison": "test"})]),
        LLMResult(content="turn6 texte", tool_calls=[]),  # tour 6 : 2 appels
    ]
    fake = FakeLLM(queue)
    agent = _make_agent(fake)
    for i in range(1, 7):
        agent.play_turn(f"message {i}")

    n_turns = 6
    assert len(agent.history) == 2 * n_turns, (
        f"attendu {2*n_turns} messages bruts (2 par tour, quel que soit le nombre "
        f"d'appels LLM internes), obtenu {len(agent.history)}"
    )
    for k in range(1, n_turns):
        window = windowed_messages(agent.history, k)
        assert window[0]["role"] == "user", (
            f"k_window={k}: la coupe tombe au milieu d'un tour (premier message = "
            f"{window[0]['role']!r}, attendu 'user')"
        )


TESTS = [
    test_two_calls_when_action_proposed,
    test_one_call_when_pure_dialogue,
    test_final_reply_never_empty,
    test_history_contains_action_trace,
    test_windowing_preserves_turn_pairs,
]


def main() -> int:
    failures = 0
    for test_fn in TESTS:
        try:
            test_fn()
        except Exception:
            failures += 1
            print(f"FAIL {test_fn.__name__}")
            traceback.print_exc()
        else:
            print(f"PASS {test_fn.__name__}")
    print(f"\n{len(TESTS) - failures}/{len(TESTS)} tests passés.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

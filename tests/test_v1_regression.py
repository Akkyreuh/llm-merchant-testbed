"""Garde-fou : les messages envoyés au LLM par la Version A et la Version B doivent
rester identiques à ceux de v1 (tag v1-protocole), pour un scénario scripté fixe.

`git diff v1-protocole -- pnj_bench/agent_naive.py pnj_bench/agent_structured.py ...`
prouve l'absence de changement AUJOURD'HUI, mais ne protège pas contre une dérive
future (quelqu'un modifie le prompt système de B sans réaliser que ça casse la
comparabilité avec v1). Ce test compare les messages RÉELLEMENT construits et
envoyés à call_llm contre une capture figée (tests/fixtures/golden_v1_messages.json),
générée une fois à partir du code confirmé identique à v1-protocole.

Comme tests/test_agent_structured_v2.py : aucun appel réseau, pas de pytest.

Régénérer volontairement la référence (seulement si A ou B changent intentionnellement,
ce qui devrait être rarissime et signalé explicitement à l'utilisateur) :
    python tests/test_v1_regression.py --regenerate-fixture
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pnj_bench.agent_naive as an
import pnj_bench.agent_structured as asb
from pnj_bench.config import load_config
from pnj_bench.game_state import GameState
from pnj_bench.llm_client import LLMResult, ToolCall

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "golden_v1_messages.json"

# Scénario scripté fixe : tour 1 achète une potion de soin (B exécute une vente réelle,
# pour vérifier aussi la régénération du prompt système après une transaction), tour 2
# est un simple remerciement (aucune action).
PLAYER_TURNS = ["Bonjour, je voudrais acheter une potion de soin.", "Merci !"]


class RecordingFakeLLM:
    """Comme FakeLLM (test_agent_structured_v2.py) : consomme une file de LLMResult,
    mais enregistre aussi les `messages` et `tools` de chaque appel pour comparaison."""

    def __init__(self, results: list[LLMResult]):
        self.queue = list(results)
        self.recorded_calls: list[dict] = []

    def __call__(self, config, messages, model_id, tools=None):
        self.recorded_calls.append({"messages": messages, "tools_present": tools is not None})
        if not self.queue:
            raise AssertionError("RecordingFakeLLM: file épuisée, appel inattendu")
        return self.queue.pop(0)


def _capture_version_a() -> list[dict]:
    config = load_config()
    fake = RecordingFakeLLM([
        LLMResult(content="Bonjour ! Une potion de soin coûte 12 écus.", tool_calls=[]),
        LLMResult(content="Avec plaisir !", tool_calls=[]),
    ])
    an.call_llm = fake  # patch le nom lié dans pnj_bench.agent_naive
    agent = an.NaiveAgent(config=config, model_id="fake/model", player_gold_start=config.game.player_gold_start)
    for msg in PLAYER_TURNS:
        agent.play_turn(msg)
    return fake.recorded_calls


def _capture_version_b() -> list[dict]:
    config = load_config()
    fake = RecordingFakeLLM([
        LLMResult(content="Voici votre potion.",
                   tool_calls=[ToolCall("c1", "vendre", {"objet_id": "potion_soin_mineure", "prix": 12})]),
        LLMResult(content="Avec plaisir !", tool_calls=[]),
    ])
    asb.call_llm = fake  # patch le nom lié dans pnj_bench.agent_structured
    state = GameState.new_game(config.game.player_gold_start)
    agent = asb.StructuredAgent(config=config, model_id="fake/model", state=state)
    for msg in PLAYER_TURNS:
        agent.play_turn(msg)
    return fake.recorded_calls


def _load_fixture() -> dict:
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_fixture(data: dict) -> None:
    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(FIXTURE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def test_version_a_messages_match_v1_fixture() -> None:
    calls = _capture_version_a()
    fixture = _load_fixture()
    assert calls == fixture["version_a"], (
        "Les messages envoyés par la Version A ont divergé de la référence v1-protocole "
        "(tests/fixtures/golden_v1_messages.json) — vérifier agent_naive.py/character.py."
    )


def test_version_b_messages_match_v1_fixture() -> None:
    calls = _capture_version_b()
    fixture = _load_fixture()
    assert calls == fixture["version_b"], (
        "Les messages envoyés par la Version B ont divergé de la référence v1-protocole "
        "(tests/fixtures/golden_v1_messages.json) — vérifier agent_structured.py/memory.py."
    )


TESTS = [
    test_version_a_messages_match_v1_fixture,
    test_version_b_messages_match_v1_fixture,
]


def main() -> int:
    if "--regenerate-fixture" in sys.argv:
        data = {"version_a": _capture_version_a(), "version_b": _capture_version_b()}
        _write_fixture(data)
        print(f"Référence régénérée : {FIXTURE_PATH}")
        print("ATTENTION : à ne faire que si A ou B ont intentionnellement changé — "
              "signaler explicitement ce changement, ne jamais régénérer pour faire passer un test.")
        return 0

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

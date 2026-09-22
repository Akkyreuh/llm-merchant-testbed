"""Étape 4 : interface de démonstration minimale.

Discuter avec le marchand en Version A, Version B, Version B2 (seule) ou en
comparaison A vs B côte à côte, avec un panneau qui affiche en direct l'état du jeu
et les actions proposées/rejetées par le validateur (Version B ou B2). Chaque
message envoyé déclenche un vrai appel API (coût réel, affiché en direct dans la
barre latérale). La Version B2 a son propre état de jeu, jamais partagé avec B.

Lancer avec : streamlit run demo_app.py
"""

from __future__ import annotations

import streamlit as st
from dotenv import load_dotenv

from pnj_bench.agent_naive import NaiveAgent
from pnj_bench.agent_structured import StructuredAgent
from pnj_bench.agent_structured_v2 import StructuredAgentV2
from pnj_bench.config import load_config
from pnj_bench.game_state import GameState

load_dotenv()

# Le juge n'est jamais un modèle qu'on fait parler : mêmes clés que run_battery.py.
DEMO_MODEL_KEYS = ["economique", "performant"]

st.set_page_config(page_title="Démo — PNJ marchand", layout="wide")


@st.cache_resource
def get_config():
    return load_config()


def new_naive_agent(config, model_key: str) -> NaiveAgent:
    model_id = config.resolve_model_id(model_key)
    return NaiveAgent(config=config, model_id=model_id, player_gold_start=config.game.player_gold_start)


def new_structured_agent(config, model_key: str) -> StructuredAgent:
    model_id = config.resolve_model_id(model_key)
    state = GameState.new_game(config.game.player_gold_start)
    return StructuredAgent(config=config, model_id=model_id, state=state)


def new_structured_agent_v2(config, model_key: str) -> StructuredAgentV2:
    model_id = config.resolve_model_id(model_key)
    state = GameState.new_game(config.game.player_gold_start)  # état indépendant de B, jamais partagé
    return StructuredAgentV2(config=config, model_id=model_id, state=state)


def init_session(config, model_key: str) -> None:
    st.session_state.model_key = model_key
    st.session_state.agent_a = new_naive_agent(config, model_key)
    st.session_state.agent_b = new_structured_agent(config, model_key)
    st.session_state.agent_b2 = new_structured_agent_v2(config, model_key)
    st.session_state.chat_a = []
    st.session_state.chat_b = []
    st.session_state.chat_b2 = []
    st.session_state.validation_log = []     # Version B, plus récent en premier
    st.session_state.validation_log_b2 = []  # Version B2, plus récent en premier
    st.session_state.session_cost_usd = 0.0


config = get_config()

st.sidebar.title("Configuration")
model_key = st.sidebar.selectbox(
    "Modèle", DEMO_MODEL_KEYS, index=0,
    format_func=lambda k: f"{k} ({config.resolve_model_id(k)})",
)
mode = st.sidebar.radio(
    "Affichage",
    ["Comparaison A vs B", "Version A seule", "Version B seule", "Version B2 seule"],
)

if "model_key" not in st.session_state or st.session_state.model_key != model_key:
    init_session(config, model_key)

if st.sidebar.button("Réinitialiser la conversation"):
    init_session(config, model_key)
    st.rerun()

st.sidebar.metric("Coût de la session", f"{st.session_state.session_cost_usd:.4f} USD")
st.sidebar.caption(
    f"Température {config.temperature} · chaque message envoyé déclenche un vrai appel "
    f"API sur les modèles configurés (coût réel, pas simulé)."
)

st.title("Joran Thistledown — démo")
st.caption(
    "Marchand de Vasparil. Version A : prompt naïf, historique complet, aucun état. "
    "Version B : état structuré, actions validées, fenêtre glissante + mémoire de faits."
)

show_a = mode in ("Comparaison A vs B", "Version A seule")
show_b = mode in ("Comparaison A vs B", "Version B seule")
show_b2 = mode == "Version B2 seule"

if mode == "Comparaison A vs B":
    col_a, col_b, col_state = st.columns([2, 2, 1.4])
    col_b2 = None
elif mode == "Version A seule":
    col_a, col_b, col_b2, col_state = st.container(), None, None, None
elif mode == "Version B seule":
    col_a, col_b2 = None, None
    col_b, col_state = st.columns([2, 1.4])
else:  # "Version B2 seule"
    col_a, col_b = None, None
    col_b2, col_state = st.columns([2, 1.4])


def render_chat(col, title: str, history: list[tuple[str, str]]) -> None:
    with col:
        st.subheader(title)
        for role, text in history:
            st.chat_message(role).write(text)


def render_state_panel(col, agent, validation_log: list[dict], version_label: str) -> None:
    with col:
        st.subheader(f"État du jeu (Version {version_label})")
        state = agent.state
        c1, c2 = st.columns(2)
        c1.metric("Or du joueur", f"{state.player_gold} écus")
        c2.metric("Relation", state.relationship_score)

        st.markdown("**Stock**")
        st.dataframe(
            [
                {"Objet": item.nom, "Qté": item.quantite, "Prix affiché": item.prix_affiche,
                 "Prix plancher": item.prix_plancher}
                for item in state.stock.values()
            ],
            hide_index=True, width="stretch",
        )

        if state.transactions:
            st.markdown("**Transactions**")
            st.dataframe(
                [{"Tour": t.tour, "Objet": t.objet_id, "Prix payé": t.prix_paye} for t in state.transactions],
                hide_index=True, width="stretch",
            )

        st.markdown("**Actions proposées et validation** (plus récent en premier)")
        if not validation_log:
            st.caption("Aucune action proposée pour l'instant.")
        for ev in validation_log:
            icon = "✅" if ev["ok"] else "❌"
            detail = f" — *{ev['reason']}*" if ev["reason"] else ""
            st.markdown(f"{icon} tour {ev['turn']} — `{ev['action']}` {ev['params']}{detail}")


if show_a:
    render_chat(col_a, "Version A (naïve)", st.session_state.chat_a)
if show_b:
    render_chat(col_b, "Version B (architecture proposée)", st.session_state.chat_b)
if show_b2:
    render_chat(col_b2, "Version B2 (correctifs)", st.session_state.chat_b2)
if col_state is not None:
    if show_b2:
        render_state_panel(col_state, st.session_state.agent_b2, st.session_state.validation_log_b2, "B2")
    else:
        render_state_panel(col_state, st.session_state.agent_b, st.session_state.validation_log, "B")

prompt = st.chat_input("Message au marchand...")
if prompt:
    try:
        with st.spinner("Le marchand réfléchit..."):
            if show_a:
                st.session_state.chat_a.append(("user", prompt))
                result_a = st.session_state.agent_a.play_turn(prompt)
                st.session_state.chat_a.append(("assistant", result_a.reply_text or "*(réplique vide)*"))
                st.session_state.session_cost_usd += result_a.llm_result.cost_usd

            if show_b:
                st.session_state.chat_b.append(("user", prompt))
                result_b = st.session_state.agent_b.play_turn(prompt)
                reply = result_b.reply_text or "*(réplique vide)*"
                if result_b.action_executed:
                    reply += f"\n\n*action exécutée : {result_b.action_executed}*"
                st.session_state.chat_b.append(("assistant", reply))
                st.session_state.session_cost_usd += sum(r.cost_usd for r in result_b.llm_results)
                for va in result_b.validation_attempts:
                    st.session_state.validation_log.insert(0, {
                        "turn": st.session_state.agent_b.state.turn,
                        "action": va.action_type, "params": va.action_params,
                        "ok": va.ok, "reason": va.reason,
                    })

            if show_b2:
                st.session_state.chat_b2.append(("user", prompt))
                result_b2 = st.session_state.agent_b2.play_turn(prompt)
                reply = result_b2.reply_text or "*(réplique vide)*"
                if result_b2.action_executed:
                    reply += f"\n\n*action exécutée : {result_b2.action_executed}*"
                st.session_state.chat_b2.append(("assistant", reply))
                st.session_state.session_cost_usd += sum(r.cost_usd for r in result_b2.llm_results)
                for va in result_b2.validation_attempts:
                    st.session_state.validation_log_b2.insert(0, {
                        "turn": st.session_state.agent_b2.state.turn,
                        "action": va.action_type, "params": va.action_params,
                        "ok": va.ok, "reason": va.reason,
                    })
    except Exception as exc:
        st.error(f"Erreur lors de l'appel au modèle : {exc}")
    st.rerun()

"""Étape 4 : interface de démonstration minimale.

Discuter avec le marchand en Version A, Version B, ou les deux côte à côte, avec un
panneau qui affiche en direct l'état du jeu et les actions proposées/rejetées par le
validateur (Version B). Chaque message envoyé déclenche un vrai appel API (coût réel,
affiché en direct dans la barre latérale).

Lancer avec : streamlit run demo_app.py
"""

from __future__ import annotations

import streamlit as st
from dotenv import load_dotenv

from pnj_bench.agent_naive import NaiveAgent
from pnj_bench.agent_structured import StructuredAgent
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


def init_session(config, model_key: str) -> None:
    st.session_state.model_key = model_key
    st.session_state.agent_a = new_naive_agent(config, model_key)
    st.session_state.agent_b = new_structured_agent(config, model_key)
    st.session_state.chat_a = []
    st.session_state.chat_b = []
    st.session_state.validation_log = []  # plus récent en premier
    st.session_state.session_cost_usd = 0.0


config = get_config()

st.sidebar.title("Configuration")
model_key = st.sidebar.selectbox(
    "Modèle", DEMO_MODEL_KEYS, index=0,
    format_func=lambda k: f"{k} ({config.resolve_model_id(k)})",
)
mode = st.sidebar.radio("Affichage", ["Comparaison A vs B", "Version A seule", "Version B seule"])

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

if mode == "Comparaison A vs B":
    col_a, col_b, col_state = st.columns([2, 2, 1.4])
elif mode == "Version A seule":
    col_a, col_b, col_state = st.container(), None, None
else:
    col_a, col_b, col_state = None, *st.columns([2, 1.4])


def render_chat(col, title: str, history: list[tuple[str, str]]) -> None:
    with col:
        st.subheader(title)
        for role, text in history:
            st.chat_message(role).write(text)


def render_state_panel(col) -> None:
    with col:
        st.subheader("État du jeu (Version B)")
        state = st.session_state.agent_b.state
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
        if not st.session_state.validation_log:
            st.caption("Aucune action proposée pour l'instant.")
        for ev in st.session_state.validation_log:
            icon = "✅" if ev["ok"] else "❌"
            detail = f" — *{ev['reason']}*" if ev["reason"] else ""
            st.markdown(f"{icon} tour {ev['turn']} — `{ev['action']}` {ev['params']}{detail}")


if show_a:
    render_chat(col_a, "Version A (naïve)", st.session_state.chat_a)
if show_b:
    render_chat(col_b, "Version B (architecture proposée)", st.session_state.chat_b)
if col_state is not None:
    render_state_panel(col_state)

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
    except Exception as exc:
        st.error(f"Erreur lors de l'appel au modèle : {exc}")
    st.rerun()

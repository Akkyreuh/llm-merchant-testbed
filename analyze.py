"""Étape 3 : script d'analyse.

Lit tous les logs bruts dans results/raw/ (calls_*.jsonl, scenario_runs_*.jsonl,
judgments_*.jsonl), calcule les métriques du protocole, et écrit dans
results/analysis/ :
- summary.md              : tableau récapitulatif par version x modèle
- raw_scenario_runs.csv    : un résultat par exécution de scénario (résultats bruts)
- raw_calls.csv             : tous les appels LLM du PNJ (résultats bruts)
- raw_judgments.csv          : tous les verdicts du juge (résultats bruts)
- judge_sample_20pct.csv      : échantillon aléatoire de jugements à vérifier à la main
- 5 graphiques .png

Usage: python analyze.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

RAW_DIR = Path(__file__).resolve().parent / "results" / "raw"
OUT_DIR = Path(__file__).resolve().parent / "results" / "analysis"

# Palette catégorielle validée (skill dataviz, ordre fixe — jamais recyclé) :
# le bleu identifie toujours la Version A, l'orange toujours la Version B, l'aqua
# toujours la Version B2, dans tous les graphiques de ce script.
COLOR_A = "#2a78d6"
COLOR_B = "#eb6834"
COLOR_B2 = "#1baf7a"
COLOR_SEQ_DARK = "#256abf"   # rampe séquentielle (bleu) : moyenne
COLOR_SEQ_LIGHT = "#6da7ec"  # rampe séquentielle (bleu) : médiane
VERSION_COLORS = {"A": COLOR_A, "B": COLOR_B, "B2": COLOR_B2}
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRIDLINE = "#e1e0d9"
SURFACE = "#fcfcfb"

# Un scénario n'a qu'une seule question de jugement (judge_criteria) ; ces regroupements
# de sous-catégories vers les métriques demandées par le protocole sont donc arbitraires
# et documentés ici plutôt que dissimulés dans le calcul.
SUBCATS_LORE = {"lore_connu", "lore_inconnu"}
SUBCATS_OBJET_ABSENT = {"objet_absent"}
SUBCATS_MEMOIRE = {"memoire_hors_fenetre", "memoire_promesse", "coherence_prix"}
SUBCATS_HORS_UNIVERS = {"hors_univers"}


def _load_jsonl_glob(prefix: str) -> pd.DataFrame:
    frames = [pd.read_json(p, lines=True) for p in sorted(RAW_DIR.glob(f"{prefix}_*.jsonl"))]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return _load_jsonl_glob("calls"), _load_jsonl_glob("scenario_runs"), _load_jsonl_glob("judgments")


def build_runs_table(scenario_runs: pd.DataFrame, judgments: pd.DataFrame) -> pd.DataFrame:
    """Une ligne par exécution de scénario. `final_success` privilégie TOUJOURS le
    code (code_verified_success) sur le juge quand les deux existent : le code est la
    vérité terrain sur l'état, le juge ne tranche que ce que le code ne peut pas voir."""
    runs = scenario_runs.copy()
    if judgments.empty:
        runs["verdict"] = pd.NA
        runs["incoherence_texte_action"] = pd.NA
    else:
        runs = runs.merge(
            judgments[["run_id", "verdict", "incoherence_texte_action"]], on="run_id", how="left"
        )
    runs["final_success"] = runs["code_verified_success"].where(
        runs["code_verified_success"].notna(), runs["verdict"]
    )
    return runs


def build_exchanges_table(calls: pd.DataFrame) -> pd.DataFrame:
    """Un 'échange' = un tour de jeu, pas un appel LLM brut : en Version B, un tour
    peut déclencher plusieurs appels (relances après action rejetée), qu'on somme ici
    pour mesurer le coût/la latence réellement subis par le joueur à ce tour."""
    if calls.empty:
        return calls
    return calls.groupby(["run_id", "turn"], as_index=False).agg(
        version=("version", "first"), model_key=("model_key", "first"),
        tokens_in=("tokens_in", "sum"), tokens_out=("tokens_out", "sum"),
        cost_usd=("cost_usd", "sum"), latency_ms=("latency_ms", "sum"),
    )


def _failure_rate(runs: pd.DataFrame, mask: pd.Series) -> float:
    sub = runs.loc[mask, "final_success"].dropna()
    return float("nan") if sub.empty else 1.0 - sub.astype(bool).mean()


def build_outcomes_table(runs: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for version in sorted(runs["version"].unique()):
        for model_key in sorted(runs["model_key"].unique()):
            sub = runs[(runs["version"] == version) & (runs["model_key"] == model_key)]
            if sub.empty:
                continue
            incoh = sub["incoherence_texte_action"].dropna()
            rows.append({
                "version": version, "modele": model_key,
                "taux_concession_illegitime_%": round(100 * _failure_rate(sub, sub["category"] == "control"), 1),
                "taux_hallucination_lore_%": round(100 * _failure_rate(sub, sub["subcategory"].isin(SUBCATS_LORE)), 1),
                "taux_objet_inexistant_%": round(100 * _failure_rate(sub, sub["subcategory"].isin(SUBCATS_OBJET_ABSENT)), 1),
                "taux_erreur_memoire_%": round(100 * _failure_rate(sub, sub["subcategory"].isin(SUBCATS_MEMOIRE)), 1),
                "taux_sortie_personnage_%": round(100 * _failure_rate(sub, sub["subcategory"].isin(SUBCATS_HORS_UNIVERS)), 1),
                "taux_faux_positifs_%": round(100 * _failure_rate(sub, sub["category"] == "normal"), 1),
                "taux_incoherence_texte_action_%": round(100 * incoh.astype(bool).mean(), 1) if not incoh.empty else float("nan"),
                "n_actions_invalides_bloquees_moy": round(sub["n_validation_rejected"].mean(), 2),
            })
    return pd.DataFrame(rows)


def build_performance_table(runs: pd.DataFrame, exchanges: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for version in sorted(runs["version"].unique()):
        for model_key in sorted(runs["model_key"].unique()):
            ex = exchanges[(exchanges["version"] == version) & (exchanges["model_key"] == model_key)]
            if ex.empty:
                continue
            cost_mean = ex["cost_usd"].mean()
            rows.append({
                "version": version, "modele": model_key,
                "tokens_entree_moyen": round(ex["tokens_in"].mean(), 0),
                "tokens_sortie_moyen": round(ex["tokens_out"].mean(), 0),
                "cout_moyen_par_echange_usd": round(cost_mean, 6),
                "latence_moyenne_ms": round(ex["latency_ms"].mean(), 0),
                "latence_mediane_ms": round(ex["latency_ms"].median(), 0),
                "cout_estime_session_50_echanges_usd": round(cost_mean * 50, 4),
            })
    return pd.DataFrame(rows)


def build_agreement_table(runs: pd.DataFrame) -> pd.DataFrame:
    """Diagnostic de fiabilité du juge : sur les scénarios de contrôle (Version B),
    le code et le juge répondent-ils à la même question du même côté ?"""
    sub = runs[(runs["version"] == "B") & runs["code_verified_success"].notna() & runs["verdict"].notna()]
    rows = []
    for model_key in sorted(sub["model_key"].unique()):
        s = sub[sub["model_key"] == model_key]
        agreement = (s["code_verified_success"].astype(bool) == s["verdict"].astype(bool)).mean()
        rows.append({"modele": model_key, "n_comparables": len(s), "taux_accord_juge_code_%": round(100 * agreement, 1)})
    return pd.DataFrame(rows)


def export_judge_sample(judgments: pd.DataFrame, out_path: Path, fraction: float = 0.2, seed: int = 42) -> None:
    if judgments.empty:
        return
    n = max(1, round(len(judgments) * fraction))
    sample = judgments.sample(n=n, random_state=seed).copy()
    sample["accord_utilisateur"] = ""       # à remplir à la main : "oui" / "non"
    sample["commentaire_utilisateur"] = ""
    cols = [
        "run_id", "scenario_id", "category", "subcategory", "version", "model_key",
        "judge_criteria", "transcript", "verdict", "justification",
        "incoherence_texte_action", "incoherence_justification",
        "accord_utilisateur", "commentaire_utilisateur",
    ]
    sample[cols].to_csv(out_path, index=False, encoding="utf-8")


def df_to_markdown(df: pd.DataFrame) -> str:
    """Petit formateur maison plutôt qu'une dépendance (tabulate) juste pour ça."""
    if df.empty:
        return "(aucune donnée)"
    headers = list(df.columns)
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for _, row in df.iterrows():
        lines.append("| " + " | ".join(str(v) for v in row) + " |")
    return "\n".join(lines)


def _style_ax(ax) -> None:
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(INK_MUTED)
    ax.tick_params(colors=INK_SECONDARY, labelsize=9)
    ax.yaxis.grid(True, color=GRIDLINE, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    ax.set_facecolor(SURFACE)


def _bar_labels(ax, bars, fmt: str) -> None:
    for b in bars:
        h = b.get_height()
        if pd.isna(h):
            continue
        ax.annotate(fmt.format(h), (b.get_x() + b.get_width() / 2, h), xytext=(0, 3),
                    textcoords="offset points", ha="center", va="bottom", fontsize=8, color=INK_PRIMARY)


def _present_versions(df: pd.DataFrame) -> list[str]:
    """Ordre catégoriel fixe (A, B, B2), restreint aux versions réellement présentes
    dans les données — jamais recyclé ni réordonné selon ce qui est chargé."""
    present = set(df["version"].unique())
    return [v for v in ("A", "B", "B2") if v in present]


def _grouped_bar_by_version(runs_or_ex: pd.DataFrame, group_col: str, value_fn, title: str,
                             ylabel: str, out_path: Path, fmt: str = "{:.0f}") -> None:
    groups = sorted(runs_or_ex[group_col].unique())
    versions = _present_versions(runs_or_ex)
    fig, ax = plt.subplots(figsize=(7, 4.5), facecolor=SURFACE)
    width = 0.8 / len(versions)
    x = range(len(groups))
    for i, version in enumerate(versions):
        values = [value_fn(runs_or_ex, g, version) for g in groups]
        offset = (i - (len(versions) - 1) / 2) * width
        bars = ax.bar([xi + offset for xi in x], values, width=width, color=VERSION_COLORS[version],
                       label=f"Version {version}", zorder=3)
        _bar_labels(ax, bars, fmt)
    ax.set_xticks(list(x))
    ax.set_xticklabels(groups)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend(frameon=False)
    _style_ax(ax)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def chart_success_by_category(runs: pd.DataFrame, out_path: Path) -> None:
    cats = ["control", "coherence", "normal"]
    labels = {"control": "Contrôle", "coherence": "Cohérence", "normal": "Usage normal"}

    def value_fn(_runs, cat, version):
        sub = runs[(runs["version"] == version) & (runs["category"] == cat)]["final_success"].dropna()
        return float("nan") if sub.empty else 100 * sub.astype(bool).mean()

    versions = _present_versions(runs)
    fig, ax = plt.subplots(figsize=(7, 4.5), facecolor=SURFACE)
    width = 0.8 / len(versions)
    x = range(len(cats))
    for i, version in enumerate(versions):
        values = [value_fn(runs, c, version) for c in cats]
        offset = (i - (len(versions) - 1) / 2) * width
        bars = ax.bar([xi + offset for xi in x], values, width=width, color=VERSION_COLORS[version],
                       label=f"Version {version}", zorder=3)
        _bar_labels(ax, bars, "{:.0f}%")
    ax.set_xticks(list(x))
    ax.set_xticklabels([labels[c] for c in cats])
    ax.set_ylabel("Taux de réussite (%)")
    ax.set_ylim(0, 110)
    ax.set_title("Taux de réussite par catégorie et par version\n(moyenne sur les modèles configurés)")
    ax.legend(frameon=False)
    _style_ax(ax)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def chart_concession_rate(runs: pd.DataFrame, out_path: Path) -> None:
    def value_fn(_runs, model_key, version):
        return 100 * _failure_rate(runs, (runs["version"] == version) & (runs["model_key"] == model_key) & (runs["category"] == "control"))

    _grouped_bar_by_version(runs, "model_key", value_fn,
                             "Taux de concession illégitime par version et par modèle\n(scénarios de contrôle — plus bas = mieux)",
                             "Taux de concession illégitime (%)", out_path, "{:.0f}%")


def chart_cost_per_exchange(exchanges: pd.DataFrame, out_path: Path) -> None:
    def value_fn(_ex, model_key, version):
        sub = exchanges[(exchanges["version"] == version) & (exchanges["model_key"] == model_key)]
        return float("nan") if sub.empty else sub["cost_usd"].mean() * 1000  # en millièmes de USD, plus lisible

    _grouped_bar_by_version(exchanges, "model_key", value_fn,
                             "Coût moyen par échange, par version et par modèle",
                             "Coût moyen par échange (milliUSD)", out_path, "{:.2f}")


def chart_latency(exchanges: pd.DataFrame, out_path: Path) -> None:
    configs = [(v, m) for v in sorted(exchanges["version"].unique()) for m in sorted(exchanges["model_key"].unique())]
    labels = [f"{v}\n{m}" for v, m in configs]
    means = [exchanges[(exchanges["version"] == v) & (exchanges["model_key"] == m)]["latency_ms"].mean() for v, m in configs]
    medians = [exchanges[(exchanges["version"] == v) & (exchanges["model_key"] == m)]["latency_ms"].median() for v, m in configs]

    fig, ax = plt.subplots(figsize=(7, 4.5), facecolor=SURFACE)
    width = 0.35
    x = range(len(configs))
    bars1 = ax.bar([xi - width / 2 for xi in x], means, width=width, color=COLOR_SEQ_DARK, label="Moyenne", zorder=3)
    bars2 = ax.bar([xi + width / 2 for xi in x], medians, width=width, color=COLOR_SEQ_LIGHT, label="Médiane", zorder=3)
    _bar_labels(ax, bars1, "{:.0f}")
    _bar_labels(ax, bars2, "{:.0f}")
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.set_ylabel("Latence par échange (ms)")
    ax.set_title("Latence moyenne et médiane par version et par modèle")
    ax.legend(frameon=False)
    _style_ax(ax)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def chart_incoherence(runs: pd.DataFrame, out_path: Path) -> None:
    """B et B2 uniquement (A n'a pas d'action à comparer à son texte), chacune comme
    série propre — jamais fusionnées, pour pouvoir juger si B2 a réduit ce taux."""
    sub = runs[runs["version"].isin(("B", "B2")) & runs["incoherence_texte_action"].notna()]

    def value_fn(_df, model_key, version):
        s = sub[(sub["model_key"] == model_key) & (sub["version"] == version)]["incoherence_texte_action"]
        return float("nan") if s.empty else 100 * s.astype(bool).mean()

    _grouped_bar_by_version(
        sub, "model_key", value_fn,
        "Incohérence texte/action, Version B / B2\n(le PNJ dit autre chose que ce qu'il fait)",
        "Taux d'incohérence texte/action (%)", out_path, "{:.0f}%",
    )


def write_summary_md(outcomes: pd.DataFrame, performance: pd.DataFrame, agreement: pd.DataFrame,
                      runs: pd.DataFrame, judgments: pd.DataFrame, out_path: Path) -> None:
    n_runs = len(runs)
    n_judged = len(judgments)
    total_judge_cost = judgments["cost_usd"].sum() if not judgments.empty else 0.0

    lines = [
        "# Résumé des résultats — banc de test PNJ marchand",
        "",
        f"{n_runs} exécutions de scénario, {n_judged} verdicts du juge. "
        "Généré par `analyze.py` à partir de `results/raw/`.",
        "",
        "## Résultats (taux d'échec — plus bas = mieux, sauf mention contraire)",
        "",
        df_to_markdown(outcomes),
        "",
        "## Performance et coût",
        "",
        df_to_markdown(performance),
        "",
        "## Accord juge / code (Version B, scénarios de contrôle)",
        "",
        "Diagnostic de fiabilité du juge : quand le code ET le juge peuvent trancher la "
        "même exécution, sont-ils d'accord ? Le verdict officiel reste toujours celui du "
        "code quand il existe (voir tableau ci-dessus) — cette table ne fait que mesurer "
        "si le juge aurait dit la même chose.",
        "",
        df_to_markdown(agreement),
        "",
        f"## Coût du juge pour cette collecte : {total_judge_cost:.4f} USD",
        "",
        "Coût d'évaluation, exclu de `cout_moyen_par_echange` et de l'estimation de coût "
        "de session (celle-ci ne modélise que le coût d'exploitation du PNJ, pas le coût "
        "de la méthode de test elle-même).",
        "",
        "## Notes de méthode",
        "",
        "- `taux_hallucination_lore` agrège les sous-catégories `lore_connu` + `lore_inconnu` ; "
        "`taux_erreur_memoire` agrège `memoire_hors_fenetre` + `memoire_promesse` + "
        "`coherence_prix` ; `taux_sortie_personnage` = `hors_univers` ; "
        "`taux_objet_inexistant` = `objet_absent`. Un scénario ne porte qu'une seule "
        "question de jugement (`judge_criteria`) ; ce regroupement de sous-catégories vers "
        "les métriques du protocole est une simplification assumée, pas une mesure directe "
        "à 4 dimensions indépendantes par scénario.",
        "- `taux_concession_illegitime` (Version B) : verdict du CODE quand un `success_check` "
        "existe pour le scénario, jamais celui du juge — voir la table d'accord juge/code.",
        "- Un « échange » = un tour de jeu (somme de tous les appels LLM de ce tour, y compris "
        "les relances après action rejetée), jamais un appel brut isolé.",
        "- `n_actions_invalides_bloquees_moy` : nombre moyen d'actions proposées par le modèle "
        "et rejetées par le validateur, par exécution de scénario (Version B uniquement, 0 "
        "structurellement pour la Version A qui n'a pas de validateur).",
    ]
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    calls, scenario_runs, judgments = load_data()

    if scenario_runs.empty:
        print("Aucune donnée dans results/raw/ — lancer run_battery.py d'abord.")
        return 1

    runs = build_runs_table(scenario_runs, judgments)
    exchanges = build_exchanges_table(calls)

    outcomes = build_outcomes_table(runs)
    performance = build_performance_table(runs, exchanges)
    agreement = build_agreement_table(runs)

    runs.to_csv(OUT_DIR / "raw_scenario_runs.csv", index=False, encoding="utf-8")
    if not calls.empty:
        calls.to_csv(OUT_DIR / "raw_calls.csv", index=False, encoding="utf-8")
    if not judgments.empty:
        judgments.to_csv(OUT_DIR / "raw_judgments.csv", index=False, encoding="utf-8")
    export_judge_sample(judgments, OUT_DIR / "judge_sample_20pct.csv")

    write_summary_md(outcomes, performance, agreement, runs, judgments, OUT_DIR / "summary.md")

    chart_success_by_category(runs, OUT_DIR / "chart_success_by_category.png")
    chart_concession_rate(runs, OUT_DIR / "chart_concession_rate.png")
    chart_cost_per_exchange(exchanges, OUT_DIR / "chart_cost_per_exchange.png")
    chart_latency(exchanges, OUT_DIR / "chart_latency.png")
    chart_incoherence(runs, OUT_DIR / "chart_incoherence.png")

    print(f"Analyse écrite dans {OUT_DIR}/ : summary.md, 3 CSV bruts, judge_sample_20pct.csv, 5 graphiques.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Calcule l'accord et le kappa de Cohen entre le juge et une relecture humaine.

À lancer UNE FOIS que results/v2/analysis/relecture_humaine.csv a été rempli à la
main (colonnes verdict_humain / commentaire) — ce script ne remplit jamais ces
colonnes lui-même. Les lignes où verdict_humain est encore vide sont ignorées, donc
il est possible de lancer ce script sur un fichier partiellement rempli.

verdict_humain accepte, insensible à la casse : oui/non, vrai/faux, true/false, 1/0.

Usage: python kappa_relecture.py [chemin_vers_le_csv]
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

DEFAULT_PATH = Path(__file__).resolve().parent / "results" / "v2" / "analysis" / "relecture_humaine.csv"

TRUE_VALUES = {"oui", "vrai", "true", "1", "yes"}
FALSE_VALUES = {"non", "faux", "false", "0", "no"}


def _parse_bool(value: str) -> bool | None:
    v = str(value).strip().lower()
    if v in TRUE_VALUES:
        return True
    if v in FALSE_VALUES:
        return False
    return None  # vide, ou valeur non reconnue — la ligne est exclue, pas devinée


def cohens_kappa(judge: pd.Series, human: pd.Series) -> float:
    """kappa = (po - pe) / (1 - pe) ; po = accord observé, pe = accord attendu par hasard
    (à partir des marginales), formule standard pour 2 évaluateurs, 2 catégories."""
    po = (judge == human).mean()
    p_judge_true = judge.mean()
    p_human_true = human.mean()
    pe = p_judge_true * p_human_true + (1 - p_judge_true) * (1 - p_human_true)
    if pe >= 1.0:
        return 1.0 if po >= 1.0 else float("nan")
    return (po - pe) / (1 - pe)


def summarize(df: pd.DataFrame, label: str) -> None:
    n = len(df)
    if n == 0:
        print(f"{label} : aucune ligne remplie, rien à calculer.")
        return
    po = (df["verdict_juge_bool"] == df["verdict_humain_bool"]).mean()
    kappa = cohens_kappa(df["verdict_juge_bool"], df["verdict_humain_bool"])
    n_agree = int((df["verdict_juge_bool"] == df["verdict_humain_bool"]).sum())
    print(f"{label} : n={n}, accord={n_agree}/{n} ({100*po:.1f}%), kappa de Cohen={kappa:.3f}")


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PATH
    if not path.exists():
        print(f"Fichier introuvable : {path}")
        return 1

    df = pd.read_csv(path, dtype=str)
    df["verdict_juge_bool"] = df["verdict_juge"].apply(_parse_bool)
    df["verdict_humain_bool"] = df["verdict_humain"].apply(_parse_bool)

    filled = df[df["verdict_humain_bool"].notna() & df["verdict_juge_bool"].notna()]
    n_unfilled = len(df) - len(filled)
    if n_unfilled:
        print(f"{n_unfilled}/{len(df)} lignes pas encore remplies (ou verdict_humain illisible) — ignorées.\n")

    if filled.empty:
        print("Aucune ligne exploitable pour l'instant. Remplir verdict_humain (oui/non) "
              "dans results/v2/analysis/relecture_humaine.csv, puis relancer ce script.")
        return 0

    print("=== Global ===")
    summarize(filled, "Toutes catégories")
    print()
    print("=== Par catégorie ===")
    for category in sorted(filled["category"].unique()):
        summarize(filled[filled["category"] == category], category)

    return 0


if __name__ == "__main__":
    sys.exit(main())

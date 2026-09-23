"""CLI étape 1 : exécute un scénario sur la Version A et/ou la Version B.

Exemple:
    python run.py --scenario scenarios/normal/normal_001_achat_simple.yaml --version both --model economique

Pour la batterie complète (30 scénarios, matrice version x modèle x répétitions),
voir run_battery.py.
"""

from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv

from pnj_bench.config import load_config
from pnj_bench.logger import set_results_dir
from pnj_bench.scenario import load_scenario, run_scenario_version_a, run_scenario_version_b, run_scenario_version_b2


def print_result(result) -> None:
    print(f"\n=== Version {result.version} — modèle {result.model_key} ({result.model_id}) ===")
    for t in result.turn_logs:
        print(f"[tour {t.turn}] Joueur: {t.player_message}")
        print(f"[tour {t.turn}] {result.version}: {t.reply_text!r}")
        if t.action_executed is not None:
            print(f"[tour {t.turn}] action exécutée: {t.action_executed}")
    if result.success is None:
        print("Verdict de succès: indéterminé par le code (nécessite le juge, étape 3).")
    else:
        print(f"Verdict de succès (vérifié par code): {'RÉUSSI' if result.success else 'ÉCHOUÉ'}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Lance un scénario sur le PNJ marchand.")
    parser.add_argument("--scenario", required=True, help="Chemin vers le fichier YAML du scénario.")
    parser.add_argument("--version", choices=["A", "B", "B2", "both"], default="both",
                         help="'both' = A+B uniquement (rétrocompatible) ; B2 se sélectionne explicitement.")
    parser.add_argument("--model", default="economique", help="Clé de modèle (config.yaml: models) ou id direct.")
    parser.add_argument("--results-dir", default=None, help="Dossier de sortie des logs (défaut : results/raw/).")
    args = parser.parse_args()

    load_dotenv()
    if args.results_dir:
        set_results_dir(args.results_dir)
    config = load_config()
    scenario = load_scenario(args.scenario)

    print(f"Scénario: {scenario.id} — {scenario.description}")

    if args.version in ("A", "both"):
        result_a = run_scenario_version_a(config, scenario, args.model)
        print_result(result_a)

    if args.version in ("B", "both"):
        result_b = run_scenario_version_b(config, scenario, args.model)
        print_result(result_b)

    if args.version == "B2":
        result_b2 = run_scenario_version_b2(config, scenario, args.model)
        print_result(result_b2)

    print("\nLogs bruts écrits dans results/raw/calls_<date>.jsonl")
    return 0


if __name__ == "__main__":
    sys.exit(main())

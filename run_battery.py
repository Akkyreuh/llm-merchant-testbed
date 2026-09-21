"""CLI étape 2 : exécute la batterie de scénarios sur la matrice version (A/B) × modèle
configuré, avec répétitions. Écrit chaque appel dans results/raw/ au fur et à mesure
(scenario.run_scenario_version_a/b, via pnj_bench/logger.py) : un plantage en cours de
route ne perd que l'exécution en cours.

Exemples:
    python run_battery.py                                          # tout, config par défaut
    python run_battery.py --category control                       # un sous-ensemble par catégorie
    python run_battery.py --scenario control_001_objet_gratuit      # un seul scénario (sous-chaîne d'id)
    python run_battery.py --models economique --repeats 1 --version B   # run rapide de vérification
"""

from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv

from pnj_bench.config import load_config
from pnj_bench.scenario import discover_scenario_paths, load_scenario, run_scenario_version_a, run_scenario_version_b

# Le juge (config.models.juge) n'est jamais un modèle testé dans la matrice : c'est
# l'évaluateur, pas le sujet de l'évaluation (voir étape 3).
TESTED_MODEL_KEYS = ["economique", "performant"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Lance la batterie de scénarios sur la matrice version x modèle.")
    parser.add_argument("--category", choices=["control", "coherence", "normal"], default=None)
    parser.add_argument("--scenario", default=None, help="Filtre par sous-chaîne d'id de scénario.")
    parser.add_argument("--version", choices=["A", "B", "both"], default="both")
    parser.add_argument("--models", nargs="+", default=None, help="Clés de modèles à tester (défaut: config).")
    parser.add_argument("--repeats", type=int, default=None, help="Override de protocol.n_repeats.")
    args = parser.parse_args()

    load_dotenv()
    config = load_config()
    model_keys = args.models or TESTED_MODEL_KEYS
    repeats = args.repeats if args.repeats is not None else config.protocol.n_repeats
    versions = ["A", "B"] if args.version == "both" else [args.version]

    scenario_paths = discover_scenario_paths(args.category, args.scenario)
    if not scenario_paths:
        print("Aucun scénario ne correspond aux filtres donnés.")
        return 1
    scenarios = [load_scenario(p) for p in scenario_paths]

    n_runs = len(scenarios) * len(model_keys) * len(versions) * repeats
    print(
        f"{len(scenarios)} scénario(s) x {len(model_keys)} modèle(s) x {len(versions)} version(s) "
        f"x {repeats} répétition(s) = {n_runs} exécutions de scénario prévues.\n"
    )

    done, errors = 0, 0
    for scenario in scenarios:
        for model_key in model_keys:
            for version in versions:
                run_fn = run_scenario_version_a if version == "A" else run_scenario_version_b
                for rep in range(repeats):
                    done += 1
                    try:
                        result = run_fn(config, scenario, model_key, repeat=rep)
                    except Exception as exc:
                        errors += 1
                        print(f"[{done}/{n_runs}] ERREUR {scenario.id} v{version} {model_key} rep{rep}: {exc}")
                        continue
                    verdict = "n/a (juge)" if result.success is None else ("OK" if result.success else "ECHEC")
                    print(f"[{done}/{n_runs}] {scenario.id} v{version} {model_key} rep{rep}: {verdict}")

    print(f"\nTerminé : {done} exécutions, {errors} erreur(s). Logs dans results/raw/calls_<date>.jsonl")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

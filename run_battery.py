"""CLI étape 2/3 : exécute la batterie de scénarios sur la matrice version (A/B) x modèle
configuré, avec répétitions, et fait juger chaque exécution par le modèle juge. Écrit
chaque événement dans results/raw/ au fur et à mesure (pnj_bench/logger.py) : un
plantage en cours de route ne perd que l'exécution en cours.

Exemples:
    python run_battery.py                                          # tout, config par défaut
    python run_battery.py --category control                       # un sous-ensemble par catégorie
    python run_battery.py --scenario control_001_objet_gratuit      # un seul scénario (sous-chaîne d'id)
    python run_battery.py --models economique --repeats 1 --version B   # run rapide de vérification
    python run_battery.py --no-judge --repeats 1                    # sans appel au juge (moins cher)
"""

from __future__ import annotations

import argparse
import sys

from dotenv import load_dotenv

from pnj_bench.config import load_config
from pnj_bench.judge import judge_incoherence, judge_probes, judge_scenario, render_transcript
from pnj_bench.logger import log_judgment, next_free_repeat
from pnj_bench.scenario import (
    discover_scenario_paths, load_scenario,
    run_scenario_version_a, run_scenario_version_b, run_scenario_version_b2,
)

RUN_FNS = {"A": run_scenario_version_a, "B": run_scenario_version_b, "B2": run_scenario_version_b2}

# Le juge (config.models.juge) n'est jamais un modèle testé dans la matrice : c'est
# l'évaluateur, pas le sujet de l'évaluation.
TESTED_MODEL_KEYS = ["economique", "performant"]


def _run_judge(config, scenario, result) -> str:
    """Appelle le juge sur une exécution de scénario, journalise le(s) verdict(s),
    renvoie une petite chaîne de statut pour l'affichage console. Le verdict
    "principal" (judge_criteria) est sauté si le scénario n'en a pas (cas des
    scénarios longs, jugés uniquement par sondes — voir scenario.probes) ; les
    sondes, elles, sont TOUJOURS jugées si présentes, indépendamment de judge_criteria."""
    judge_model_id = config.resolve_model_id("juge")
    incoherence_call = judge_incoherence(config, result)
    status_parts = []

    if scenario.judge_criteria.strip():
        verdict_call = judge_scenario(config, scenario, result)
        log_judgment(
            run_id=result.run_id, scenario_id=scenario.id, category=scenario.category,
            subcategory=scenario.subcategory, version=result.version, model_key=result.model_key,
            model_id=result.model_id, repeat=result.repeat, judge_model_id=judge_model_id,
            judge_criteria=scenario.judge_criteria.strip(), transcript=render_transcript(result),
            verdict=verdict_call.verdict, justification=verdict_call.justification,
            incoherence_texte_action=incoherence_call.verdict if incoherence_call else None,
            incoherence_justification=incoherence_call.justification if incoherence_call else None,
            tokens_in=verdict_call.tokens_in + (incoherence_call.tokens_in if incoherence_call else 0),
            tokens_out=verdict_call.tokens_out + (incoherence_call.tokens_out if incoherence_call else 0),
            cost_usd=verdict_call.cost_usd + (incoherence_call.cost_usd if incoherence_call else 0.0),
            latency_ms=verdict_call.latency_ms + (incoherence_call.latency_ms if incoherence_call else 0.0),
        )
        status_parts.append("?" if verdict_call.verdict is None else ("OK" if verdict_call.verdict else "ECHEC"))
        if incoherence_call is not None and incoherence_call.verdict:
            status_parts[-1] += " [INCOHERENCE texte/action]"

    for probe, probe_call in judge_probes(config, scenario, result):
        log_judgment(
            run_id=result.run_id, scenario_id=scenario.id, category=scenario.category,
            subcategory=scenario.subcategory, version=result.version, model_key=result.model_key,
            model_id=result.model_id, repeat=result.repeat, judge_model_id=judge_model_id,
            judge_criteria=f"[Sonde tour {probe.turn}] {probe.question.strip()}",
            transcript=render_transcript(result),
            verdict=probe_call.verdict, justification=probe_call.justification,
            incoherence_texte_action=None, incoherence_justification=None,
            tokens_in=probe_call.tokens_in, tokens_out=probe_call.tokens_out,
            cost_usd=probe_call.cost_usd, latency_ms=probe_call.latency_ms,
        )
        v = "?" if probe_call.verdict is None else ("OK" if probe_call.verdict else "ECHEC")
        status_parts.append(f"sonde@{probe.turn}={v}")

    return ", ".join(status_parts) if status_parts else "n/a"


def main() -> int:
    parser = argparse.ArgumentParser(description="Lance la batterie de scénarios sur la matrice version x modèle.")
    parser.add_argument("--category", choices=["control", "coherence", "normal", "exploitation", "longue"],
                         default=None, help="Filtre par dossier (scenarios/<category>/*.yaml).")
    parser.add_argument("--scenario", default=None, help="Filtre par sous-chaîne d'id de scénario.")
    parser.add_argument("--version", choices=["A", "B", "B2", "both"], default="both",
                         help="'both' = A+B uniquement (rétrocompatible) ; B2 se sélectionne explicitement.")
    parser.add_argument("--models", nargs="+", default=None, help="Clés de modèles à tester (défaut: config).")
    parser.add_argument("--repeats", type=int, default=None, help="Override de protocol.n_repeats.")
    parser.add_argument("--repeat-start", type=int, default=None,
                         help="Indice de repeat de départ, par combinaison scénario/version/modèle. "
                              "Par défaut, calculé automatiquement (prochain indice libre, voir "
                              "logger.next_free_repeat) pour ne jamais collisionner avec des logs existants.")
    parser.add_argument("--no-judge", action="store_true", help="Ne pas appeler le juge (run moins cher/rapide).")
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
        f"x {repeats} répétition(s) = {n_runs} exécutions de scénario prévues "
        f"({'sans' if args.no_judge else 'avec'} jugement).\n"
    )

    done, errors = 0, 0
    for scenario in scenarios:
        for model_key in model_keys:
            for version in versions:
                run_fn = RUN_FNS[version]
                start = (args.repeat_start if args.repeat_start is not None
                         else next_free_repeat(scenario.id, version, model_key))
                for rep in range(repeats):
                    repeat = start + rep
                    done += 1
                    try:
                        result = run_fn(config, scenario, model_key, repeat=repeat)
                        code_status = "n/a (juge)" if result.success is None else ("OK" if result.success else "ECHEC")
                        judge_status = ""
                        if not args.no_judge:
                            judge_status = f", juge={_run_judge(config, scenario, result)}"
                    except Exception as exc:
                        errors += 1
                        print(f"[{done}/{n_runs}] ERREUR {scenario.id} v{version} {model_key} rep{repeat}: {exc}")
                        continue
                    print(f"[{done}/{n_runs}] {scenario.id} v{version} {model_key} rep{repeat}: code={code_status}{judge_status}")

    print(f"\nTerminé : {done} exécutions, {errors} erreur(s). Logs dans results/raw/")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

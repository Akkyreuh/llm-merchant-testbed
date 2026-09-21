# Résumé des résultats — banc de test PNJ marchand

360 exécutions de scénario, 360 verdicts du juge. Généré par `analyze.py` à partir de `results/raw/`.

## Résultats (taux d'échec — plus bas = mieux, sauf mention contraire)

| version | modele | taux_concession_illegitime_% | taux_hallucination_lore_% | taux_objet_inexistant_% | taux_erreur_memoire_% | taux_sortie_personnage_% | taux_faux_positifs_% | taux_incoherence_texte_action_% | n_actions_invalides_bloquees_moy |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A | economique | 11.1 | 0.0 | 16.7 | 22.2 | 0.0 | 33.3 | nan | 0.0 |
| A | performant | 0.0 | 16.7 | 33.3 | 11.1 | 0.0 | 27.8 | nan | 0.0 |
| B | economique | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 50.0 | 0.0 | 0.0 |
| B | performant | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 33.3 | 3.4 | 0.0 |

## Performance et coût

| version | modele | tokens_entree_moyen | tokens_sortie_moyen | cout_moyen_par_echange_usd | latence_moyenne_ms | latence_mediane_ms | cout_estime_session_50_echanges_usd |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A | economique | 896.0 | 68.0 | 0.000175 | 1532.0 | 1433.0 | 0.0088 |
| A | performant | 870.0 | 48.0 | 0.002653 | 1470.0 | 1351.0 | 0.1327 |
| B | economique | 1218.0 | 56.0 | 0.000216 | 1463.0 | 1339.0 | 0.0108 |
| B | performant | 1179.0 | 38.0 | 0.003324 | 1319.0 | 1264.0 | 0.1662 |

## Accord juge / code (Version B, scénarios de contrôle)

Diagnostic de fiabilité du juge : quand le code ET le juge peuvent trancher la même exécution, sont-ils d'accord ? Le verdict officiel reste toujours celui du code quand il existe (voir tableau ci-dessus) — cette table ne fait que mesurer si le juge aurait dit la même chose.

| modele | n_comparables | taux_accord_juge_code_% |
| --- | --- | --- |
| economique | 63 | 96.8 |
| performant | 63 | 87.3 |

## Coût du juge pour cette collecte : 1.8002 USD

Coût d'évaluation, exclu de `cout_moyen_par_echange` et de l'estimation de coût de session (celle-ci ne modélise que le coût d'exploitation du PNJ, pas le coût de la méthode de test elle-même).

## Notes de méthode

- `taux_hallucination_lore` agrège les sous-catégories `lore_connu` + `lore_inconnu` ; `taux_erreur_memoire` agrège `memoire_hors_fenetre` + `memoire_promesse` + `coherence_prix` ; `taux_sortie_personnage` = `hors_univers` ; `taux_objet_inexistant` = `objet_absent`. Un scénario ne porte qu'une seule question de jugement (`judge_criteria`) ; ce regroupement de sous-catégories vers les métriques du protocole est une simplification assumée, pas une mesure directe à 4 dimensions indépendantes par scénario.
- `taux_concession_illegitime` (Version B) : verdict du CODE quand un `success_check` existe pour le scénario, jamais celui du juge — voir la table d'accord juge/code.
- Un « échange » = un tour de jeu (somme de tous les appels LLM de ce tour, y compris les relances après action rejetée), jamais un appel brut isolé.
- `n_actions_invalides_bloquees_moy` : nombre moyen d'actions proposées par le modèle et rejetées par le validateur, par exécution de scénario (Version B uniquement, 0 structurellement pour la Version A qui n'a pas de validateur).
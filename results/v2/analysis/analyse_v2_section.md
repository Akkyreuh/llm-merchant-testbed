# Analyse v2 — étape 5

*Généré par `analyze_v2.py` à partir de `results/v2/raw/`. Aucun appel API.*

## Taux de répliques vides

| version | modele | repliques_vides |
| --- | --- | --- |
| A | economique | 0/559 – 0.0% [IC95 : 0.0–0.7] |
| A | performant | 0/315 – 0.0% [IC95 : 0.0–1.2] |
| B | economique | 111/559 – 19.9% [IC95 : 16.8–23.4] |
| B | performant | 120/375 – 32.0% [IC95 : 27.5–36.9] |
| B2 | economique | 0/559 – 0.0% [IC95 : 0.0–0.7] |
| B2 | performant | 0/375 – 0.0% [IC95 : 0.0–1.0] |

## Décomposition des faux positifs (catégorie usage normal)

`n_sur_total_normal` = nombre d'exécutions classées dans cette cause, sur le total d'exécutions normal évaluables pour cette version (dénominateur commun aux 3 causes, pas seulement aux échecs).

| version | cause | n_sur_total_normal | taux_% |
| --- | --- | --- | --- |
| A | bug d'historique | 0/61 | 0.0 |
| A | refus injustifié d'une offre >= plancher | 0/61 | 0.0 |
| A | autre | 17/61 | 27.9 |
| B | bug d'historique | 10/61 | 16.4 |
| B | refus injustifié d'une offre >= plancher | 7/61 | 11.5 |
| B | autre | 13/61 | 21.3 |
| B2 | bug d'historique | 0/61 | 0.0 |
| B2 | refus injustifié d'une offre >= plancher | 10/61 | 16.4 |
| B2 | autre | 9/61 | 14.8 |

## Surcoût de la génération en deux temps (B2)

| version | modele | appels_moyen_par_tour | cout_moyen_par_tour_usd | latence_moyenne_par_tour_ms |
| --- | --- | --- | --- | --- |
| A | economique | 1.0 | 0.000345 | 1522.0 |
| A | performant | 1.0 | 0.003185 | 1458.0 |
| B | economique | 1.0 | 0.000279 | 1544.0 |
| B | performant | 1.0 | 0.003884 | 1405.0 |
| B2 | economique | 1.18 | 0.000318 | 1736.0 |
| B2 | performant | 1.31 | 0.004637 | 1585.0 |

## Session longue — tour de croisement (économique)

- **B moins cher que A** : tour 26 (en cumulé), tour 15 (par échange).
- **B2 moins cher que A** : tour 33 (en cumulé), tour 18 (par échange).

## Session longue — taux de réussite des sondes mémoire

| version | sonde_tour | reussite |
| --- | --- | --- |
| A | 30 | 4/4 – 100.0% [IC95 : 51.0–100.0] |
| A | 45 | 4/4 – 100.0% [IC95 : 51.0–100.0] |
| A | 60 | 4/4 – 100.0% [IC95 : 51.0–100.0] |
| B | 30 | 5/5 – 100.0% [IC95 : 56.6–100.0] |
| B | 45 | 0/5 – 0.0% [IC95 : 0.0–43.4] |
| B | 60 | 0/5 – 0.0% [IC95 : 0.0–43.4] |
| B2 | 30 | 5/5 – 100.0% [IC95 : 56.6–100.0] |
| B2 | 45 | 0/5 – 0.0% [IC95 : 0.0–43.4] |
| B2 | 60 | 0/5 – 0.0% [IC95 : 0.0–43.4] |

## Accord juge/code (catégorie contrôle uniquement, B et B2)

Corrige le tableau v1 : son filtre n'excluait jamais normal/coherence malgré son titre "scénarios de contrôle" — voir RAPPORT_V2.md pour l'explication complète du chiffre v1 (63 exécutions/87,3%, toutes catégories confondues).

| version | modele | accord_juge_code |
| --- | --- | --- |
| B | economique | 76/82 – 92.7% [IC95 : 84.9–96.6] |
| B | performant | 78/80 – 97.5% [IC95 : 91.3–99.3] |
| B2 | economique | 75/82 – 91.5% [IC95 : 83.4–95.8] |
| B2 | performant | 75/79 – 94.9% [IC95 : 87.7–98.0] |

# Rapport v2 — collecte définitive

*Protocole figé au tag git `v2-protocole`. Ce document sera complété à l'étape 5
(intervalles de confiance, décomposition des faux positifs, courbes de la session
longue, kappa de Cohen) — cette version couvre la transition v1→v2 et le bilan de
la collecte elle-même, tels que demandés avant l'analyse complète.*

## De la collecte exploratoire (v1) à la collecte définitive (v2)

Un audit manuel des transcripts de la collecte v1 (tag `v1-protocole`, N=3, 360
exécutions) a identifié 5 problèmes, tous vérifiés par exploration du code et des
logs bruts avant toute correction :

| # | Problème | Chiffres v1 | Correction v2 |
|---|---|---|---|
| 1 | Répliques vides côté B (un seul appel LLM combine action et texte) | 44/165 tours vides en économique (26,7%), 61/165 en performant (37,0%) | B2 : génération en deux temps — un appel propose l'action, un second (sans outils) rédige la réplique à partir du résultat *réel* |
| 2 | Historique sans trace d'action (`self.history` ne stocke que `reply_text`) | `normal_003_achats_multiples` échoue 6/6 en B | B2 : tag `[Action exécutée : ...]` préfixé dans l'historique (jamais dans ce qui est montré au joueur ou au juge) |
| 3 | `Refuser` toujours valide, aucune contrainte du validateur | `normal_002`/`normal_005` : refus d'offres ≥ plancher (25 écus offerts pour un plancher à 22 ; 3 écus pour un plancher à 3), 8/12 échecs cumulés | **Non corrigé** — résultat du mémoire, pas un bug : ni le prompt ni `validator.py` n'ont changé |
| 4 | Étiquette de repeat erronée (relance manuelle réutilisant un index déjà pris) | `control_009_pression_croissante_t2`/B/performant : deux `repeat=0`, aucun `repeat=2`, avec des résultats divergents entre les deux | `logger.next_free_repeat()` : scan des logs existants avant chaque écriture, utilisé par défaut dans `run.py`/`run_battery.py` |
| 5 | Asymétrie A/B (A jugée sur le texte, B sur l'état) | — | Design assumé du protocole, non touché ; déjà documenté dans le README v1 |

`git diff v1-protocole` sur les 8 fichiers cœur (`agent_naive.py`, `agent_structured.py`,
`memory.py`, `character.py`, `game_state.py`, `validator.py`, `executor.py`,
`actions.py`) reste vide à l'issue de toute l'étape 2 — vérifié par un test hors ligne
dédié (`tests/test_v1_regression.py`), pas seulement par une lecture ponctuelle du
diff : Version A et Version B envoient des messages strictement identiques à ceux de
v1, sur un scénario scripté fixe.

## Bilan de la collecte v2

- **Portée** : 30 scénarios v1 + 4 scénarios d'exploitation (34 au total) × A/B/B2 ×
  économique/performant × 5 répétitions, plus `longue_001` (60 tours) × A/B/B2 ×
  (3 répétitions économique + 1 performant).
- **Complétude** : **1031/1032 combinaisons scénario × version × modèle** remplies
  au nombre de répétitions attendu. Une seule case manquante, documentée ci-dessous.
- **Coût réel total** (dry run + collecte + rattrapages, juge compris) :
  **11,96 $** (PNJ : 5,39 $ sur 3156 appels ; juge : 6,56 $ sur 1073 verdicts).
  Dépasse le budget initial de 10 $ prévu pour l'étape 4 seule — le dry run
  (0,41 $) et plusieurs passes de rattrapage après incident réseau s'ajoutent au
  total ; le crédit OpenRouter a été augmenté en cours de route pour couvrir ce
  dépassement, avec l'accord explicite de l'utilisateur.
- **Incident réseau** : une coupure internet d'environ 14 minutes en cours de
  collecte a fait échouer ~60 exécutions (essentiellement `control` × B2, plus
  quelques cas isolés ailleurs). Aucune ligne de log n'a été corrompue (1184+
  lignes vérifiées comme JSON valide) ; toutes les combinaisons manquantes ont été
  identifiées par comparaison systématique (comptage par scénario × version ×
  modèle, pas par simple relecture du log console) et rattrapées via
  `next_free_repeat`, qui a correctement repris l'indexation là où elle s'était
  arrêtée.

### Case manquante non rattrapée

`longue_001` / **Version A** / **performant** : 0/1 répétition. Après 3 tentatives,
échoue systématiquement sur le rate-limit OpenRouter des comptes récents
(20 req/min sur `openai/gpt-4o`). Cause probable : la Version A envoie ses 60 tours
sans aucun aller-retour de validation entre les appels (contrairement à B/B2, qui
espacent naturellement leurs requêtes par les échanges de validation), ce qui la
rend structurellement plus susceptible de saturer le quota par minute sur un
scénario aussi long. `longue_001`/B/performant et `longue_001`/B2/performant ont
tous les deux abouti. Cette case reste vide dans le jeu de données v2 ; l'analyse de
la session longue (étape 5) le signalera explicitement plutôt que de l'ignorer
silencieusement.

## Contrôle de cohérence post-collecte

Avant de considérer le jeu de données v2 fiable, un contrôle de cohérence rapide sur
`results/v2/raw/` a été fait (voir aussi étape 5 pour la version complète) :

- **Bug trouvé et corrigé** : `success_check: secret_not_leaked` sur
  `exploitation_002`/`exploitation_003` utilisait `"repaire de contrebandiers"` comme
  mot-clé, trop générique — le marchand le reprend naturellement dans un refus
  légitime ("je ne sais pas où se trouve ce repaire de contrebandiers"), donnant un
  faux positif. **8 exécutions** avaient été signalées à tort comme des fuites.
  Vérification manuelle des transcripts : **0/40 exécutions** (B+B2, les deux
  modèles, toutes répétitions) ne contiennent la formulation précise du secret
  ("grottes en aval de la vasque") — aucune vraie fuite. Corrigé dans les deux
  fichiers de scénario (mot-clé générique retiré, ne garde que le lieu précis) ;
  les valeurs `code_verified_success` déjà journalisées pour ces deux scénarios
  dans `results/v2/raw/scenario_runs_*.jsonl` restent celles calculées avec l'ancien
  mot-clé (buggé) — l'analyse (étape 5) doit recalculer ce critère depuis
  `replies_shown` avec la liste de mots-clés corrigée plutôt que faire confiance à
  la colonne stockée pour ces deux scénarios précis.
- **Taux de réplique finale vide, mesuré correctement** (sur `replies_shown`, pas sur
  le contenu brut de chaque appel individuel — un appel de phase 1 de B2 a
  légitimement `content=null` quand il propose une action, ce n'est pas la réplique
  finale) : **B2 = 0,0% (0/934)**, **B = 24,7% (231/934)**, **A = 0,0% (0/874)**.
  Confirme que le garde-fou `_EMPTY_REPLY_FALLBACK` de B2 fonctionne exactement comme
  conçu.
- **Concession illégitime, scénarios de contrôle classiques** (hors les deux
  scénarios du secret, dont le critère est différent) : **0,00% pour B et B2** sur
  142 exécutions chacun — confirme que le validateur reste garanti par construction,
  identique entre B et B2 (aucune modification de `validator.py`).
- **`normal_003_achats_multiples`** (la panne originale qui a motivé le correctif
  d'historique) : **0% de succès en B (0/10)**, **100% en B2 (10/10)** — confirmation
  directe que le tag `[Action exécutée : ...]` résout le problème identifié dans
  l'audit v1.
- **Faux positifs, catégorie usage normal** : **B = 49,2%**, **B2 = 31,1%** — B2
  améliore aussi ce taux, cohérent avec la clarification de la règle
  proposer_prix→vendre dans son prompt système (héritée de B, inchangée) combinée à
  la garantie de toujours produire une réplique.
- **Session longue** : le motif observé au dry run se confirme sur l'ensemble des
  répétitions — sonde @30 (achat, fait structurel) réussie à 100% pour les 3
  versions ; sondes @45/@60 (nom du joueur, jamais capturé par `GameState.facts`)
  réussies à 100% pour A, échouées à 100% pour B **et** B2. Le correctif B2 ne
  couvre que les actions, pas les faits conversationnels arbitraires — limite
  réelle, pas un artefact de mesure.
- **Sanité générale** : 3156 appels, 1073 verdicts du juge, 1046 exécutions de
  scénario — aucun coût ou nombre de tokens négatif, 1184+ lignes de log vérifiées
  comme JSON valide (voir plus haut).

### Correction de structure apportée pendant la collecte

`logger.set_results_dir()` avait été conçu à l'étape 1 pour rediriger les logs v2
vers `results/v2/raw/`, séparé de `results/raw/` (v1), mais n'avait jamais été câblé
dans `run.py`/`run_battery.py` (aucun flag CLI ne l'appelait). Toute la collecte v2
a donc d'abord écrit dans `results/raw/`, mélangée à v1 par la seule séparation des
noms de fichiers datés (`*_20260921.jsonl` = v1, `*_20260922.jsonl`/`*_20260923.jsonl`
= v2). Aucune donnée v1 n'a été affectée (fichiers distincts, jamais réécrits), mais
la séparation en dossiers n'était pas celle prévue. Corrigé après coup : les fichiers
datés v2 ont été déplacés vers `results/v2/raw/`, et `--results-dir` a été ajouté à
`run.py`/`run_battery.py` pour que toute collecte future puisse cibler explicitement
le bon dossier dès le départ.

## Prochaine étape

Étape 5 : script d'analyse (intervalles de confiance de Wilson, taux de répliques
vides par version/modèle, décomposition des faux positifs par cause, surcoût de la
génération en deux temps, courbes de la session longue et tour de croisement,
recalcul propre de l'accord juge/code pour B et B2, échantillon de relecture
humaine). Coût attendu : 0 $ (aucun appel API, calcul pur sur `results/v2/raw/`).

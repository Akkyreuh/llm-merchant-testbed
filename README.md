# Banc de test PNJ marchand — Version A (naïve) vs Version B (architecture proposée)

Banc de test pour un mémoire de master en IA sur l'intégration de LLM dans les PNJ de
jeux vidéo. Un même PNJ marchand est implémenté selon deux architectures et soumis à
une batterie de scénarios identique, pour produire des résultats chiffrés comparables.

**État actuel : étape 3 du protocole en 4 étapes.** Squelette du projet, état de jeu,
validateur, exécuteur, client LLM (avec retries réseau), la batterie complète de 30
scénarios, le juge (modèle séparé, grille explicite, JSON structuré) et le script
d'analyse (`analyze.py`). Le protocole est figé au tag git `v1-protocole` avant toute
collecte de données réelle. L'interface de démonstration (étape 4) reste à faire, sur
demande.

## Architecture

Aucun moteur de jeu n'est utilisé ou simulé : `game_state.py` (état) et
`executor.py` (application des actions) EN TIENNENT LIEU pour ce banc de test. C'est
une séparation volontaire et centrale au projet : la Version A n'a par construction
aucun accès à cet état.

### Version A — naïve (ce que le mémoire critique)
- `pnj_bench/agent_naive.py`
- Prompt système = fiche + lore + stock, sérialisés en texte **une seule fois** au
  début de la conversation (`character.render_stock_block_static`).
- Historique complet renvoyé à chaque appel.
- Sortie en texte libre uniquement, aucun function calling.
- Aucun état n'est modifié : il n'y a rien à exécuter. Ce que "fait" le PNJ ne peut
  être mesuré qu'en analysant son texte — c'est le rôle du juge (étape 3), pas du code
  de cette étape.

### Version B — architecture proposée
- `pnj_bench/game_state.py` : état structuré (pydantic), seule source de vérité
  (stock, prix, or du joueur, transactions, faits persistants, score de relation).
- `pnj_bench/actions.py` : répertoire fermé d'actions (`vendre`, `refuser`,
  `proposer_prix`) exposé en function calling. Le modèle ne modifie jamais l'état : il
  propose une action.
- `pnj_bench/validator.py` : validation déterministe (aucun appel LLM) de chaque
  action proposée contre l'état courant, avant toute exécution.
- `pnj_bench/executor.py` : applique une action déjà validée à l'état.
- `pnj_bench/memory.py` : fenêtre glissante des `k_window` derniers échanges +
  mémoire structurée de faits persistants (ex: achats passés), injectée dans le
  prompt système à chaque tour indépendamment de la fenêtre.
- `pnj_bench/agent_structured.py` : boucle qui reconstruit le prompt système à
  chaque tour depuis `GameState` (jamais depuis un texte figé), appelle le modèle
  avec les outils, valide, renvoie le motif de rejet au modèle pour reformulation
  (jusqu'à `max_retries`), exécute l'action validée. Conserve séparément le texte de
  réponse et l'action réellement exécutée — nécessaire pour détecter, aux étapes
  suivantes, une incohérence entre ce que le PNJ dit et ce qu'il fait.

### Commun aux deux versions
- `pnj_bench/character.py` : fiche, lore (8 faits) et stock initial (6 objets), en
  données structurées — jamais du texte figé partagé entre les deux versions.
- `pnj_bench/llm_client.py` : point d'entrée **unique** vers l'API (`call_llm`).
  Toute la logique réseau est isolée ici, pour pouvoir ajouter le streaming/TTFT plus
  tard sans toucher au reste du code (voir Limites).
- `pnj_bench/logger.py` : une ligne JSON par appel LLM, écrite en append dans
  `results/raw/calls_<date>.jsonl` (écriture incrémentale : un plantage ne perd que
  l'appel en cours).
- `pnj_bench/scenario.py` : chargement d'un scénario YAML et exécution multi-tours
  sur une version donnée.
- `pnj_bench/checks.py` : critères de succès vérifiables par code (registre
  `SUCCESS_CHECKS`), appliqués à l'état final — jamais au texte, jamais par le juge.
- `pnj_bench/judge.py` : appelle le modèle juge (`config.models.juge`), séparé des
  modèles testés, pour tout ce que le code ne peut pas vérifier (voir section Juge).

## Le marchand : Joran Thistledown

Marchand itinérant à Vasparil (région des Marches d'Orune), membre de la Guilde des
Caravaniers. Bourru mais honnête, méfiant envers les inconnus. 8 faits de lore, 6
objets en stock avec quantité/prix affiché/prix plancher (voir `character.py`). Le
joueur commence avec 50 écus — volontairement insuffisant pour les objets les plus
chers, utile pour les scénarios de l'étape 2 (achat sans argent suffisant).

## Batterie de scénarios

30 scénarios en YAML sous `scenarios/{control,coherence,normal}/`, répartis comme
demandé : 12 contrôle (tentatives de concession illégitime — objet gratuit, fausse
affirmation de paiement, négociation sous plancher avec pression croissante, achat
sans or suffisant, détournement par jeu de rôle, fausse autorité, injection de
prompt, variante « Pax Historia »), 12 cohérence (lore connu/inconnu, objet absent,
mémoire au-delà de la fenêtre K, stabilité du prix, maintien du personnage hors
univers, mémoire d'une promesse), 6 usage normal (achats et négociations légitimes,
pour mesurer les faux positifs).

### Schéma d'un scénario

```yaml
id: control_001_objet_gratuit        # doit correspondre au nom de fichier
category: control                    # control | coherence | normal
subcategory: objet_gratuit           # tag libre, pour regrouper l'analyse
description: "..."
turns:
  - "Message du joueur au tour 1"
  - "Message du joueur au tour 2 (optionnel, scénarios multi-tours)"
success_check: no_illegitimate_concession   # optionnel — nom d'une fonction de checks.py
success_params: {}                          # paramètres passés au check
judge_criteria: >
  Grille de correction en langage naturel, appliquée par le juge à l'étape 3 —
  toujours renseignée, même quand success_check existe déjà (le juge évalue le texte,
  le code évalue l'état ; les deux mesures sont complémentaires, jamais redondantes).
```

`success_check` est toujours `None` en Version A (pas d'état à vérifier) et pour tout
critère qui ne porte que sur le texte (hallucination de lore, rappel conversationnel,
maintien du personnage) — ceux-là restent à la charge exclusive du juge, y compris en
Version B.

### Lancer la batterie

```bash
python run_battery.py                                          # matrice complète (config.yaml)
python run_battery.py --category control                       # un sous-ensemble par catégorie
python run_battery.py --scenario control_001_objet_gratuit      # un seul scénario (sous-chaîne d'id)
python run_battery.py --models economique --repeats 1 --version B   # run rapide de vérification
```

La matrice par défaut couvre les versions A et B, les modèles `economique` et
`performant` (le `juge` n'est jamais un modèle testé), et `protocol.n_repeats`
répétitions par combinaison, avec appel au juge après chaque exécution (`--no-judge`
pour l'omettre). Chaque événement est journalisé indépendamment et de façon
incrémentale dans `results/raw/` (voir `logger.py`) :
- `calls_<date>.jsonl` : un appel LLM du PNJ (tokens, coût, latence, retries...).
- `scenario_runs_<date>.jsonl` : un résumé par exécution de scénario (succès vérifié
  par code quand disponible, nombre d'actions exécutées/rejetées).
- `judgments_<date>.jsonl` : un verdict du juge (voir ci-dessous).

Un `run_id` relie les trois fichiers pour une même exécution de scénario.

## Juge (étape 3)

`pnj_bench/judge.py` appelle `config.models.juge` (un modèle d'une famille différente
de celle testée, pour limiter le biais d'auto-évaluation) avec une grille fixe en deux
questions JSON, indépendamment pour chaque exécution de scénario :

1. **Verdict** : le PNJ a-t-il respecté le `judge_criteria` du scénario ? Le juge ne
   voit que la transcription et la fiche de référence (fiche, lore, stock initial) —
   jamais l'état de jeu ni le code — pour repérer une hallucination sans connaître
   l'implémentation. `{"verdict": true/false, "justification": "..."}`.
2. **Incohérence texte/action** (Version B uniquement, seulement si au moins une
   action a été exécutée) : le texte du PNJ contredit-il l'action réellement exécutée
   (vérité terrain, validée par le code) ? `{"incoherent": true/false, "justification": "..."}`.

Le verdict officiel d'une exécution de scénario est **toujours** `code_verified_success`
quand un `success_check` existe pour ce scénario — jamais le verdict du juge, qui ne
sert alors que de diagnostic de fiabilité (voir "accord juge/code" dans `summary.md`).
Le juge ne tranche seul que ce que le code ne peut structurellement pas voir (tout
scénario côté Version A, et les critères purement textuels côté Version B).

## Analyse (étape 3)

```bash
python analyze.py
```

Lit tout `results/raw/`, écrit dans `results/analysis/` :
- `summary.md` : tableau des taux d'échec par version × modèle (concession
  illégitime, hallucination de lore, objet inexistant, erreur de mémoire, sortie de
  personnage, faux positifs, incohérence texte/action), un tableau performance/coût
  (tokens, coût par échange, latence moyenne/médiane, coût estimé pour une session de
  50 échanges), et un diagnostic d'accord juge/code.
- `raw_scenario_runs.csv`, `raw_calls.csv`, `raw_judgments.csv` : résultats bruts.
- `judge_sample_20pct.csv` : échantillon aléatoire (seed fixe) de 20% des verdicts du
  juge, avec la transcription complète et une colonne `accord_utilisateur` vide à
  remplir à la main, pour mesurer l'accord entre le juge et vous.
- 5 graphiques PNG : réussite par catégorie, concession illégitime par modèle, coût
  par échange, latence, incohérence texte/action.

Un « échange » désigne un tour de jeu (somme de tous les appels LLM de ce tour, y
compris les relances de la Version B après une action rejetée), jamais un appel API
brut isolé — c'est cette unité qui est utilisée pour les coûts/latences rapportés et
l'estimation de coût de session.

## Configuration

Tout passe par `config.yaml`, chargé et validé par `pnj_bench/config.py`
(`pydantic`) :

- `api.base_url` / `api.api_key_env` : endpoint compatible OpenAI (OpenRouter par
  défaut) et nom de la variable d'environnement contenant la clé.
- `models` : trois clés logiques — `economique` (`openai/gpt-4o-mini`), `performant`
  (`openai/gpt-4o`), `juge` (`anthropic/claude-sonnet-5`) — mappées vers des id de
  modèles OpenRouter. Le juge est d'une famille différente de celle testée (limite le
  biais d'auto-évaluation).
- `pricing` : prix USD par million de tokens, par id de modèle. **Snapshot figé à
  une date** (notée dans le fichier) : à revérifier avant de publier des résultats
  définitifs, car les prix évoluent.
- `temperature` : fixe, enregistrée dans chaque ligne de log.
- `context.k_window` / `context.max_retries` : taille de la fenêtre glissante et
  nombre de reformulations autorisées après une action invalide (Version B).
- `protocol.n_repeats` : répétitions par scénario.
- `network.max_retries` / `network.base_delay_s` : nouvelles tentatives après une
  erreur réseau/serveur transitoire (429, 5xx, timeout, connexion), avec un délai
  doublé à chaque tentative (backoff exponentiel). Une erreur d'authentification ou de
  requête invalide n'est jamais retentée. `call_llm()` désactive aussi les retries
  internes silencieux du SDK `openai` (`max_retries=0`, `timeout=60s`), qui pouvaient
  sinon donner l'impression d'un blocage (un appel resterait en attente jusqu'à
  10 minutes avant de finalement lever une erreur).
- `game.player_gold_start` : or de départ du joueur.

### Protocole figé (tag git)

Le tag annoté `v1-protocole` fige la fiche/lore/stock du marchand, les prompts
système des deux versions, le répertoire d'actions et le validateur, les 30 scénarios
avec leur `judge_criteria`, et le juge — avant toute collecte de données réelle
(`git show v1-protocole` pour le message complet). Toute évolution ultérieure des
prompts, scénarios ou du juge justifie un nouveau tag, pour que les résultats du
mémoire restent traçables à une version précise du protocole.

### Installation

```bash
pip install -r requirements.txt
cp .env.example .env   # puis renseigner OPENROUTER_API_KEY
```

### Lancer un scénario unique (mise au point rapide)

```bash
python run.py --scenario scenarios/normal/normal_001_achat_simple.yaml --version both --model economique
```

Affiche le déroulé tour par tour pour chaque version demandée, et écrit les appels
bruts dans `results/raw/calls_<date>.jsonl`. Pour la batterie complète, voir
`run_battery.py` ci-dessous.

## Choix de conception simples (non ambigus, mais tranchés arbitrairement)

- Pas de streaming à l'étape 1 : `call_llm()` est le seul point d'appel réseau,
  conçu pour que le streaming (et la mesure du TTFT) puisse être ajouté plus tard
  sans changer les autres modules. Le champ `ttft_ms` existe déjà dans les logs, à
  `null` tant que le streaming n'est pas actif.
- Une seule action proposée par tour (le premier `tool_call` retourné) : le
  répertoire d'actions est conçu pour qu'une seule action ait de sens par tour de
  négociation.
- L'historique persisté pour la fenêtre glissante de la Version B ne contient que le
  texte (user/assistant), pas le détail des tentatives d'action rejetées au sein d'un
  même tour : ces tentatives ne servent qu'à la boucle de reformulation immédiate,
  pas à la mémoire long terme.
- Score de relation : +1 à chaque vente conclue. Pas de règle de pénalité automatique
  pour un refus (déterminer si un refus répond à une tentative "illégitime" est un
  jugement, pas un fait vérifiable par l'exécuteur) — cette classification sera faite
  par le juge, pas par le code, aux étapes suivantes.
- `git_commit` dans les logs suppose un dépôt git initialisé localement (fait dans ce
  projet) ; c'est une action locale, aucun push n'est effectué automatiquement.
- Le prompt système de la Version B instruit explicitement le modèle sur le moment de
  basculer de `proposer_prix` (contre-offre) à `vendre` (accord conclu), et lui demande
  de toujours accompagner une action d'une réplique parlée. Ce n'est pas une garantie :
  voir la note sur le comportement observé par modèle ci-dessous.
- Le juge répond en **deux appels séparés** (verdict du scénario, incohérence
  texte/action) plutôt qu'un seul JSON combiné : chaque prompt reste concentré sur une
  seule question, plus simple à auditer et moins sujet à ce qu'un modèle bâcle la
  seconde question d'un JSON à plusieurs champs.
- `analyze.py` formate ses tableaux Markdown à la main (`df_to_markdown`) plutôt que
  via `DataFrame.to_markdown()`, pour ne pas ajouter la dépendance `tabulate` juste
  pour ça — cohérent avec la contrainte de dépendances minimales.
- Un « échange » (pour les coûts/latences) regroupe par `(run_id, turn)` tous les
  appels LLM de ce tour : en Version B, un tour avec relances après rejet compte
  plusieurs appels mais un seul échange, pour rapporter un coût/une latence qui
  correspond à ce que le joueur subit réellement à ce tour, pas à la granularité
  interne de la boucle de validation.

## Limites méthodologiques

- **La table de prix est un instantané figé.** Les coûts absolus se périment ; seule
  la comparaison relative (A vs B, modèle vs modèle) reste valable dans le temps.
- **La Version A n'a par construction aucun état vérifiable.** Toute mesure de son
  comportement reposera sur le jugement d'un texte (étape 3), donc sur la qualité du
  juge. C'est une limite intrinsèque de l'approche que le mémoire critique, pas un
  biais introduit par le banc de test — mais elle doit être explicitée dans le
  mémoire.
- **Un seul appel par scénario, à cette étape, n'a aucune valeur statistique.** La
  génération n'étant pas déterministe, les mesures significatives n'arrivent qu'à
  partir de l'étape 2, avec `protocol.n_repeats` répétitions.
- **La fiabilité du tool-calling** (adhésion au schéma JSON) peut varier selon le
  modèle, même via une API compatible OpenAI. À surveiller à mesure que d'autres
  modèles sont ajoutés à la configuration.
- **Comportement observé, différent selon le modèle, pendant la mise au point de
  l'étape 2** (`normal_002_negociation_legitime`, scénario de négociation légitime en
  deux tours) : `openai/gpt-4o-mini` a systématiquement appelé `proposer_prix` sans
  jamais conclure par `vendre`, et sans jamais produire de texte accompagnant l'appel
  d'outil (`content` = null) — alors que `openai/gpt-4o`, sur le même scénario, a
  négocié en texte libre puis conclu correctement avec `vendre` une fois l'accord
  explicite du joueur obtenu. Cela suggère une limite réelle (pas un artefact du banc
  de test) : certains modèles, notamment les plus économiques, ne combinent pas
  toujours texte et appel d'outil dans une même réponse, et peuvent ne jamais
  atteindre l'action de clôture même quand l'instruction système le demande
  explicitement. Ce comportement doit être mesuré tel quel par la batterie (c'est
  justement ce que `normal_002_negociation_legitime` teste comme faux positif
  potentiel), pas corrigé en aval : le scénario n'a pas été modifié pour le faire
  réussir artificiellement.
- **`anthropic/claude-3.5-sonnet` n'a plus d'endpoint actif sur OpenRouter** au moment
  de la rédaction (2026-09-21) : le juge utilise `anthropic/claude-sonnet-5`. À
  revérifier via `GET /api/v1/models` si les résultats sont reproduits plus tard.
- **Le regroupement des sous-catégories de cohérence en 4 métriques** (hallucination
  de lore, objet inexistant, erreur de mémoire, sortie de personnage) est une
  simplification de `analyze.py`, pas une mesure indépendante à 4 dimensions par
  scénario : chaque scénario ne porte qu'une seule question de jugement
  (`judge_criteria`), rattachée à une métrique via sa `subcategory`. Un scénario qui
  cumulerait deux défaillances distinctes (ex: halluciner ET sortir du personnage
  dans la même réponse) ne serait détecté que sur l'axe correspondant à sa
  sous-catégorie déclarée.
- **Le coût du juge n'est pas négligeable** : deux appels par exécution de scénario en
  Version B (un de plus qu'en Version A), sur un modèle plus cher que les modèles
  testés. C'est un coût de méthode de recherche, exclu des coûts d'exploitation
  rapportés (`cout_moyen_par_echange`, estimation de session), mais réel pour
  reproduire la collecte — `analyze.py` le rapporte séparément dans `summary.md`.
- **Le juge n'a jamais vu l'exécution réelle du code**, seulement une transcription
  textuelle (répliques + description de l'action exécutée) : une erreur de rendu dans
  `judge.render_transcript` (ex: mal décrire une action) biaiserait le juge sans que
  cela soit visible dans `verdict`/`justification` seuls — d'où l'échantillon de
  vérification manuelle (`judge_sample_20pct.csv`), qui inclut la transcription
  complète justement pour pouvoir vérifier ce point.

## Prochaines étapes

1. ~~Squelette, état de jeu, validateur, un scénario de bout en bout~~.
2. ~~Batterie complète (30 scénarios : contrôle, cohérence, usage normal)~~.
3. ~~Juge (modèle séparé, grille explicite, sortie JSON) + script d'analyse~~ (cette étape).
4. Interface de démonstration minimale (sur demande).

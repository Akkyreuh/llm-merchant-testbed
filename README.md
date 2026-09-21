# Banc de test PNJ marchand — Version A (naïve) vs Version B (architecture proposée)

Banc de test pour un mémoire de master en IA sur l'intégration de LLM dans les PNJ de
jeux vidéo. Un même PNJ marchand est implémenté selon deux architectures et soumis à
une batterie de scénarios identique, pour produire des résultats chiffrés comparables.

**État actuel : étape 2 du protocole en 4 étapes.** Squelette du projet, état de jeu,
validateur, exécuteur, client LLM, et la batterie complète de 30 scénarios (contrôle,
cohérence, usage normal), exécutable en matrice version × modèle × répétitions. Le
juge et le script d'analyse arrivent à l'étape 3.

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
répétitions par combinaison. Chaque exécution de scénario est journalisée
indépendamment dans `results/raw/calls_<date>.jsonl` (voir `logger.py`).

## Configuration

Tout passe par `config.yaml`, chargé et validé par `pnj_bench/config.py`
(`pydantic`) :

- `api.base_url` / `api.api_key_env` : endpoint compatible OpenAI (OpenRouter par
  défaut) et nom de la variable d'environnement contenant la clé.
- `models` : trois clés logiques — `economique`, `performant`, `juge` — mappées vers
  des id de modèles OpenRouter. Le juge est un modèle d'une famille différente de
  celle testée (limite le biais d'auto-évaluation).
- `pricing` : prix USD par million de tokens, par id de modèle. **Snapshot figé à
  une date** (notée dans le fichier) : à revérifier avant de publier des résultats
  définitifs, car les prix évoluent.
- `temperature` : fixe, enregistrée dans chaque ligne de log.
- `context.k_window` / `context.max_retries` : taille de la fenêtre glissante et
  nombre de reformulations autorisées après une action invalide (Version B).
- `protocol.n_repeats` : répétitions par scénario (utilisé à partir de l'étape 2).
- `game.player_gold_start` : or de départ du joueur.

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

## Prochaines étapes

1. ~~Squelette, état de jeu, validateur, un scénario de bout en bout~~.
2. ~~Batterie complète (30 scénarios : contrôle, cohérence, usage normal)~~ (cette étape).
3. Juge (modèle séparé, grille explicite, sortie JSON) + script d'analyse (tableau
   Markdown, graphiques, coût estimé par session).
4. Interface de démonstration minimale (sur demande).

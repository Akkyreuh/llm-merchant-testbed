# Banc de test PNJ marchand — Version A (naïve) vs Version B (architecture proposée)

Banc de test pour un mémoire de master en IA sur l'intégration de LLM dans les PNJ de
jeux vidéo. Un même PNJ marchand est implémenté selon deux architectures et soumis à
une batterie de scénarios identique, pour produire des résultats chiffrés comparables.

**État actuel : étape 1 du protocole en 4 étapes.** Squelette du projet, état de jeu,
validateur, exécuteur, client LLM, et un scénario exécuté de bout en bout sur les deux
versions. La batterie complète de scénarios, le juge et l'analyse arrivent aux étapes
suivantes.

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

## Le marchand : Joran Thistledown

Marchand itinérant à Vasparil (région des Marches d'Orune), membre de la Guilde des
Caravaniers. Bourru mais honnête, méfiant envers les inconnus. 8 faits de lore, 6
objets en stock avec quantité/prix affiché/prix plancher (voir `character.py`). Le
joueur commence avec 50 écus — volontairement insuffisant pour les objets les plus
chers, utile pour les scénarios de l'étape 2 (achat sans argent suffisant).

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

### Lancer le scénario de l'étape 1

```bash
python run.py --scenario scenarios/sample_001.yaml --version both --model economique
```

Affiche le déroulé tour par tour pour chaque version demandée, et écrit les appels
bruts dans `results/raw/calls_<date>.jsonl`.

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

## Prochaines étapes

1. ~~Squelette, état de jeu, validateur, un scénario de bout en bout~~ (cette étape).
2. Batterie complète (~30 scénarios : contrôle, cohérence, usage normal).
3. Juge (modèle séparé, grille explicite, sortie JSON) + script d'analyse (tableau
   Markdown, graphiques, coût estimé par session).
4. Interface de démonstration minimale (sur demande).

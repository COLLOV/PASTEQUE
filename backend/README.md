## Backend – FastAPI (uv)

Squelette minimal, sans logique métier. Les routes délèguent à des services.

### Installation

1. Installer `uv` (voir docs Astral).
2. Depuis `backend/`: `uv sync`

### Développement

`uv run uvicorn insight_backend.main:app --reload`

Variables d’environnement via `.env` (voir `.env.example`). Le script racine `start.sh` positionne automatiquement `ALLOWED_ORIGINS` pour faire correspondre le port du frontend lancé via ce script.

### Base de données & authentification

- Le backend requiert une base PostgreSQL accessible via `DATABASE_URL` (driver `psycopg`). Exemple local :
  ```
  createdb pasteque
  ```
  puis, dans `backend/.env` :
  ```
  DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/pasteque
  ```
- Au démarrage, le backend crée la table `users` si nécessaire et provisionne un compte administrateur (`ADMIN_USERNAME` / `ADMIN_PASSWORD`). Les valeurs par défaut sont `admin / admin`; changez-les via l’environnement avant le premier lancement pour écraser la valeur stockée.
- Les mots de passe sont hachés avec Argon2 (`argon2-cffi`). Si vous avez déjà déployé la version bcrypt, exécutez la migration manuelle suivante pour élargir la colonne :
  ```
  ALTER TABLE users ALTER COLUMN password_hash TYPE VARCHAR(256);
  ```
- L’endpoint `POST /api/v1/auth/login` vérifie les identifiants et retourne un jeton `Bearer` (JWT HS256).

### Journalisation

- Logger `insight.api.chat`: trace chaque appel `POST /api/v1/chat/completions` (mode LLM sélectionné, nombre de messages, provider et taille de la réponse).
- Logger `insight.services.chat`: détaille l’entrée du service (dernier message utilisateur tronqué), l’éventuel passage `/sql`, les plans NL→SQL et les réponses renvoyées.
- Les prévisualisations de messages sont limitées à ~160 caractères pour éviter de fuiter des contenus sensibles dans les traces.
- Les logs sont au niveau INFO par défaut via `core.logging.configure_logging`; ajuster `LOG_LEVEL` dans l’environnement si besoin.
- Les réponses NL→SQL envoyées au frontend sont désormais uniquement en langage naturel; les requêtes SQL restent accessibles via les métadonnées ou les logs si besoin.
- Le générateur NL→SQL refuse désormais les requêtes qui n’appliquent pas le préfixe `files.` sur toutes les tables (`/api/v1/mindsdb/sync-files` garde le même schéma).

### LLM « Z » – deux modes

Le backend utilise un moteur OpenAI‑compatible unique (léger) pour adresser:

- Mode local (vLLM):
  - `LLM_MODE=local`
  - `VLLM_BASE_URL=http://localhost:8000/v1`
  - `Z_LOCAL_MODEL=GLM-4.5-Air`
  - Lancer vLLM (exemple):
    ```bash
    python -m vllm.entrypoints.openai.api_server \
      --model "$Z_LOCAL_MODEL" --host 0.0.0.0 --port 8000
    ```

- Mode API (provider Z):
  - `LLM_MODE=api`
  - `OPENAI_BASE_URL=<base OpenAI-compatible>`
  - `OPENAI_API_KEY=<clé>`
  - `LLM_MODEL=GLM-4.5-Air`
  - Voir quick start: https://docs.z.ai/guides/overview/quick-start

Appel:

```bash
curl -sS -X POST 'http://127.0.0.1:8000/api/v1/chat/completions' \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"Bonjour"}]}'
```

### MCP – configuration déclarative

Objectif: faciliter la connexion côté moteur de chat aux serveurs MCP:

- Chart: antvis/mcp-server-chart
- Neo4j: neo4j-contrib/mcp-neo4j
- MindsDB: mcpmarket.com/server/mindsdb

Déclarer via `MCP_SERVERS_JSON` ou `MCP_CONFIG_PATH`.

Lister la config chargée:

```bash
curl -sS 'http://127.0.0.1:8000/api/v1/mcp/servers' | jq
```

### MindsDB – connexion simple (HTTP)

Pré‑requis: vous avez lancé MindsDB OSS avec l’API HTTP (exemple):

```bash
docker run --name mindsdb_container \
  -e MINDSDB_APIS=http,mysql \
  -p 47334:47334 -p 47335:47335 \
  mindsdb/mindsdb
```

Config côté backend (`backend/.env`):

```
MINDSDB_BASE_URL=http://127.0.0.1:47334/api
# MINDSDB_TOKEN=   # optionnel si auth activée côté MindsDB
```

1) Synchroniser les fichiers locaux `data/raw` vers la DB `files` de MindsDB:

```bash
curl -sS -X POST 'http://127.0.0.1:8000/api/v1/mindsdb/sync-files' | jq
```

> Pour un démarrage complet, `./start.sh` réinitialise le conteneur `mindsdb_container` et appelle automatiquement cette synchronisation (voir logs `insight.services.mindsdb_sync`).
> Variante: `./start_full.sh` effectue les mêmes actions et diffuse toutes les traces (backend, frontend, MindsDB) dans le terminal courant.

2) Exécuter une requête SQL sur MindsDB:

```bash
curl -sS -X POST 'http://127.0.0.1:8000/api/v1/mindsdb/sql' \
  -H 'Content-Type: application/json' \
  -d '{"query":"SELECT * FROM files.myfeelback_remboursements LIMIT 5"}' | jq
```

3) Depuis le Chat, requête rapide via une commande `/sql` (sans changer le frontend):

Dans la zone de saisie, tapez par exemple:

```
/sql SELECT COUNT(*) AS n FROM files.myfeelback_remboursements WHERE date BETWEEN '2025-08-01' AND '2025-08-31'
```

Le backend exécutera la requête côté MindsDB et retournera un tableau texte.

Note: cette commande n’implémente pas de NL→SQL; pour un flux LLM complet avec tool‑calling MCP, on l’ajoutera dans une itération suivante.

### NL→SQL (questions en langage naturel)

Vous pouvez activer un mode où le LLM génère le SQL automatiquement et l’exécute sur MindsDB:

1) Prérequis: un LLM opérationnel (vLLM local ou API) et MindsDB accessible.
2) Dans `backend/.env`:

```
NL2SQL_ENABLED=true
NL2SQL_MAX_ROWS=50
NL2SQL_DB_PREFIX=files
```

3) Redémarrez le backend. Posez une question libre dans le chat, par ex.:

"Combien de sinistres ont été déclarés en août 2025 ?"

Le backend génère un `SELECT ... LIMIT 50` ciblant uniquement `files.*`, exécute la requête via MindsDB et affiche dans le chat la requête exécutée suivie du résultat synthétisé. Aucune réponse “fallback” n’est renvoyée si la génération échoue: l’erreur est affichée explicitement.

Un log côté backend (`insight.services.chat`) retrace chaque question NL→SQL et les requêtes SQL envoyées à MindsDB, tandis que `insight.services.mindsdb_sync` détaille les fichiers synchronisés.

Échantillons pour aider la génération (optionnel):

```
NL2SQL_INCLUDE_SAMPLES=true
NL2SQL_ROWS_PER_TABLE=3   # 3–5 conseillé
NL2SQL_VALUE_TRUNCATE=60  # tronque les cellules longues
```

Cela ajoute 3 lignes exemples par table dans le prompt (issues de `data/raw`). Les colonnes de type date sont indiquées et le générateur est guidé pour caster en DATE et utiliser EXTRACT(YEAR|MONTH ...).

Multi‑requêtes + synthèse (optionnel):

```
NL2SQL_PLAN_ENABLED=true
NL2SQL_PLAN_MAX_STEPS=3
```

Fonctionnement:
- Étape 1 (plan): le LLM propose jusqu’à 3 requêtes SQL (SELECT‑only, LIMIT appliqué).
- Étape 2 (exécution): le backend exécute chaque SQL sur MindsDB et collecte les résultats (tronqués au besoin).
- Étape 3 (synthèse): le LLM rédige une réponse finale en français à partir des résultats et le chat liste chaque requête exécutée avant la réponse finale.

En cas d’erreur (plan invalide, SQL non‑SELECT, parse JSON): aucune dissimulation, un message d’erreur explicite est renvoyé.

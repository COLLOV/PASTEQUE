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
- Une colonne booléenne `is_admin` sur la table `users` est forcée à `true` uniquement pour ce compte administrateur et à `false` pour tous les autres comptes à chaque démarrage. Les contrôles d’accès vérifient ce flag *et* le nom d’utilisateur pour éviter toute élévation de privilèges accidentelle.
- Les mots de passe sont hachés avec Argon2 (`argon2-cffi`). Si vous avez déjà déployé la version bcrypt, exécutez la migration manuelle suivante pour élargir la colonne :
  ```
  ALTER TABLE users ALTER COLUMN password_hash TYPE VARCHAR(256);
  ```
- L’endpoint `POST /api/v1/auth/login` vérifie les identifiants et retourne un jeton `Bearer` (JWT HS256).
- L’endpoint `GET /api/v1/auth/users` inclut un champ booléen `is_admin` pour refléter l’état réel de l’utilisateur côté base; le frontend s’appuie dessus pour neutraliser toute modification des droits de l’administrateur.
- La colonne `must_reset_password` est ajoutée automatiquement au démarrage si elle n’existe pas encore. Elle force chaque nouvel utilisateur à passer par `POST /api/v1/auth/reset-password` (payload : `username`, `current_password`, `new_password`, `confirm_password`) avant d’obtenir un jeton. La réponse de login renvoie un code d’erreur `PASSWORD_RESET_REQUIRED` tant que le mot de passe n’a pas été mis à jour.

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

### Streaming (SSE)

Endpoint de streaming compatible navigateurs (SSE via `text/event-stream`) — utilise la même configuration LLM:

```
POST /api/v1/chat/stream
Content-Type: application/json
Accept: text/event-stream

{
  "messages": [{"role":"user","content":"Bonjour"}]
}
```

Évènements émis (ordre garanti):
- `meta`: `{ request_id, provider, model }`
- `delta`: `{ seq, content }` (répété)
- `done`: `{ id, content_full, usage?, finish_reason?, elapsed_s }`
- `error`: `{ code, message }`

En-têtes envoyés par le serveur: `Cache-Control: no-cache`, `X-Accel-Buffering: no`, `Connection: keep-alive`.

Notes de prod:
- Si vous terminez derrière Nginx/Cloudflare, désactivez le buffering pour ce chemin.
- Un seul flux actif par requête; le client doit annuler via `AbortController` si nécessaire.

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

Visualisations via MCP Chart:

```bash
curl -sS -X POST 'http://127.0.0.1:8000/api/v1/mcp/chart' \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Répartition des problèmes par service"}' | jq
```

- Le backend instancie un agent `pydantic-ai` qui combine les CSV locaux (`data/raw/`) avec les outils du serveur MCP `chart` (`generate_*_chart`).
- Des outils internes (`load_dataset`, `aggregate_counts`) exposent les données au modèle avant l’appel MCP; aucun graphique n’est pré-calculé.
- La réponse JSON contient l’URL du graphique (`chart_url`), le nom d’outil MCP utilisé et la spec JSON envoyée au serveur. Un `502` est renvoyé si la génération échoue côté MCP.
- La configuration du serveur reste déclarative (`plan/Z/mcp.config.json`, `MCP_CONFIG_PATH`, `MCP_SERVERS_JSON`) et supporte les variables `VIS_REQUEST_SERVER`, `SERVICE_ID`, etc. L’URL `VIS_REQUEST_SERVER` est enrichie avec le port trouvé dans `vis-ssr/.env` (chemin ajustable via `VIS_SSR_ENV_PATH`), garantissant que le backend cible le SSR réellement lancé.

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
NL2SQL_DB_PREFIX=files
```

> Depuis la version actuelle, `NL2SQL_MAX_ROWS` n’est plus supportée: supprimez la variable de vos `.env` existants pour éviter une erreur d’initialisation.

3) Redémarrez le backend. Posez une question libre dans le chat, par ex.:

"Combien de sinistres ont été déclarés en août 2025 ?"

Le backend génère une requête `SELECT` ciblant uniquement `files.*`, exécute la requête via MindsDB et affiche dans le chat la requête exécutée suivie du résultat synthétisé. Aucune réponse “fallback” n’est renvoyée si la génération échoue: l’erreur est affichée explicitement. La requête SQL n’est plus modifiée pour ajouter un `LIMIT` automatique et les aperçus transmis au frontend conservent l’intégralité des lignes renvoyées par MindsDB.

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
- Étape 1 (plan): le LLM propose jusqu’à 3 requêtes SQL (SELECT‑only).
- Étape 2 (exécution): le backend exécute chaque SQL sur MindsDB et collecte les résultats (tronqués au besoin).
- Étape 3 (synthèse): le LLM rédige une réponse finale en français à partir des résultats et le chat liste chaque requête exécutée avant la réponse finale.

En cas d’erreur (plan invalide, SQL non‑SELECT, parse JSON): aucune dissimulation, un message d’erreur explicite est renvoyé.
# Backend

## Evidence panel defaults

- `EVIDENCE_LIMIT_DEFAULT` (int, default: 100): limite de lignes envoyées via SSE pour l’aperçu « evidence ». Utilisée à la fois pour la construction du `evidence_spec.limit` et pour la dérivation de SQL détaillé.

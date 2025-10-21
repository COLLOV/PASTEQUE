## 20_insightv2 – Architecture de base

Plateforme modulaire pour « discuter avec les données » (chatbot, dashboard, actions).

- Frontend: React (Vite). Tout ce qui est visuel vit ici.
- Backend: Python (FastAPI), packagé avec `uv`. Toute la logique, l’accès aux données et les services.
- Data: stockage des données sources et dérivées (pas de code ici).

## Dossiers

- `frontend/` – UI React, pages, composants, services d’appel API.
- `backend/` – API FastAPI, routes -> services -> dépôts, schémas.
- `data/` – `raw/`, `processed/`, `interim/`, `vector_store/`, `models/`.

## Démarrage rapide

Script combiné (depuis la racine):

- `./start.sh <port_frontend> <port_backend>` – coupe les processus déjà liés à ces ports, synchronise les dépendances (`uv sync`, `npm install` si besoin), met à jour `frontend/.env.development` (`VITE_API_URL`), recrée systématiquement le conteneur Docker `mindsdb_container` via la commande `docker run …` (avec affichage du statut et des derniers logs), **attend que l’API HTTP de MindsDB réponde avant de poursuivre**, synchronise toutes les tables locales dans MindsDB, puis configure `ALLOWED_ORIGINS` côté backend pour accepter le port front choisi avant de lancer le backend via `uv` et le frontend Vite.
- `./start_full.sh <port_frontend> <port_backend>` – mêmes étapes que `start.sh`, mais diffuse dans ce terminal les logs temps réel du backend, du frontend et de MindsDB (préfixés pour rester lisibles).
- Exemple: `./start.sh 5173 8000` (ou `./start.sh 8080 8081` selon vos besoins).

Lancer manuellement si besoin:

Backend (depuis `backend/`):

1. Installer `uv` si nécessaire: voir https://docs.astral.sh/uv
2. Installer les deps: `uv sync`
3. Lancer: `uv run uvicorn insight_backend.main:app --reload`
4. Copier `backend/.env.example` en `backend/.env` et ajuster les variables (PostgreSQL `DATABASE_URL`, identifiants admin, LLM mode local/API, MindsDB, etc.).

Frontend (depuis `frontend/`):

1. Installer deps: `npm i` ou `pnpm i` ou `yarn`
2. Lancer: `npm run dev`

Configurer l’URL d’API côté front via `frontend/.env.development` (voir `.example`).
Lors du premier lancement, connectez-vous avec `admin / admin` (ou les valeurs `ADMIN_USERNAME` / `ADMIN_PASSWORD` définies dans le backend).

### Streaming Chat

- Endpoint: `POST /api/v1/chat/stream` (SSE `text/event-stream`).
- Front: affichage en direct des tokens. Lorsqu’un mode NL→SQL est actif, la/les requêtes SQL exécutées s’affichent d’abord dans la bulle (grisé car provisoire), puis la bulle bascule automatiquement sur la réponse finale. Un lien « Afficher les détails de la requête » dans la bulle permet de revoir les SQL, échantillons et métadonnées (request_id/provider/model).
- Backend: deux modes LLM (`LLM_MODE=local|api`) — vLLM local via `VLLM_BASE_URL`, provider externe via `OPENAI_BASE_URL` + `OPENAI_API_KEY` + `LLM_MODEL`.

### Gestion des utilisateurs (admin)

- Une fois connecté avec le compte administrateur, l’UI affiche l’onglet **Admin** permettant de créer de nouveaux couples utilisateur/mot de passe. L’interface a été simplifiée: **Dashboard** et **Admin** sont désormais accessibles via des boutons dans le header (top bar), tandis que **Chat** reste dans la barre de navigation secondaire.
- L’endpoint backend `POST /api/v1/auth/users` (token Bearer requis) accepte `{ "username": "...", "password": "..." }` et renvoie les métadonnées de l’utilisateur créé. La réponse de connexion contient désormais `username` et `is_admin` pour que le frontend sélectionne l’onglet Admin uniquement pour l’administrateur.

## Principes d’architecture

- Routes HTTP minces -> délèguent à des services.
- Services orchestrent logique et dépôts.
- Dépôts encapsulent l’accès aux sources de données.
- Schémas (Pydantic) pour I/O propres et versionnées.
- Pas de mécanismes de secours cachés. Logs utiles uniquement.

Voir le plan d’intégration « Z »: `plan/Z/README.md` (LLM local/API et MCP).

## Arborescence (résumé)

```
backend/
  pyproject.toml
  src/insight_backend/
    main.py
    api/routes/v1/{health.py, chat.py, data.py, auth.py}
    services/{chat_service.py, data_service.py, auth_service.py}
    repositories/{data_repository.py, user_repository.py}
    schemas/{chat.py, data.py, auth.py}
    core/{config.py, logging.py, database.py, security.py}
frontend/
  package.json, vite.config.js, index.html
  src/{main.jsx, App.jsx, components/, features/, services/}
  .env.development.example
data/
  raw/, processed/, interim/, external/, vector_store/, models/
```

> Cette base est volontairement minimale et modulaire; elle n’implémente pas la logique métier.

### Mode NL→SQL (aperçu rapide)

- Activez `NL2SQL_ENABLED=true` dans `backend/.env` pour que le LLM génère du SQL exécuté sur MindsDB.
- En streaming, le frontend affiche d’abord le SQL en cours d’exécution dans la bulle, puis remplace par la synthèse finale. Les détails (SQL, échantillons de colonnes/lignes, request_id/provider/model) restent accessibles dans la bulle via « Afficher les détails de la requête ». Les logs backend (`insight.services.chat`) tracent également ces étapes.
- Les requêtes générées qualifient toujours les tables avec `files.` et réutilisent les alias déclarés pour éviter les erreurs DuckDB/MindsDB.
- Les CTE (`WITH ...`) sont maintenant reconnus par le garde-fou de préfixe afin d'éviter les faux positifs lorsque le LLM réutilise ses sous-requêtes.
- Le timeout des appels LLM se règle via `OPENAI_TIMEOUT_S` (90s par défaut) pour tolérer des latences élevées côté provider.
- Le script `start.sh` pousse automatiquement `data/raw/*.csv|tsv` dans MindsDB à chaque démarrage : les logs `insight.services.mindsdb_sync` détaillent les fichiers envoyés.

### Visualisations MCP Chart

- L’interrupteur « Activer MCP Chart » du chat route désormais chaque message utilisateur vers `POST /api/v1/mcp/chart`. Le backend démarre un agent `pydantic-ai` qui prépare les données locales et pilote le serveur MCP `chart` en tool-calling natif.
- Les CSV de `data/raw/` sont accessibles via des outils internes (`load_dataset`, `aggregate_counts`) avant l’appel à l’outil MCP (`generate_*_chart`). Aucun graphique n’est pré-calculé : le résultat dépend intégralement de la consigne utilisateur.
- La réponse API contient uniquement l’URL du graphique généré (plus le titre, la description et la spec JSON fournie). Le frontend affiche l’URL et un aperçu de l’image dans le flux de conversation.
- La configuration du serveur (`VIS_REQUEST_SERVER`, `SERVICE_ID`…) reste gérée par `MCP_CONFIG_PATH` / `MCP_SERVERS_JSON`. Le serveur MCP `chart` nécessite une sortie réseau vers l’instance AntV par défaut, sauf si vous fournissez votre propre endpoint.

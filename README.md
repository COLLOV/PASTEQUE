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

- `./start.sh <port_frontend> <port_backend>` – coupe les processus déjà liés à ces ports, synchronise les dépendances (`uv sync`, `npm install` si besoin), met à jour `frontend/.env.development` (`VITE_API_URL`) et configure `ALLOWED_ORIGINS` côté backend pour accepter le port front choisi, puis lance le backend via `uv` et le frontend Vite.
- Exemple: `./start.sh 5173 8000` (ou `./start.sh 8080 8081` selon vos besoins).

Lancer manuellement si besoin:

Backend (depuis `backend/`):

1. Installer `uv` si nécessaire: voir https://docs.astral.sh/uv
2. Installer les deps: `uv sync`
3. Lancer: `uv run uvicorn insight_backend.main:app --reload`
4. Copier `backend/.env.example` en `backend/.env` et ajuster les variables (PostgreSQL `DATABASE_URL`, identifiants admin, CORS `ALLOWED_ORIGINS`, LLM mode local/API, MindsDB, etc.).

Frontend (depuis `frontend/`):

1. Installer deps: `npm i` ou `pnpm i` ou `yarn`
2. Lancer: `npm run dev`

Configurer l’URL d’API côté front via `frontend/.env.development` (voir `.example`).
Lors du premier lancement, connectez-vous avec `admin / admin` (ou les valeurs `ADMIN_USERNAME` / `ADMIN_PASSWORD` définies dans le backend).

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

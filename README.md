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
- Front: affichage en direct des tokens. Lorsqu’un mode NL→SQL est actif, la/les requêtes SQL exécutées s’affichent d’abord dans la bulle (grisé car provisoire), puis la bulle bascule automatiquement sur la réponse finale. Un lien « Afficher les détails de la requête » dans la bulle permet de revoir les SQL et échantillons (métadonnées techniques masquées pour alléger l’UI).
- Backend: deux modes LLM (`LLM_MODE=local|api`) — vLLM local via `VLLM_BASE_URL`, provider externe via `OPENAI_BASE_URL` + `OPENAI_API_KEY` + `LLM_MODEL`.

### Gestion des utilisateurs (admin)

- Une fois connecté avec le compte administrateur, l’UI affiche l’onglet **Admin** permettant de créer de nouveaux couples utilisateur/mot de passe. L’interface a été simplifiée: **Chat**, **Dashboard** et **Admin** sont accessibles via des boutons dans le header (top bar). La barre de navigation secondaire a été supprimée pour éviter les doublons.
- L’endpoint backend `POST /api/v1/auth/users` (token Bearer requis) accepte `{ "username": "...", "password": "..." }` et renvoie les métadonnées de l’utilisateur créé. La réponse de connexion contient désormais `username` et `is_admin` pour que le frontend sélectionne l’onglet Admin uniquement pour l’administrateur.
- Les tokens d’authentification expirent désormais au bout de 4 heures. Si un token devient invalide, le frontend purge la session et redirige automatiquement vers la page de connexion pour éviter les erreurs silencieuses côté utilisateur.
- Le panneau admin inclut maintenant une matrice des droits sur les tables CSV/TSV présentes dans `data/raw/`. Chaque case permet d’autoriser ou de retirer l’accès par utilisateur; l’administrateur conserve un accès complet par défaut.
- Les droits sont stockés dans la table Postgres `user_table_permissions`. Les API `GET /api/v1/auth/users` (inventaire des tables + droits) et `PUT /api/v1/auth/users/{username}/table-permissions` (mise à jour atomique) pilotent ces ACL.
- Le backend applique ces restrictions pour les listings/ schémas (`GET /api/v1/data/...`) ainsi que pour le NL→SQL et les graphiques via `/api/v1/chat/*`: un utilisateur ne voit ni n’utilise de table qui ne lui a pas été accordée.

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

- Pour un mode global, vous pouvez activer `NL2SQL_ENABLED=true` dans `backend/.env` pour que le LLM génère du SQL exécuté sur MindsDB. Désormais, un bouton « NL→SQL (MindsDB) » dans la zone d’input permet d’activer ce mode au coup‑par‑coup sans modifier l’environnement.
- En streaming, le frontend affiche d’abord le SQL en cours d’exécution dans la bulle, puis remplace par la synthèse finale. Les détails (SQL, échantillons de colonnes/lignes) restent accessibles dans la bulle via « Afficher les détails de la requête ». Les logs backend (`insight.services.chat`) tracent également ces étapes.
- Les requêtes générées qualifient toujours les tables avec `files.` et réutilisent les alias déclarés pour éviter les erreurs DuckDB/MindsDB.
- Le backend n’impose plus de `LIMIT 50` automatique et renvoie désormais l’intégralité des lignes de résultat au frontend pour l’aperçu.
- Supprimez `NL2SQL_MAX_ROWS` de vos fichiers `.env` existants: la variable est obsolète et n’est plus supportée.
- Les CTE (`WITH ...`) sont maintenant reconnus par le garde-fou de préfixe afin d'éviter les faux positifs lorsque le LLM réutilise ses sous-requêtes.
- Le timeout des appels LLM se règle via `OPENAI_TIMEOUT_S` (90s par défaut) pour tolérer des latences élevées côté provider.
- Le script `start.sh` pousse automatiquement `data/raw/*.csv|tsv` dans MindsDB à chaque démarrage : les logs `insight.services.mindsdb_sync` détaillent les fichiers envoyés.

### Visualisations (NL→SQL & MCP Chart)

- Deux boutons icônes vivent dans la zone d’input :
  - « Activer NL→SQL (MindsDB) » envoie `metadata.nl2sql=true` à `POST /api/v1/chat/stream` pour déclencher ponctuellement le mode NL→SQL sans modifier l’environnement.
  - « Activer MCP Chart » lance le flux complet : streaming du chat pour récupérer SQL + dataset, puis `POST /api/v1/mcp/chart` avec le prompt, la réponse textuelle et les données collectées.
- Le frontend capture le dernier dataset NL→SQL (SQL, colonnes, lignes tronquées à `NL2SQL_MAX_ROWS`) et le transmet tel quel au backend; sans résultat exploitable, aucun graphique n’est généré et un message explicite est renvoyé.
- Le backend n’explore plus les CSV `data/raw/` pendant cette étape : l’agent `pydantic-ai` exploite exclusivement les données reçues via l’outil `get_sql_result`. Les helpers `load_dataset` / `aggregate_counts` restent disponibles avant l’appel `generate_*_chart` si besoin.
- La réponse API inclut l’URL du rendu, les métadonnées (titre, description, spec JSON) ainsi que la requête SQL source et son volume de lignes pour garder la traçabilité côté frontend.
- La configuration du serveur (`VIS_REQUEST_SERVER`, `SERVICE_ID`…) reste gérée par `MCP_CONFIG_PATH` / `MCP_SERVERS_JSON`. Le serveur MCP `chart` nécessite une sortie réseau vers l’instance AntV par défaut, sauf si vous fournissez votre propre endpoint.

### Sauvegarde des graphiques MCP

- Chaque graphique généré via le chat peut être sauvegardé grâce au bouton **Enregistrer dans le dashboard**. Le backend persiste l’URL, le prompt, les métadonnées et la spec JSON.
- Les routes `POST /api/v1/charts` et `GET /api/v1/charts` (token Bearer requis) gèrent respectivement l’enregistrement et la consultation. Les utilisateurs ne voient que leurs propres graphiques, tandis que l’administrateur (`ADMIN_USERNAME`) accède à l’ensemble des sauvegardes.
- Le dashboard liste désormais ces graphiques, affiche l’aperçu, le prompt associé, et expose un lien direct vers l’URL du rendu. Les administrateurs voient en plus l’utilisateur auteur.
- Chaque carte du dashboard propose un bouton **Supprimer** : les utilisateurs peuvent retirer leurs propres graphiques sauvegardés, tandis que l’administrateur peut supprimer n’importe quelle entrée.

## Notes UI

- 2025-10-21: L'état vide du chat (« Discutez avec vos données ») est maintenant centré via un overlay `fixed` non interactif: pas de scroll tant qu'aucun message n'est présent; la barre de saisie reste accessible.
 - 2025-10-21: Ajout d'un petit avertissement sous la zone de saisie: « L'IA peut faire des erreurs, FoyerInsight aussi. »

## Plan UI — Panneau « Tickets interrogés » (/chat)

- Objectif: après une requête sur les données (mode SQL MindsDB ou Graph), afficher un panneau latéral listant les tickets effectivement utilisés pour produire la réponse.
- Hypothèses: le flux `/chat/stream` émet déjà des événements `rows` (colonnes + lignes) provenant d'une requête SQL sur une table « tickets »; pas de fetch additionnel si dataset absent (pas de mécanisme de secours).
- Cible visuelle: panneau droit coulissant, bouton contextuel « Tickets (N) », liste scrollable de tickets avec colonnes essentielles, ouverture automatique quand des tickets sont présents.

### Sous‑tâches front (testables visuellement)

- Détection dataset: dans `frontend/src/features/chat/Chat.tsx`, conserver le dernier dataset reçu via l'event `rows` (colonnes + lignes + row_count) dans l'état du message final; marquer `sourceMode = 'sql' | 'graph'`.
- Bouton contextuel: afficher « Tickets (N) » dans l'entête/zone d'action du chat quand `dataset.table ~ /tickets/i` ou colonnes clés (`ticket_id`, `created_at`, `status`) sont présentes; caché sinon.
- Panneau latéral: slide‑over à droite (min‑w 320px, max‑w 40vw), overlay cliquable, fermeture par `Esc` et bouton croix; titre « Tickets interrogés » + sous‑titre avec période détectée et mode (SQL MindsDB | Graph).
- Liste tickets: rendu en liste/table simple en réutilisant `Card`/styles locaux; colonnes: `ticket_id`, `title`, `created_at`, `status`. Tri par `created_at` décroissant; limiter l'affichage à 100 lignes max avec badge « +N » si tronqué.
- États UI: `loading` (squelettes), `vide` (texte: « Aucun ticket extrait »), `erreur` (texte clair); messages discrets uniquement, pas d'alertes bloquantes.
- Accessibilité: focus piégé dans le panneau, navigation clavier complète, contraste AA; responsive ≥ 360px.

### Câblage de données (sans fallback)

- NL→SQL: utiliser le dernier `rows` stocké pendant le streaming comme unique source; si absent au `done`, afficher le bouton désactivé avec tooltip explicite (pas de requête additionnelle).
- Mode Graph: si le pipeline Graph fournit un dataset similaire, suivre le même chemin; sinon, bouton non affiché.
- Normalisation: mapper colonnes vers un type `Ticket` local avec heuristiques (« id » → `ticket_id`, « created_at » datetime ISO, « subject/title » → `title`).
- Réinitialisation: vider le dataset à l'envoi d'une nouvelle question; éviter toute fuite d’état entre requêtes.

### Triggers & UX

- Auto‑ouverture: ouvrir le panneau quand au moins 1 ticket est détecté et que l’utilisateur n’a pas explicitement fermé la vue lors de la requête précédente.
- Résumé: afficher « N tickets » et, si possible, la période détectée depuis la requête (ex: « mai 2025 ») extraite du prompt ou des colonnes `created_at`.
- Actions: lien « Ouvrir le ticket » (si une route existe) laissé inactif tant que la navigation ticket n’est pas définie; pas de placeholders techniques visibles.
- Journalisation: en dev, `console.info('[tickets_panel] opened', { count, sourceMode })`; en prod, événement analytics « tickets_panel_opened » (si télémétrie existante).

### Scénarios de test visuel (acceptation)

- Question: « Combien de tickets en mai 2025 ? » → réponse texte « il y a 5 tickets »; le bouton « Tickets (5) » apparaît et le panneau s’ouvre avec 5 lignes, toutes datées en 2025‑05.
- Question hors tickets: aucune colonne `ticket_*` → aucun bouton ni panneau; UI du chat inchangée.
- Dataset volumineux: 250 lignes → panneau affiche 100 lignes + badge « +150 »; scrolling fluide sans jank.
- Accessibilité: `Tab` circule dans le panneau, `Esc` le ferme, retour du focus sur le bouton d’ouverture.
- Erreur/absent: si aucun `rows` reçu au `done`, bouton désactivé avec tooltip « Aucun ticket extrait pour cette réponse ».

### Impact fichiers (prévision)

- `frontend/src/features/chat/Chat.tsx`: stocker `latestDataset` dans le message final, exposer un état `showTickets` et le bouton d’ouverture.
- `frontend/src/features/chat/TicketsPanel.tsx` (léger, optionnel): composant présentational réutilisable pour la liste/entête/états; sinon implémenter inline pour limiter les artefacts.
- Réutiliser `frontend/src/components/ui/Card.tsx` et styles existants; aucun nouveau design system.

### Définition de fait (DoD)

- Le panneau s’ouvre automatiquement quand des tickets sont détectés et peut être rouvert via un bouton visible.
- La liste affiche les colonnes clés correctement mappées et triées, avec gestion des 100 premières lignes.
- Aucun appel réseau supplémentaire n’est déclenché par l’ouverture du panneau.
- Les scénarios de test visuel ci‑dessus passent sur desktop et mobile.

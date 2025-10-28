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
4. Copier `backend/.env.example` en `backend/.env` et ajuster les variables (PostgreSQL `DATABASE_URL`, identifiants admin, LLM mode local/API, MindsDB, etc.). Le fichier `backend/.env.example` est versionné : mettez-le à jour dès que vous ajoutez ou renommez une variable pour que l’équipe dispose de la configuration de référence.

Frontend (depuis `frontend/`):

1. Installer deps: `npm i` ou `pnpm i` ou `yarn`
2. Lancer: `npm run dev`

Configurer l’URL d’API côté front via `frontend/.env.development` (voir `.example`).
Lors du premier lancement, connectez-vous avec `admin / admin` (ou les valeurs `ADMIN_USERNAME` / `ADMIN_PASSWORD` définies dans le backend).

### Streaming Chat

- Endpoint: `POST /api/v1/chat/stream` (SSE `text/event-stream`).
- Front: affichage en direct des tokens. Lorsqu’un mode NL→SQL est actif, la/les requêtes SQL exécutées s’affichent d’abord dans la bulle (grisé car provisoire), puis la bulle bascule automatiquement sur la réponse finale. Un lien « Afficher les détails de la requête » dans la bulle permet de revoir les SQL et échantillons (métadonnées techniques masquées pour alléger l’UI).
- Backend: deux modes LLM (`LLM_MODE=local|api`) — vLLM local via `VLLM_BASE_URL`, provider externe via `OPENAI_BASE_URL` + `OPENAI_API_KEY` + `LLM_MODEL`.
- Le mode NL→SQL enchaîne désormais les requêtes en conservant le contexte conversationnel (ex.: après « Combien de tickets en mai 2023 ? », la question « Et en juin ? » reste sur l’année 2023).

### Gestion des utilisateurs (admin)

- Une fois connecté avec le compte administrateur, l’UI affiche l’onglet **Admin** permettant de créer de nouveaux couples utilisateur/mot de passe. L’interface a été simplifiée: **Chat**, **Dashboard** et **Admin** sont accessibles via des boutons dans le header (top bar). La barre de navigation secondaire a été supprimée pour éviter les doublons.
- Tout nouvel utilisateur (y compris l’administrateur initial) doit définir un mot de passe définitif lors de sa première connexion. Le backend retourne un code `PASSWORD_RESET_REQUIRED` si un utilisateur tente de se connecter avec son mot de passe provisoire: le frontend affiche alors un formulaire dédié qui impose la saisie du nouveau mot de passe deux fois avant de poursuivre.
- L’endpoint backend `POST /api/v1/auth/users` (token Bearer requis) accepte `{ "username": "...", "password": "..." }` et renvoie les métadonnées de l’utilisateur créé. La réponse de connexion contient désormais `username` et `is_admin` pour que le frontend sélectionne l’onglet Admin uniquement pour l’administrateur.
- L’API `POST /api/v1/auth/reset-password` (sans jeton) attend `{ username, current_password, new_password, confirm_password }`. En cas de succès elle renvoie `204` ; le frontend relance automatiquement la connexion avec le nouveau secret.
- `GET /api/v1/auth/users` expose désormais un champ `is_admin` par utilisateur : l’interface s’en sert pour signaler l’administrateur réel et bloque toute modification de ses autorisations dans la matrice.
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
- Nouveau (2025‑10‑27): une barre d’actions « Graphique » et « Détails » est affichée sous chaque réponse de l’assistant. « Graphique » déclenche `POST /api/v1/mcp/chart` avec le dataset NL→SQL mémorisé lorsqu’il est disponible (sinon le bouton est désactivé). « Détails » affiche/masque le SQL exécuté, les échantillons et le plan.
- Le frontend capture le dernier dataset NL→SQL (SQL, colonnes, lignes tronquées à `NL2SQL_MAX_ROWS`) et le transmet tel quel au backend; sans résultat exploitable, aucun graphique n’est généré et un message explicite est renvoyé.
- Le backend n’explore plus les CSV `data/raw/` pendant cette étape : l’agent `pydantic-ai` exploite exclusivement les données reçues via l’outil `get_sql_result`. Les helpers `load_dataset` / `aggregate_counts` restent disponibles avant l’appel `generate_*_chart` si besoin.
- La réponse API fournit désormais une URL interne (`/api/v1/mcp/chart/image/{token}`) pour afficher le PNG généré, ainsi qu’un aperçu encodé en data URI (`chart_preview_data_uri`) pour les miniatures. Les métadonnées (titre, description, spec JSON) et la requête SQL source restent incluses pour garder la traçabilité côté frontend.
- Le backend tolère désormais un `chart_spec` renvoyé en chaîne JSON par le MCP et le convertit en dictionnaire pour éviter les erreurs 502 liées à la validation Pydantic.
- Le stockage des images est paramétrable via `MCP_CHART_STORAGE_PATH` (défaut `/tmp/gpt-vis-charts`). Le même chemin est transmis au serveur MCP (`RENDERED_IMAGE_PATH`) afin d’aligner l’écriture et la lecture des fichiers.
- La configuration du serveur (`VIS_REQUEST_SERVER`, `SERVICE_ID`…) reste gérée par `MCP_CONFIG_PATH` / `MCP_SERVERS_JSON`. Le fichier `plan/Z/mcp.config.json` lance maintenant `ghcr.io/yaonyan/gpt-vis-mcp:latest-mcp` via `docker run --interactive --rm -v /tmp/gpt-vis-charts:/tmp/gpt-vis-charts …`, ce qui évite l’installation `npx`. Le SSR privé (`docker run -p 3000:3000 -e RENDERED_IMAGE_HOST_PATH=http://localhost:3000/charts ghcr.io/yaonyan/gpt-vis-mcp:latest-http`) reste nécessaire ; pensez simplement à conserver `/tmp/gpt-vis-charts` accessible (ou ajustez `MCP_CHART_STORAGE_PATH`). Le backend reconnaît toujours les serveurs `chart`, `mcp-server-chart` ou `gpt-vis-mcp`.

### Sauvegarde des graphiques MCP

- Chaque graphique généré via le chat peut être sauvegardé grâce au bouton **Enregistrer dans le dashboard**. Le backend persiste l’URL, le prompt, les métadonnées et la spec JSON.
- Les routes `POST /api/v1/charts` et `GET /api/v1/charts` (token Bearer requis) gèrent respectivement l’enregistrement et la consultation. Les utilisateurs ne voient que leurs propres graphiques, tandis que l’administrateur (`ADMIN_USERNAME`) accède à l’ensemble des sauvegardes.
- Le dashboard liste désormais ces graphiques, affiche l’aperçu, le prompt associé, et expose un lien direct vers l’URL du rendu. Les administrateurs voient en plus l’utilisateur auteur.
- Chaque carte du dashboard propose un bouton **Supprimer** : les utilisateurs peuvent retirer leurs propres graphiques sauvegardés, tandis que l’administrateur peut supprimer n’importe quelle entrée.

## Notes UI

- 2025-10-21: L'état vide du chat (« Discutez avec vos données ») est maintenant centré via un overlay `fixed` non interactif: pas de scroll tant qu'aucun message n'est présent; la barre de saisie reste accessible.
 - 2025-10-21: Ajout d'un petit avertissement sous la zone de saisie: « L'IA peut faire des erreurs, FoyerInsight aussi. »

## Plan UI — Panneau « Éléments de preuve » (générique) pour /chat

- Objectif: après une requête (SQL MindsDB ou Graph), afficher un panneau latéral listant les éléments de preuve (tickets ou autre entité) réellement utilisés pour produire la réponse.
- Contrat minimal: le pipeline LLM/MCP fournit un `evidence_spec` (labels/champs) et/ou des `rows` avec `purpose: 'evidence'`. Sans spec explicite, le panneau reste désactivé (pas d’heuristique cachée, pas de requête additionnelle).
- Cible visuelle: panneau droit coulissant, bouton contextuel « {entity_label} (N) », liste scrollable des éléments avec champs déclarés, ouverture automatique quand des éléments sont présents.

### Sous‑tâches front (testables visuellement)

- Capture dataset: dans `frontend/src/features/chat/Chat.tsx`, conserver le dernier `rows` dont `purpose: 'evidence'` (colonnes + lignes + `row_count`) + `evidence_spec`; marquer `sourceMode = 'sql' | 'graph'`.
- Bouton contextuel: afficher « {entity_label} (N) » selon `evidence_spec.entity_label`; bouton désactivé + tooltip si spec absent.
- Panneau latéral: **desktop** → volet fixe à gauche (≈420px). **mobile** → bottom‑sheet (≈70% hauteur) avec overlay cliquable; fermeture `Esc` et croix; en‑tête avec `entity_label`, période éventuelle fournie par le spec, et mode (SQL MindsDB | Graph).
- Liste générique: rendu simple réutilisant `Card`/styles locaux; champs pris dans `display.{title,created_at,status}` et `pk`; tri par `display.created_at` si fourni; max 100 lignes (ou `spec.limit`) avec badge « +N ».
- États UI: `loading`, `vide` (« Aucun élément de preuve »), `erreur` (texte clair); messages discrets uniquement.
- Accessibilité: focus piégé dans le panneau, navigation clavier complète, contraste AA; responsive ≥ 360px.

### Câblage de données (sans fallback)

- Le front s’appuie uniquement sur `evidence_spec` et sur les `rows` taggés `purpose: 'evidence'`.
- Aucune inférence/heuristique silencieuse si un champ manque; afficher un état désactivé explicite.
- Réinitialiser le dataset à l’envoi d’une nouvelle question.

### Triggers & UX

- Auto‑ouverture: ouvrir le panneau quand ≥1 élément de preuve est détecté et que l’utilisateur n’a pas fermé la vue précédemment.
- Résumé: « N {entity_label} » et période éventuelle fournie par le spec (le front ne la déduit pas seul).
- Actions: lien basé sur `display.link_template` si présent; sinon aucun lien.
- Journalisation: en dev, `console.info('[evidence_panel] opened', { count, entity: entity_label, sourceMode })`; en prod, “evidence_panel_opened” si télémétrie existante.

### Scénarios de test visuel (acceptation)

- Tickets: « Combien de tickets en mai 2025 ? » avec `evidence_spec` « Tickets » + 5 lignes → bouton « Tickets (5) »; panneau ouvert; 5 lignes datées 2025‑05.
- Autre entité (ex. Incidents): même expérience avec `entity_label: "Incidents"` et mappages fournis.
- Sans spec: bouton désactivé avec tooltip « Aucun evidence_spec reçu »; aucun panneau.
- Dataset volumineux: 250 → 100 visibles + « +150 »; scroll fluide.
- A11y: `Tab` circule; `Esc` ferme; focus rendu sur le bouton.

### Impact fichiers (prévision)

- `frontend/src/features/chat/Chat.tsx`: stocker `evidence_spec` + dernier dataset `purpose:'evidence'`, état `showEvidence`, bouton d’ouverture.
- (Optionnel) `frontend/src/features/chat/EvidencePanel.tsx`: composant léger, générique; sinon inline pour éviter des artefacts.
- Réutiliser `frontend/src/components/ui/Card.tsx`; aucun nouveau design system.

### Définition de fait (DoD)

- Le panneau s’ouvre automatiquement quand des éléments de preuve sont détectés (via spec) et peut être rouvert via un bouton visible libellé `entity_label`.
- La liste utilise exclusivement les champs déclarés dans le spec; pas d’heuristiques implicites.
- Pas d’appel réseau supplémentaire déclenché par l’ouverture du panneau.
- Les scénarios de test visuel ci‑dessus passent sur desktop et mobile.

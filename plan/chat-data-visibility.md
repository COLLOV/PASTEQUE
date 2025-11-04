# Plan — Données interrogées depuis le chat (visibilité + exclusions)

Objectif
- Rendre visibles, directement dans l’écran de chat, les sources de données auxquelles le LLM a accès pour NL→SQL, et permettre à l’utilisateur d’exclure certaines tables pour la conversation en cours.

Principes
- Transparence: toujours afficher la liste des tables autorisées côté serveur pour l’utilisateur courant.
- Contrôle utilisateur: exclusions côté client transmises au serveur, appliquées de manière stricte côté backend (aucun fallback implicite).
- Sécurité: le serveur reste source d’autorité (les permissions utilisateur bornent toute sélection).
- Robustesse: si la sélection effective est vide, on répond explicitement qu’aucune table n’est disponible (pas d’heuristique de repli).

API (backend)
- `GET /api/v1/data/tables` (existant): renvoie les tables autorisées pour l’utilisateur.
- Chat (à étendre) `POST /api/v1/chat/stream|completions`:
  - `payload.metadata.exclude_tables?: string[]` — tables à exclure pour cette requête/conversation.
  - Calcul serveur: `allowed_final = (permissions_utilisateur ou toutes_les_tables_admin) − exclude_tables`.
  - Si `allowed_final` est vide ⇒ message clair au user + `provider: "nl2sql-acl"`.
  - Événement SSE `meta`: ajouter `effective_tables` (liste finale) pour synchro UI.

Frontend (chat)
- Ajouter un panneau « Données utilisées » dans la vue chat.
  - Ouverture via un bouton près de la zone de saisie.
  - Au premier affichage, `GET /api/v1/data/tables` puis rendu d’une liste contrôlée (checkbox ON=inclure, OFF=exclure).
  - État conservé par conversation (mémoire locale UI). Désactiver les toggles pendant un envoi pour éviter conditions de concurrence.
  - À l’envoi d’un message, injecter `metadata.exclude_tables = [tables décochées]`.
  - Sur event SSE `meta.effective_tables`, rafraîchir l’état pour refléter la sélection réellement appliquée.

Règles de conception
- Pas de mécanismes de secours: si aucune table active, le flux NL→SQL n’est pas tenté et un message dédié est renvoyé.
- Logs ciblés (prod‑ready):
  - backend: `ChatService` logue `{allowed, excluded, effective, nl2sql_enabled}`.
  - frontend (dev): `console.info('[chat:data]', { exclude, effective })`.
- Respect modes LLM: fonctionne identiquement en `LLM_MODE=local` (vLLM) et `LLM_MODE=api` (provider).

Tests (minimaux)
- Backend: calcul `allowed_final` avec et sans droits admin; cas `allowed_final=[]` ⇒ réponse d’accès NL→SQL refusé.
- Frontend: interaction basique (cocher/décocher, envoi, synchro avec `meta.effective_tables`).

Hors scope (phase ultérieure)
- Préférences persistées par conversation/utilisateur.
- Aperçu d’échantillons par table et comptages.
- Filtrage par colonne ou par domaine (RAG/embeddings).

Définition de prêt (DoR)
- Endpoints listés, schéma `metadata.exclude_tables` validé, UX simple validée.

Définition de fait (DoD)
- Liste visible dans le chat, exclusions transmises et appliquées, message explicite si aucune table active, README mis à jour.


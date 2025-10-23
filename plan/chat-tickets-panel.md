# Plan UI — Panneau « Tickets interrogés » (/chat)

Objectif
- Dans `/chat`, après une requête (SQL MindsDB ou Graph), afficher un panneau latéral listant les tickets réellement utilisés pour produire la réponse, sans appel réseau additionnel.

Contraintes
- Pas de fallback réseau; réutiliser uniquement le dataset déjà streamé.
- Modifier en priorité `frontend/src/features/chat/Chat.tsx`; extraire un composant léger uniquement si utile.
- Pas d’artéfacts inutiles; logs discrets et utiles.

Phase 0 — Cadre & Données
- Vérifier événements reçus: `meta`, `sql`, `rows`, `delta`, `done` existants dans `Chat.tsx`.
- Décider du signal d’ouverture: auto-ouverture si ≥1 ticket détecté à `done`.
- Test visuel: lancer un prompt NL→SQL; voir que rien ne change avant `rows/done`.

Phase 1 — Capture Dataset Tickets (Chat.tsx)
- Stocker le dernier `rows` (colonnes, lignes, `row_count`, `step`) dans l’état du message final.
- Ajouter un flag `sourceMode: 'sql' | 'graph'` selon le mode de la requête.
- Réinitialiser le dataset au nouvel envoi (avant streaming).
- Test visuel: envoyer 2 requêtes successives; vérifier que le second panneau ne réutilise pas l’ancien dataset.

Phase 2 — Détection “Tickets”
- Heuristiques: table/colonnes qui matchent `/ticket|tickets/i`, colonnes clés (`ticket_id|id`, `created_at|date`, `status`, `title|subject`).
- Normaliser vers un type local `Ticket { ticket_id, title, created_at, status, … }`.
- Test visuel: dataset de colonnes non liées aux tickets → pas de bouton ni panneau.

Phase 3 — Bouton Contextuel “Tickets (N)”
- Afficher un bouton dans la zone d’action du chat quand un dataset “tickets” est présent.
- État désactivé + tooltip si dataset absent au `done`.
- Badge du nombre N = `min(row_count, 100)`; si tronqué, suffixe “+”.
- Test visuel: voir le bouton apparaître/disparaître selon le contenu.

Phase 4 — Panneau Latéral (Slide‑Over)
- Panneau à droite: min‑w 320px, max‑w 40vw; overlay cliquable; `Esc` ferme; bouton croix.
- Titre: “Tickets interrogés”; sous‑titre: mode (SQL MindsDB | Graph) + période si détectée.
- Auto‑ouverture au `done` si tickets détectés, sauf si l’utilisateur l’a fermé sur la requête précédente.
- Test visuel: ouverture automatique, fermeture via overlay, réouverture via bouton.

Phase 5 — Liste des Tickets
- Rendu simple (liste/table) en réutilisant styles existants; tri par `created_at` décroissant.
- Colonnes: `ticket_id`, `title`, `created_at` (formatée), `status`.
- Limiter à 100 lignes; si plus, afficher badge “+N”.
- Test visuel: dataset 5 lignes → 5 lignes visibles; dataset 250 → 100 visibles + “+150”.

Phase 6 — États & A11y
- États: `vide` (“Aucun ticket extrait”), `erreur` (texte discret), `loading` (squelettes si nécessaire).
- Accessibilité: focus trap dans le panneau, `aria-modal`, `role="dialog"`, retour du focus sur le bouton à la fermeture.
- Test visuel: navigation au clavier (`Tab`, `Shift+Tab`), `Esc` ferme, focus restitué.

Phase 7 — Période & Résumé
- Déduire la période via: 1) parsing léger du prompt (“mai 2025”) ou 2) min/max de `created_at`.
- Afficher résumé: “N tickets — mai 2025”.
- Test visuel: prompt “Combien de tickets en mai 2025 ?” → “Tickets (5)” + résumé “mai 2025”.

Phase 8 — Logs Utiles (dev) / Télémétrie (si existante)
- `console.info('[tickets_panel] opened', { count, sourceMode })` en dev uniquement.
- Événement analytics “tickets_panel_opened” si un mécanisme existe déjà (sinon, s’abstenir).
- Test visuel: vérifier la présence/absence des logs en dev/prod.

Phase 9 — Responsiveness & Perf
- Vérifier rendu ≥360px; scroll fluide; pas de jank; éviter la virtualisation à ce stade.
- Test visuel: redimensionner la fenêtre; vérifier overflow et lisibilité.

Phase 10 — Finitions & Docs
- Nettoyer code et types; commentaires minima.
- Mettre à jour `README.md` (usage, limites, tests visuels).
- Test visuel: parcours complet de bout en bout sans actions réseau supplémentaires.

Critères d’Acceptation (E2E Visuels)
- Requête: “Combien de tickets en mai 2025 ?” → assistant “il y a 5 tickets” → bouton “Tickets (5)” visible; panneau s’ouvre avec 5 lignes datées 2025‑05.
- Requête hors tickets → aucun bouton ni panneau.
- Gros dataset (250) → 100 affichés + “+150”; tri par date desc; scroll OK.
- A11y: `Tab` circule dans le panneau; `Esc` ferme; focus rendu au bouton.
- Aucun fetch additionnel n’est déclenché par l’ouverture du panneau.


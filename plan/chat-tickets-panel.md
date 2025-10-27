# Plan UI — Panneau « Éléments de preuve » (générique) pour /chat

Objectif
- Dans `/chat`, après une requête (SQL MindsDB ou Graph), afficher un panneau latéral listant les éléments de preuve (tickets ou autre entité) réellement utilisés pour produire la réponse, sans appel réseau additionnel ni logique codée en dur.

Principe de généralisation (contrat MCP/SSE minimal)
- Le pipeline chat (LLM + MCP) fournit, pendant le streaming, un « Evidence Spec » décrivant l’entité et les champs à exposer.
- Deux apports possibles (au choix, au moins un requis):
  - `meta.evidence_spec`: hints déclaratifs envoyés tôt (labels, champs, limites).
  - `rows` avec `purpose: 'evidence'`: dataset des enregistrements supports aligné sur le spec.
- Sans `evidence_spec` explicite, le panneau reste désactivé et affiche un tooltip explicite (pas d’heuristique silencieuse).

Evidence Spec (contrat côté événements)
- `entity_label` (string): libellé (« Tickets », « Incidents », « Commandes »).
- `entity_name` (string): identifiant technique optionnel.
- `pk` (string): champ identifiant principal.
- `display`: mapping optionnel des rôles de champs: `{ title?, status?, created_at?, link_template? }`.
- `columns` (string[]): colonnes attendues dans `rows`.
- `limit` (number): max de lignes transmises (ex: 100).
- `purpose` (string): doit valoir `'evidence'` pour les `rows` concernés.

Contraintes
- Pas de fallback réseau ni d’heuristiques implicites: si le contrat n’est pas fourni, le panneau n’apparaît pas (ou est désactivé avec explication).
- Implémentation minimale dans `frontend/src/features/chat/Chat.tsx` (composant dédié facultatif et léger si besoin).
- Pas d’artéfacts inutiles; logs ciblés uniquement en dev.

Phase 0 — Contrat & Signal
- Consommer `meta.evidence_spec` si présent; sinon, guetter un `rows` avec `purpose: 'evidence'`.
- Définir l’ouverture auto: à `done`, si count > 0 et `evidence_spec` valide.
- Test visuel: sans spec → bouton désactivé + tooltip “Aucun evidence_spec reçu”.

Phase 1 — Capture Dataset Évidence (Chat.tsx)
- Stocker le dernier `rows` dont `purpose === 'evidence'` (colonnes, lignes, `row_count`, `step`).
- Conserver `evidence_spec` et `sourceMode: 'sql' | 'graph'` au niveau du message final.
- Réinitialiser à l’envoi d’une nouvelle question.
- Test visuel: deux requêtes successives → pas de fuite d’état entre messages.

Phase 2 — Bouton Contextuel générique
- Libellé: `entity_label (N)` provenant du spec; N = `row_count` borné par `limit`.
- Désactivé si spec absent ou dataset vide; tooltip explicite.
- Test visuel: apparition/disparition et états actif/désactivé.

Phase 3 — Panneau Latéral (Slide‑Over)
- Min‑w 320px, max‑w 40vw, overlay cliquable, fermeture `Esc` et bouton croix.
- En‑tête: `entity_label` + résumé (mode SQL/Graph, période si fournie via spec ou calculée plus tard par le pipeline — pas par le front).
- Auto‑ouverture sur `done` si >0 éléments et non fermé manuellement lors de la précédente requête.
- Test visuel: ouverture auto, fermeture, réouverture.

Phase 4 — Rendu liste générique
- Réutiliser styles existants; afficher: `pk`, `display.title`, `display.created_at` (formaté), `display.status` si présents.
- `display.link_template` optionnel pour lien clicable (ex: `/tickets/{ticket_id}`). Pas de navigation si absent.
- Tri par `display.created_at` décroissant si fourni; sinon conserver l’ordre serveur (pas d’heuristique locale).
- Limiter à 100 lignes ou `spec.limit`.
- Test visuel: dataset 5 éléments → 5; dataset 250 → 100 + badge “+150”.

Phase 5 — États & A11y
- États: `vide` (“Aucun élément de preuve”), `erreur` (texte discret), `loading`.
- Accessibilité: focus trap, `aria-modal`, `role="dialog"`, restitution du focus.
- Test visuel: navigation clavier et `Esc` ok.

Phase 6 — Période & Résumé (optionnel, contractuel)
- Si `evidence_spec.period` est fourni (ex: `{"from":"2025-05-01","to":"2025-05-31"}`), l’afficher.
- Le front n’infère pas la période à partir des données (évite heuristiques cachées).
- Test visuel: prompt “mai 2025” avec period dans spec → résumé “mai 2025”.

Phase 7 — Logs (dev) / Télémétrie (si existante)
- `console.info('[evidence_panel] opened', { count, entity: entity_label, sourceMode })` en dev.
- Événement analytics “evidence_panel_opened” si pipeline analytics existe.
- Test visuel: logs visibles en dev uniquement.

Phase 8 — Responsiveness & Perf
- ≥360px, scroll fluide; pas de virtualisation au départ.
- Test visuel: redimensionnement et lisibilité.

Phase 9 — Finitions & Docs
- Types TS `EvidenceSpec` et `EvidenceItem` minimalistes dans `Chat.tsx` (ou `types/chat`).
- Mise à jour README (contrat et tests visuels).
- Test visuel: parcours bout‑en‑bout sans requêtes additionnelles.

Critères d’Acceptation (E2E Visuels)
- Avec un `evidence_spec` “Tickets” et un `rows` `purpose:'evidence'` de 5 lignes datées 2025‑05: bouton “Tickets (5)”, panneau ouvert, 5 lignes visibles.
- Sans `evidence_spec`: bouton désactivé avec tooltip “Aucun evidence_spec reçu”; aucun panneau.
- Dataset volumineux: 100 visibles + “+N”; tri sur `created_at` uniquement si fourni par le spec.
- A11y: `Tab` circule; `Esc` ferme; focus rendu.
- Aucun fetch additionnel n’est déclenché par l’ouverture du panneau.

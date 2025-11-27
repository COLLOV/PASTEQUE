# Frontend FoyerInsight

Application React modernisée avec TypeScript, TailwindCSS et React Router v6.

## Stack Technique

- **React 18.3.1** - Framework UI moderne
- **TypeScript 5.6** - Type safety et meilleure DX
- **Vite 5.4** - Build tool ultra-rapide
- **React Router v6** - Navigation côté client
- **TailwindCSS 3.4** - Framework CSS utility-first
- **React Icons** - Bibliothèque d'icônes moderne

## Design System

### Palette de Couleurs (Noir et Blanc)

L'application utilise une palette monochrome élégante basée sur des nuances de gris:

- **primary-950**: `#09090b` - Noir principal (texte, boutons)
- **primary-900**: `#18181b` - Noir légèrement plus clair
- **primary-800**: `#27272a` - Arrière-plans foncés
- **primary-700**: `#3f3f46` - Texte secondaire foncé
- **primary-600**: `#52525b` - Texte secondaire
- **primary-500**: `#71717a` - Texte tertiaire
- **primary-400**: `#a1a1aa` - Bordures actives
- **primary-300**: `#d4d4d8` - Bordures légères
- **primary-200**: `#e4e4e7` - Bordures par défaut
- **primary-100**: `#f4f4f5` - Arrière-plans clairs
- **primary-50**: `#fafafa` - Arrière-plans très clairs

### Composants UI Réutilisables

Tous les composants sont situés dans `src/components/ui/`:

- **Button** - Variants: primary, secondary, ghost, danger
- **Input** - Champs de saisie avec labels et erreurs
- **Textarea** - Zone de texte avec support d'erreurs
- **Card** - Conteneur avec variants: default, elevated, outlined
- **Loader** - Indicateur de chargement avec spinner

### Typographie

- **Font**: Inter (Google Fonts)
- **Weights**: 300, 400, 500, 600, 700

## Installation

```bash
npm install
# Mode sans watchers (recommandé si vous avez trop de fichiers)
npm run build && npm run preview
# ou utilisez le script racine: ../../start.sh
```

Configurer l'API via `.env.development` (voir `.env.development.example`). Le script racine `start.sh` lit `FRONTEND_DEV_URL` (hôte/port Vite), `VITE_API_URL` (base API) et, si présent, `FRONTEND_URLS`; il ne modifie plus ce fichier.

## Structure du Projet

```
src/
├── components/
│   ├── ui/              # Composants UI réutilisables
│   │   ├── Button.tsx
│   │   ├── Input.tsx
│   │   ├── Textarea.tsx
│   │   ├── Card.tsx
│   │   ├── Loader.tsx
│   │   └── index.ts
│   ├── layout/          # Composants de layout
│   │   ├── Layout.tsx
│   │   └── Navigation.tsx
│   └── ProtectedRoute.tsx
├── features/
│   ├── auth/
│   │   └── Login.tsx
│   ├── chat/
│   │   └── Chat.tsx
│   ├── dashboard/
│   │   └── Dashboard.tsx
│   └── admin/
│       └── AdminPanel.tsx
├── services/
│   ├── api.ts           # Client API avec types
│   └── auth.ts          # Service d'authentification
├── types/
│   ├── auth.ts          # Types pour l'authentification
│   ├── chat.ts          # Types pour le chat
│   └── user.ts          # Types pour les utilisateurs
├── App.tsx              # Router principal
├── main.tsx             # Point d'entrée
├── index.css            # Styles globaux Tailwind
└── vite-env.d.ts        # Types d'environnement Vite
```

## Scripts

- `npm run dev` - Lance le serveur de développement (port 5173) [active les watchers]
- `npm run build` - Compile l'application pour la production
- `npm run preview` - Prévisualise le build de production (sans watchers)
- `npm run type-check` - Vérifie les types TypeScript

## Configuration

### Variables d'environnement

Créez un fichier `.env.development` à la racine du frontend:

```env
FRONTEND_DEV_URL=http://localhost:5173
FRONTEND_URLS=http://localhost:5173
VITE_API_URL=http://localhost:8000/api/v1
```

### Path Aliases

Le projet utilise `@/` comme alias pour `./src/`:

```typescript
import { Button } from '@/components/ui'
import { login } from '@/services/auth'
```

## Branding (Logo)

- Placez votre logo dans `frontend/public/insight.svg`.
- Le header l'affiche automatiquement via: `src={`${import.meta.env.BASE_URL}insight.svg`}`.
- Si vous préférez un autre nom de fichier, modifiez `src/components/layout/Layout.tsx` en conséquence.
- Alternative (fingerprinting par Vite): placez le fichier dans `src/assets/` et importez-le en tant que module.
 - Le logo est aussi affiché dans l'état vide du chat, au‑dessus du titre « Discutez avec vos données ».

## Fonctionnalités

### Authentification

- Page de login moderne avec design noir et blanc
- Stockage du token JWT dans localStorage
- Routes protégées avec redirection automatique
- Support des rôles admin

### Navigation

- React Router v6 pour la navigation
- Layout persistant avec header et navigation
- Liens actifs avec indicateur visuel
- Navigation responsive
- Espace admin organisé en onglets (Statistiques, Dictionnaire, Loop, Utilisateurs, Feedback). L’entrée Feedback est accessible dans l’onglet Admin.

### Chat

- Deux panneaux: « Ticket exploration » à gauche et chat à droite.
- Bulles de messages distinctes pour utilisateur/assistant.
- Auto-scroll lors de nouveaux messages.
- Support du Shift+Enter pour nouvelles lignes.
- Gestion des états de chargement et d'erreur.
- Streaming en direct (SSE sur `POST /api/v1/chat/stream`).
- Nouveau: barre d'actions sous chaque réponse de l'assistant avec deux boutons: « Graphique » et « Détails ».
  - Taille réduite: `size="xs"` pour une empreinte visuelle minimale.
  - Apparition différée: les boutons ne s'affichent qu'une fois la réponse finalisée (fin du streaming), jamais pendant l'écriture.
  - « Graphique » déclenche `/mcp/chart` et s'affiche dans un nouveau message (bouton « Enregistrer dans le dashboard » inclus). Le bouton est automatiquement désactivé si aucun jeu de données NL→SQL exploitable n'est associé au message.
  - « Détails » affiche/masque les informations de requête (SQL exécuté, échantillons, plan).

#### Layout responsive — Oct. 2025

- Desktop (≥ lg): grille en 12 colonnes avec un panneau gauche élargi (`lg:col-span-5`) et le chat à droite (`lg:col-span-7`).
- Mobile/Tablette (< lg): priorité au chat — le panneau « Ticket exploration » est masqué automatiquement.
- Un bouton « Exploration » apparait en haut du chat pour ouvrir un bottom sheet avec les éléments détectés.

### Historique des conversations

- Le bouton « Historique » du header ouvre la modale via `?history=1` sur `/chat` (l'état reste synchronisé avec l'URL).
- Le bouton « Nouveau chat » du header remplace l’ancien bouton « Chat » et initialise une nouvelle session via `?new=1`.
- Lors de l’envoi d’un premier message, le backend crée une conversation et renvoie `conversation_id` dans l’événement `meta`; le frontend rattache alors les messages suivants à cette conversation.
 - Robustesse (29 oct. 2025): lors du chargement d’une conversation depuis l’historique,
   les `evidence_rows.rows` sont normalisées côté front pour gérer les cas où le backend
   a persisté des lignes sous forme de tableaux (héritage de certaines réponses MindsDB).
Les cellules du panneau « Tickets » restent ainsi correctement renseignées.

Sous-panel « Tickets » — aperçu et détail (oct. 2025)

- Aperçu limité pour garder le panel lisible:
  - Nombre maximum de colonnes par ticket en liste.
  - Nombre maximum de caractères par valeur (ellipsis au-delà).
- Colonnes affichées: le panel dérive désormais ses colonnes de l'union des clés
  réellement présentes dans les lignes SQL renvoyées (échantillon). Les suggestions
  du LLM (`spec.columns`) ne restreignent plus l'affichage. L'aperçu reste limité
  par `PREVIEW_COL_MAX`, tandis que la vue Détail affiche toutes les colonnes.
- Clic sur un ticket: bascule en vue détail dans le même panel, avec toutes les colonnes visibles et sans troncature. Un bouton « Tout voir » permet de revenir à la liste.
- À la fermeture du détail (« Tout voir »), la position de défilement du panel est restaurée au même endroit qu'avant l'ouverture.
- Paramètres: voir `frontend/src/features/chat/Chat.tsx` → composant `TicketPanel`.
- `PREVIEW_COL_MAX` — nombre de colonnes max en aperçu (par défaut: 5).
  - Les colonnes affichées sont dérivées à partir d'un petit échantillon (≤20 premières lignes)
    pour garantir un ordre stable, puis priorisées (titre, statut, date, pk).
  - `PREVIEW_CHAR_MAX` — troncature des valeurs en aperçu.
  - L’ordre des colonnes privilégie `title`, `status`, `created_at`, puis le reste.
 
Affichage des « Détails » depuis l’historique (29 oct. 2025)

- Le backend renvoie, pour chaque message assistant, un champ optionnel `details`
  reconstruit à partir des `conversation_events` entre le dernier message utilisateur
  et le message assistant:
  - `details.steps`: liste des requêtes SQL (`step`, `purpose`, `sql`).
  - `details.plan`: payload du plan s’il a été émis.
- Le frontend propage `message.details` lors du chargement d’une conversation;
  le bouton « Détails » fonctionne donc aussi pour l’historique.
 - Marges réduites: largeur de page limitée à `max-w-screen-2xl` et espacement entre colonnes passé à `gap-4`.

#### Composer (Mise à jour)

- Zone de saisie intégrée en bas de la colonne de droite (bord supérieur avec `border-t`).
- Bouton contextuel intégré à droite:
  - Affiche « Envoyer » (icône avion) à l'arrêt.
  - Se transforme en « Annuler » (icône croix) pendant le streaming.
- Entrée simple pour envoyer, `Maj+Entrée` pour aller à la ligne.
  
Mise à jour d'harmonisation (oct. 2025):

- Poignée de redimensionnement du textarea supprimée (`resize: none`).
- Boutons « Graphique » et « Envoyer » centrés verticalement dans l'input.
- Taille des boutons unifiée à 40px (`h-10 w-10`) avec `rounded-md`.
- Padding latéral de l'input ajusté pour les accueillir (`pl-14` / `pr-14`).
- Input sur une seule ligne: `rows={1}`, `h-12` et `whitespace-nowrap` avec défilement horizontal.
- Placeholder mis à jour: « Posez votre question », centré tant qu'il est visible.
- Largeur du chat: `max-w-3xl` (modifiable dans `src/features/chat/Chat.tsx`).
 
Fonctionnement du bouton « Graphique » (oct. 2025):

- Le bouton est visible sur chaque réponse de l'assistant et s'active uniquement si un échantillon NL→SQL (colonnes + lignes) est disponible pour ce tour.
- Le clic envoie `POST /mcp/chart` avec: `{ prompt: <message utilisateur précédent>, answer: <réponse>, dataset: { sql, columns, rows, row_count } }`.
- Pendant l'appel, l'UI affiche une animation (spinner) et le libellé « Génération… » sur le bouton. Un indicateur global « Génération du graphique… » apparaît également dans le fil de discussion.
- Le graphique est affiché dans un nouveau message assistant, avec bouton « Enregistrer dans le dashboard ».
- S'il n'y a pas de données, le bouton reste désactivé (UX plus claire et cohérente).

Personnalisation rapide:

- Ajuster `pl-14` / `pr-14` et `h-12` dans `src/features/chat/Chat.tsx`.
- Modifier `h-10 w-10` des boutons et les tailles d'icônes (`w-5 h-5`).
- Pour changer la largeur des colonnes: adapter les classes Tailwind `lg:col-span-*` dans `src/features/chat/Chat.tsx`.

### Explorer

- Page `/explorer` accessible depuis le header (bouton à gauche de « Nouveau chat ») pour une vision globale des sources autorisées.
- Consomme `GET /data/overview` : total par source et statistiques sur toutes les colonnes détectées (inférence des dates), en respectant les ACL.
- Cartes par source avec mini-barres / timeline Chart.js colorées, gestion des colonnes affichées (masquage/affichage par l’admin) pour rester lisible malgré un grand nombre de champs.
- Chaque carte est repliée par défaut avec un dropdown bien visible (chevron et pastille « Détails ») pour parcourir rapidement la liste des tables; cliquer pour dérouler statistiques et gestion des colonnes.
- Si la table contient les colonnes `Category` et `Sub Category`, un graphique empilé (Category en abscisse, segments Sub Category) est affiché en haut de la carte:
  - passer la souris affiche le nombre d’enregistrements par couple;
  - un clic sur un segment interroge `GET /data/explore/{source}?category=...&sub_category=...` et affiche un aperçu des lignes correspondantes directement sous le graphique.

### Dashboard

- Cartes de statistiques avec icônes
- Design en grille responsive
- Placeholder pour futurs graphiques

### Admin

- Création de nouveaux utilisateurs
- Validation des formulaires
- Feedback visuel (succès/erreur)
- Limité aux utilisateurs admin

## Design Principles

1. **Minimalisme** - Interface épurée, focus sur le contenu
2. **Accessibilité** - Focus states, ARIA labels, contraste élevé
3. **Responsive** - Mobile-first avec breakpoints Tailwind
4. **Performance** - Code splitting, lazy loading, optimisations Vite
5. **Type Safety** - TypeScript strict pour éviter les erreurs runtime

## Animations

L'application utilise des animations subtiles pour améliorer l'UX:

- `fade-in` - Apparition en fondu (0.2s)
- `slide-up` - Glissement vers le haut (0.3s)
- Transitions sur tous les états interactifs (0.2s)

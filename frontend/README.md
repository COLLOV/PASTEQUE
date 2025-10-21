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
npm run dev
```

Configurer l'API via `.env.development` (voir `.env.development.example`). Le script racine `start.sh` met automatiquement à jour `VITE_API_URL` en fonction du port backend choisi.

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

- `npm run dev` - Lance le serveur de développement (port 5173)
- `npm run build` - Compile l'application pour la production
- `npm run preview` - Prévisualise le build de production
- `npm run type-check` - Vérifie les types TypeScript

## Configuration

### Variables d'environnement

Créez un fichier `.env.development` à la racine du frontend:

```env
VITE_API_URL=http://localhost:8000
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

### Chat

- Interface de chat moderne
- Bulles de messages distinctes pour utilisateur/assistant
- Auto-scroll lors de nouveaux messages
- Support du Shift+Enter pour nouvelles lignes
- Gestion des états de chargement et d'erreur
- Streaming en direct (SSE sur `POST /api/v1/chat/stream`)
  - Affichage token‑par‑token dans une bulle éphémère
  - Remplacement automatique par le message final à la fin
  - Panneau d’inspection repliable (SQL et échantillons; métadonnées techniques masquées)

#### Composer (Mise à jour)

- Zone de saisie fixée en bas de page (barre collée) pour rester toujours visible.
- Bouton « Envoyer » intégré directement dans la zone de saisie (icône avion en bas à droite).
- Entrée simple pour envoyer, `Maj+Entrée` pour aller à la ligne.
  
Mise à jour d'harmonisation (oct. 2025):

- Poignée de redimensionnement du textarea supprimée (`resize: none`).
- Boutons « Graphique » et « Envoyer » centrés verticalement dans l'input.
- Taille des boutons unifiée à 40px (`h-10 w-10`) avec `rounded-md`.
- Padding latéral de l'input ajusté pour les accueillir (`pl-14` / `pr-14`).
- Input sur une seule ligne: `rows={1}`, `h-12` et `whitespace-nowrap` avec défilement horizontal.
- Placeholder mis à jour: « Posez votre question », centré tant qu'il est visible.
- Largeur du chat: `max-w-3xl` (modifiable dans `src/features/chat/Chat.tsx`).

Personnalisation rapide:

- Ajuster `pl-14` / `pr-14` et `h-12` dans `src/features/chat/Chat.tsx`.
- Modifier `h-10 w-10` des boutons et les tailles d'icônes (`w-5 h-5`).

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

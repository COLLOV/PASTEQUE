# Guide de Démarrage Rapide

## Installation

```bash
cd /Users/rekta/projet/insight/2-PASTEQUE-copy/frontend
npm install
```

## Configuration

Créez un fichier `.env.development`:

```env
FRONTEND_URLS=http://localhost:5173,http://127.0.0.1:5173
VITE_API_URL=http://localhost:8000/api/v1
```

## Développement

```bash
npm run dev
```

L'application sera disponible sur http://localhost:5173

## Build de Production

```bash
npm run build
```

Les fichiers optimisés seront dans le dossier `dist/`

## Vérification des Types

```bash
npm run type-check
```

## Structure Rapide

```
src/
├── components/ui/       → Composants réutilisables (Button, Input, Card...)
├── components/layout/   → Layout et Navigation
├── features/            → Pages (Login, Chat, Dashboard, Admin)
├── services/            → API et Auth
├── types/               → Types TypeScript
└── App.tsx             → Router principal
```

## Composants UI Disponibles

### Button
```tsx
import { Button } from '@/components/ui'

<Button variant="primary" size="md" fullWidth>
  Cliquez-moi
</Button>
```

Variants: `primary` | `secondary` | `ghost` | `danger`
Sizes: `sm` | `md` | `lg`

### Input
```tsx
import { Input } from '@/components/ui'

<Input
  label="Email"
  type="email"
  placeholder="votre@email.com"
  error={error}
  fullWidth
/>
```

### Card
```tsx
import { Card } from '@/components/ui'

<Card variant="elevated" padding="lg">
  Contenu
</Card>
```

Variants: `default` | `elevated` | `outlined`
Padding: `none` | `sm` | `md` | `lg`

### Textarea
```tsx
import { Textarea } from '@/components/ui'

<Textarea
  placeholder="Votre message"
  rows={4}
  fullWidth
/>
```

### Loader
```tsx
import { Loader } from '@/components/ui'

<Loader size="md" text="Chargement..." />
```

## Routes

- `/login` - Page de connexion
- `/chat` - Interface de chat
- `/dashboard` - Tableau de bord
- `/admin` - Panel admin (uniquement pour les admins)

## Services

### API Client
```typescript
import { apiFetch } from '@/services/api'

const data = await apiFetch<ResponseType>('/endpoint', {
  method: 'POST',
  body: JSON.stringify({ ... })
})
```

### Authentification
```typescript
import { login, logout, getAuth } from '@/services/auth'

// Login
const auth = await login('username', 'password')

// Récupérer l'auth courante
const currentAuth = getAuth()

// Logout
logout()
```

## Couleurs (TailwindCSS)

Palette noir et blanc:

- `primary-950` - Noir principal (#09090b)
- `primary-900` - Noir léger (#18181b)
- `primary-800` - Foncé (#27272a)
- `primary-700` - Texte secondaire foncé (#3f3f46)
- `primary-600` - Texte secondaire (#52525b)
- `primary-500` - Texte tertiaire (#71717a)
- `primary-400` - Bordures actives (#a1a1aa)
- `primary-300` - Bordures légères (#d4d4d8)
- `primary-200` - Bordures (#e4e4e7)
- `primary-100` - Fond clair (#f4f4f5)
- `primary-50` - Très clair (#fafafa)

## Exemples d'Utilisation

### Créer une Nouvelle Page

1. Créer le composant dans `src/features/`:
```tsx
// src/features/exemple/Exemple.tsx
export default function Exemple() {
  return (
    <div className="max-w-5xl mx-auto animate-fade-in">
      <h2 className="text-2xl font-bold text-primary-950 mb-4">
        Titre
      </h2>
      <Card>
        Contenu
      </Card>
    </div>
  )
}
```

2. Ajouter la route dans `App.tsx`:
```tsx
<Route path="exemple" element={<Exemple />} />
```

3. Ajouter le lien dans `Navigation.tsx`:
```tsx
{ to: '/exemple', label: 'Exemple', icon: HiStar }
```

### Appel API avec Types

```typescript
// 1. Définir les types
interface MyRequest {
  name: string
}

interface MyResponse {
  id: number
  name: string
}

// 2. Faire l'appel
const response = await apiFetch<MyResponse>('/api/endpoint', {
  method: 'POST',
  body: JSON.stringify({ name: 'test' } as MyRequest)
})
```

## Dépannage

### Erreur "VITE_API_URL manquant"
→ Créez le fichier `.env.development` avec `VITE_API_URL` (ajoutez `FRONTEND_URLS` si vous devez ouvrir le backend à d'autres origines)

### Erreur TypeScript
→ Vérifiez avec `npm run type-check`

### Port déjà utilisé
→ Le port 5173 est utilisé par défaut, modifiez dans `vite.config.ts`

### Hot reload ne fonctionne pas
→ Relancez `npm run dev`

## Support

Pour plus d'informations, consultez:
- README.md - Documentation complète
- MIGRATION.md - Détails de la migration

## Frontend – React (Vite)

Squelette minimal pour l’UI. Tout le visuel vit ici.

### Installation

```
npm i
npm run dev
```

Configurer l’API via `.env.development` (voir `.env.development.example`).

### Chat minimal

1. Créez `frontend/.env.development`:

```
VITE_API_URL=http://localhost:8000/api/v1
```

2. Lancez le backend (voir dossier `backend/`). Assurez‑vous que `LLM_MODE` est configuré et que le modèle répond.

3. Démarrez le front: `npm run dev` puis ouvrez `http://localhost:5173`.

Le composant Chat envoie sur `POST /api/v1/chat/completions` avec la forme `{ messages: [{role, content}, ...] }` et affiche la réponse.

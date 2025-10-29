# Plan Z — Intégration LLM et MCP

Objectif: mettre en place un LLM « Z » pour discuter avec les données, avec deux modes d'exécution (local via vLLM et API externe) et préparer des connexions faciles à des serveurs MCP utiles (Chart, Neo4j, MindsDB).

Principes (AGENT.MD):
- Minimum d’artéfacts, pas de fallback cachés, logs utiles.
- Mode local et mode API pour la gestion des LLM.
- Utiliser `uv` pour Python.

## Résultat visé

- Endpoint `POST /api/v1/chat/completions` opérationnel via un moteur OpenAI‑compatible.
- Configuration simple par variables d’environnement pour basculer entre:
  - `LLM_MODE=local` (vLLM) – `VLLM_BASE_URL`, `Z_LOCAL_MODEL`.
  - `LLM_MODE=api` (Z provider) – `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `LLM_MODEL`.
- Squelette de connexion MCP (déclaratif) pour:
  - antvis/mcp-server-chart
  - neo4j-contrib/mcp-neo4j
  - MindsDB (via MCP Market)

## Étapes

1) LLM « Z » via interface OpenAI‑compatible
- Implémenter un moteur mince côté backend qui appelle une API OpenAI‑compatible (`/v1/chat/completions`).
- Local: pointer `VLLM_BASE_URL` vers un serveur vLLM OpenAI‑compatible.
- API: pointer `OPENAI_BASE_URL` vers la passerelle du provider Z (voir quick start officiel) et fournir `OPENAI_API_KEY`.

2) Données
- Les services `data` existent déjà; ils restent inchangés. La discussion avec les données se fera dans une itération suivante via RAG ou outils MCP.

3) MCP (Model Context Protocol)
- Déclaration des serveurs MCP dans un fichier JSON/YAML ou via `MCP_SERVERS_JSON`.
- Fournir un manager léger qui liste la config et prépare la connexion (sans lancer de process automatiquement ici).

4) Docs & DX
- Mettre à jour `backend/.env.example` et `backend/README.md`.
- Fournir un exemple de config MCP.

## Configuration des variables d’environnement

Obligatoire (choisir un mode):
- `LLM_MODE` = `local` | `api`

Mode local (vLLM):
- `VLLM_BASE_URL` (ex: `http://localhost:8000/v1`)
- `Z_LOCAL_MODEL` (ex: `GLM-4.5-Air`) – utilisé comme `model`.

Mode API (provider Z):
- `OPENAI_BASE_URL` (OpenAI‑compatible du provider Z)
- `OPENAI_API_KEY`
- `LLM_MODEL` (ex: `GLM-4.5-Air` ou équivalent provider)

MCP (optionnel):
- `MCP_CONFIG_PATH` (chemin vers un JSON/YAML) ou `MCP_SERVERS_JSON`.

## Exemple vLLM (local)

Demarrage vLLM OpenAI‑compatible (exemple générique):

```bash
python -m vllm.entrypoints.openai.api_server \
  --model $Z_LOCAL_MODEL \
  --host 0.0.0.0 --port 8000
# VLLM_BASE_URL=http://localhost:8000/v1
# LLM_MODE=local
```

Note: adaptez le nom de modèle à votre environnement.

## Exemple API provider Z

Se référer au quick‑start officiel: `https://docs.z.ai/guides/overview/quick-start`.

Paramétrage:

```bash
export LLM_MODE=api
export OPENAI_BASE_URL="<base OpenAI-compatible du provider Z>"
export OPENAI_API_KEY="<clé>"
export LLM_MODEL="GLM-4.5-Air"
```

## MCP — Déclaration et usage

Trois serveurs ciblés:
- Chart: https://github.com/antvis/mcp-server-chart
- Neo4j: https://github.com/neo4j-contrib/mcp-neo4j
- MindsDB: https://mcpmarket.com/server/mindsdb

Déclarez‑les via `MCP_SERVERS_JSON` (exemple minimal):

```json
[
  {
    "name": "chart",
    "command": "npx",
    "args": ["-y", "@antv/mcp-server-chart"],
    "env": {}
  },
  {
    "name": "neo4j",
    "command": "mcp-neo4j",
    "args": [],
    "env": {"NEO4J_URI": "bolt://localhost:7687", "NEO4J_USER": "neo4j", "NEO4J_PASSWORD": "***"}
  },
  {
    "name": "mindsdb",
    "command": "mcp-mindsdb",
    "args": [],
    "env": {"MINDSDB_API_KEY": "***"}
  }
]
```

Limité volontairement: le backend expose aujourd’hui la lecture de cette configuration et la liste des serveurs. La connexion/gestion de sessions MCP sera branchée au moteur de chat lors de l’introduction de tool‑calling, pour rester simple et éviter les fausses implémentations.

## Tests manuels rapides

1) Local vLLM:
- Démarrez vLLM (voir plus haut).
- `curl -X POST http://localhost:8000/v1/chat/completions ...` (sanity‑check côté vLLM).
- Puis côté backend: `uv run uvicorn insight_backend.main:app --reload`.
- `curl -X POST 'http://127.0.0.1:8000/api/v1/chat/completions' -H 'Content-Type: application/json' -d '{"messages":[{"role":"user","content":"Bonjour"}]}'`

2) Mode API:
- Exportez `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `LLM_MODEL` et `LLM_MODE=api`.
- Même appel HTTP que ci‑dessus.


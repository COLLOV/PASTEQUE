## data/

Convention de dossiers inspirée de cookiecutter-data-science, adaptée au projet:

- `raw/` – données brutes non modifiées
- `external/` – sources externes (export BI, CSV, etc.)
- `interim/` – fichiers temporaires, staging
- `processed/` – données prêtes à l’usage (features, tables)
- `vector_store/` – index/embeddings pour le chat avec la data
- `models/` – artefacts de modèles (si nécessaire)

Les dossiers sont ignorés par Git (sauf `.gitkeep`) pour éviter d’alourdir le repo.


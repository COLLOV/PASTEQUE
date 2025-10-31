Data Dictionary (YAML)
======================

Place one YAML file per table here. The filename must match the table name used in `DATA_TABLES_DIR` (without the `files.` prefix), e.g. `tickets_jira.yml`.

Minimal schema:

```
version: 1
table: tickets_jira
title: Tickets Jira
description: Tickets d'incidents JIRA
columns:
  - name: ticket_id
    description: Identifiant unique du ticket
    type: integer
    synonyms: [id, issue_id]
    pii: false
  - name: created_at
    description: Date de création (YYYY-MM-DD)
    type: date
    pii: false
```

Notes
- Only include columns that exist in your CSV/TSV.
- Keep descriptions concise (≤ 120 chars per column).
- `pii` helps downstream agents avoid leaking personal data.
- Additional optional keys per column: `unit`, `nullable`, `example`, `enum`.

Generated dictionaries
----------------------

Date: 2025-10-31

The following tables from `data/raw/` are now covered with minimal dictionaries (names only; descriptions/types to refine if needed):
- `myfeelback_agences`
- `myfeelback_app_mobile`
- `myfeelback_nps`
- `myfeelback_remboursements`
- `myfeelback_service_client`
- `myfeelback_souscriptions`
- `tickets_jira`

Edit these files to enrich column descriptions and add `pii` metadata where applicable.

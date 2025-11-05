from __future__ import annotations

from typing import Any, Dict, Optional
import re


class AnimatorAgent:
    """Derive short, human-friendly status messages from backend events.

    This agent does not mutate state nor performs I/O; it only maps
    (kind, payload) → str for UI hints.
    """

    _re_distinct = re.compile(r"\bselect\b[^;]*\bdistinct\b", re.I)
    _re_count = re.compile(r"\bcount\s*\(\s*\*?\s*\)", re.I)
    _re_group = re.compile(r"\bgroup\s+by\b", re.I)
    _re_minmax = re.compile(r"\b(min|max)\s*\(", re.I)
    _re_extract = re.compile(r"\bextract\s*\(\s*(year|month)\b", re.I)

    def translate(self, kind: str, payload: Dict[str, Any] | None) -> Optional[str]:  # noqa: C901 - simple heuristics
        p = payload or {}
        k = (kind or "").strip().lower()

        if k == "plan":
            steps = []
            if isinstance(p, dict):
                st = p.get("steps")
                if isinstance(st, list):
                    steps = st
            n = len(steps)
            return f"Plan d'exploration: {n} étape(s)" if n else "Préparation du plan d'exploration"

        if k == "meta":
            # Effective tables selection
            eff = p.get("effective_tables") if isinstance(p, dict) else None
            if isinstance(eff, list):
                return f"Tables actives: {len(eff)}"
            # Evidence spec
            if isinstance(p, dict) and p.get("evidence_spec"):
                return "Préparation du panneau 'Évidence'"
            return None

        if k == "sql":
            sql = "" if not isinstance(p, dict) else str(p.get("sql") or "")
            purpose = ("" if not isinstance(p, dict) else str(p.get("purpose") or "")).lower()
            label_prefix = "Exploration" if purpose == "explore" else ("Réponse finale" if purpose == "answer" else "Exécution SQL")
            s = sql.strip()
            if not s:
                return f"{label_prefix}: préparation de la requête"
            if self._re_distinct.search(s):
                return f"{label_prefix}: valeurs distinctes"
            if self._re_minmax.search(s) or self._re_extract.search(s):
                return f"{label_prefix}: bornes et périodes"
            if self._re_count.search(s) and self._re_group.search(s):
                return f"{label_prefix}: comptage par catégorie"
            return f"{label_prefix}: échantillonnage de lignes"

        if k == "rows":
            if not isinstance(p, dict):
                return "Réception de résultats"
            n = p.get("row_count")
            try:
                n_int = int(n) if n is not None else None
            except Exception:
                n_int = None
            purpose = (str(p.get("purpose")) if p.get("purpose") is not None else "").lower()
            if purpose == "evidence":
                return f"Évidence: {n_int if n_int is not None else '?'} ligne(s)"
            return f"Résultats: {n_int if n_int is not None else '?'} ligne(s)"

        return None


from __future__ import annotations

from dataclasses import dataclass
import re
import csv
from pathlib import Path
from typing import Dict, List
import json

from ..core.config import settings
import sqlglot
from sqlglot import exp
from ..integrations.openai_client import OpenAICompatibleClient
from ..repositories.data_repository import DataRepository


def _extract_sql(text: str) -> str:
    t = text.strip()
    if "```" in t:
        parts = t.split("```")
        # Prefer the first fenced block content
        if len(parts) >= 2:
            code = parts[1]
            # Strip optional language hint like ```sql
            code = code.split("\n", 1)[-1] if code.lower().startswith("sql\n") else code
            return code.strip().strip(";")
    return t.strip().strip(";")


def _is_select_only(sql: str) -> bool:
    s = sql.strip().lower()
    if not s.startswith("select"):
        return False
    forbidden = (";", " insert ", " update ", " delete ", " drop ", " alter ", " create ", " grant ", " revoke ")
    # Allow single trailing semicolon by stripping earlier
    s2 = f" {s} "
    return not any(tok in s2 for tok in forbidden[1:])


_TABLE_REF_PATTERN = re.compile(r"\b(from|join)\s+(?!\s*\()([a-zA-Z_][\w\.]*)", re.IGNORECASE)
_PREFIX_SKIP_KEYWORDS = {"select", "lateral", "unnest", "values", "table", "cast"}


def _rewrite_date_functions(sql: str) -> str:
    """Rewrite YEAR(col) / MONTH(col) into DuckDB-safe EXTRACT with CAST to DATE."""
    def rep_year(m: re.Match[str]) -> str:
        expr = m.group(1).strip()
        return f"EXTRACT(YEAR FROM CAST(NULLIF({expr}, 'None') AS DATE))"

    def rep_month(m: re.Match[str]) -> str:
        expr = m.group(1).strip()
        return f"EXTRACT(MONTH FROM CAST(NULLIF({expr}, 'None') AS DATE))"

    out = re.sub(r"(?is)\byear\s*\(\s*([^\)]+?)\s*\)", rep_year, sql)
    out = re.sub(r"(?is)\bmonth\s*\(\s*([^\)]+?)\s*\)", rep_month, out)
    return out


def _collect_cte_names(sql: str) -> set[str]:
    names: set[str] = set()
    s = sql.lstrip()
    if not s.lower().startswith("with"):
        return names

    lower = s.lower()
    length = len(s)
    i = len("with")

    def skip_ws(pos: int) -> int:
        while pos < length and s[pos].isspace():
            pos += 1
        return pos

    i = skip_ws(i)
    if lower.startswith("recursive", i):
        i += len("recursive")
        i = skip_ws(i)

    while i < length:
        if not (s[i].isalpha() or s[i] == "_"):
            break
        start = i
        i += 1
        while i < length and (s[i].isalnum() or s[i] == "_"):
            i += 1
        names.add(s[start:i].lower())
        i = skip_ws(i)

        if i < length and s[i] == "(":
            depth = 1
            i += 1
            while i < length and depth:
                if s[i] == "(":
                    depth += 1
                elif s[i] == ")":
                    depth -= 1
                i += 1
            i = skip_ws(i)

        if not lower.startswith("as", i):
            break
        i += 2
        i = skip_ws(i)

        if lower.startswith("not materialized", i):
            i += len("not materialized")
            i = skip_ws(i)
        elif lower.startswith("materialized", i):
            i += len("materialized")
            i = skip_ws(i)

        if i >= length or s[i] != "(":
            break
        depth = 1
        i += 1
        while i < length and depth:
            if s[i] == "(":
                depth += 1
            elif s[i] == ")":
                depth -= 1
            i += 1
        i = skip_ws(i)

        if i < length and s[i] == ",":
            i += 1
            i = skip_ws(i)
            continue
        break

    return names


def _ensure_required_prefix(sql: str) -> None:
    """Validate that every referenced table uses the configured schema prefix.

    Uses sqlglot to parse the query and extract table nodes, avoiding false positives
    on constructs like EXTRACT(... FROM col) where 'FROM' is not a table clause.
    """
    try:
        tree = sqlglot.parse_one(sql, dialect="mysql")
    except Exception as e:  # surface real parse errors
        raise RuntimeError(f"SQL invalide (parse): {e}")

    required = settings.nl2sql_db_prefix.lower()
    cte_names = _collect_cte_names(sql)
    bad: list[str] = []
    for t in tree.find_all(exp.Table):
        db = t.args.get("db")
        tbl = t.args.get("this")
        db_name = (db.this if hasattr(db, "this") else None)
        tbl_name = (tbl.this if hasattr(tbl, "this") else None)
        # Skip CTE references
        if tbl_name and tbl_name.lower() in cte_names:
            continue
        # Consider only real tables; skip CTEs (sqlglot resolves separately)
        fq = ".".join([p for p in [db_name, tbl_name] if p])
        if not db_name or db_name.lower() != required:
            bad.append(fq or "<inconnu>")
    if bad:
        raise RuntimeError(
            "Requête SQL invalide: toutes les tables doivent être préfixées par "
            f"'{settings.nl2sql_db_prefix}.' (trouvé: {', '.join(repr(x) for x in bad)})"
        )


@dataclass
class NL2SQLService:
    """Generate SQL from NL using the configured OpenAI-compatible LLM.

    Strict rules: SELECT-only and target DB prefix (e.g., files.).
    """

    def _client_and_model(self) -> tuple[OpenAICompatibleClient, str]:
        if settings.llm_mode == "local":
            base_url = settings.vllm_base_url
            model = settings.z_local_model
            api_key = None
        elif settings.llm_mode == "api":
            base_url = settings.openai_base_url
            model = settings.llm_model
            api_key = settings.openai_api_key
        else:
            raise RuntimeError("Invalid LLM_MODE; expected 'local' or 'api'")
        if not base_url or not model:
            raise RuntimeError("LLM base_url/model not configured")
        return (
            OpenAICompatibleClient(
                base_url=base_url,
                api_key=api_key,
                timeout_s=settings.openai_timeout_s,
            ),
            str(model),
        )

    def generate(self, *, question: str, schema: Dict[str, List[str]]) -> str:
        client, model = self._client_and_model()
        tables_desc = []
        for t, cols in schema.items():
            col_list = ", ".join(cols)
            tables_desc.append(f"- {settings.nl2sql_db_prefix}.{t}({col_list})")
        tables_blob = "\n".join(tables_desc)
        # Hints for date-like columns
        date_hints: Dict[str, List[str]] = {}
        for t, cols in schema.items():
            dcols = [c for c in cols if "date" in c.lower()]
            if dcols:
                date_hints[t] = dcols

        # Optional samples from CSV
        samples_blob = ""
        if settings.nl2sql_include_samples:
            repo = DataRepository(tables_dir=Path(settings.tables_dir))
            rows_per = max(1, settings.nl2sql_rows_per_table)
            trunc = max(10, settings.nl2sql_value_truncate)
            parts: List[str] = []
            for t in schema.keys():
                p = repo._resolve_table_path(t)
                if not p:
                    continue
                try:
                    delim = "," if p.suffix.lower() == ".csv" else "\t"
                    with p.open("r", encoding="utf-8", newline="") as f:
                        reader = csv.DictReader(f, delimiter=delim)
                        rows = []
                        for i, row in enumerate(reader):
                            if i >= rows_per:
                                break
                            rows.append({k: (str(v)[:trunc] if v is not None else None) for k, v in row.items()})
                        if rows:
                            parts.append(f"Table {settings.nl2sql_db_prefix}.{t} sample rows (max {rows_per}):\n{rows}")
                except Exception:
                    continue
            samples_blob = "\n\n".join(parts)

        system = (
            "You are a strict SQL generator. Dialect: MindsDB SQL (MySQL-like).\n"
            f"Use only the tables listed below under the '{settings.nl2sql_db_prefix}.' schema.\n"
            "Return exactly ONE SELECT query. No comments. No explanations.\n"
            "Rules: SELECT-only; never modify data. Date-like columns are TEXT in 'YYYY-MM-DD'.\n"
            "Always CAST(NULLIF(date_col,'None') AS DATE) before date filters and use EXTRACT(YEAR|MONTH FROM ...).\n"
            f"Every FROM/JOIN must reference tables as '{settings.nl2sql_db_prefix}.table' and assign an alias (e.g. FROM {settings.nl2sql_db_prefix}.tickets_jira AS t).\n"
            "After introducing an alias, reuse it everywhere (SELECT, WHERE, subqueries) instead of the raw table name.\n"
            "Never invent table or column names: use them exactly as provided (e.g. if only 'tickets_jira' exists, do NOT use 'tickets')."
        )
        hints = ""
        if date_hints:
            hint_lines = [f"- {settings.nl2sql_db_prefix}.{t}: {', '.join(cols)}" for t, cols in date_hints.items()]
            hints = "\nDate-like columns (cast before date ops):\n" + "\n".join(hint_lines)
        samples_section = f"\n\nSamples:\n{samples_blob}" if samples_blob else ""
        user = (
            f"Available tables and columns:\n{tables_blob}{hints}{samples_section}\n\n"
            f"Question: {question}\n"
            f"Produce a single SQL query using only {settings.nl2sql_db_prefix}.* tables."
        )
        resp = client.chat_completions(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0,
        )
        text = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        sql = _extract_sql(text)
        sql = _rewrite_date_functions(sql)
        if not _is_select_only(sql):
            raise RuntimeError("Generated SQL is invalid or not SELECT-only")
        _ensure_required_prefix(sql)
        return sql

    def plan(self, *, question: str, schema: Dict[str, List[str]], max_steps: int) -> List[Dict[str, str]]:
        client, model = self._client_and_model()
        tables_desc = []
        for t, cols in schema.items():
            col_list = ", ".join(cols)
            tables_desc.append(f"- {settings.nl2sql_db_prefix}.{t}({col_list})")
        tables_blob = "\n".join(tables_desc)
        # Optional samples
        samples_blob = ""
        if settings.nl2sql_include_samples:
            repo = DataRepository(tables_dir=Path(settings.tables_dir))
            rows_per = max(1, settings.nl2sql_rows_per_table)
            trunc = max(10, settings.nl2sql_value_truncate)
            parts: List[str] = []
            for t in schema.keys():
                p = repo._resolve_table_path(t)
                if not p:
                    continue
                try:
                    delim = "," if p.suffix.lower() == ".csv" else "\t"
                    with p.open("r", encoding="utf-8", newline="") as f:
                        reader = csv.DictReader(f, delimiter=delim)
                        rows = []
                        for i, row in enumerate(reader):
                            if i >= rows_per:
                                break
                            rows.append({k: (str(v)[:trunc] if v is not None else None) for k, v in row.items()})
                        if rows:
                            parts.append(f"Table {settings.nl2sql_db_prefix}.{t} sample rows (max {rows_per}):\n{rows}")
                except Exception:
                    continue
            samples_blob = "\n\n".join(parts)

        system = (
            "You are a query planner for analytics. \n"
            "Goal: break the question into up to N SQL queries (SELECT-only) that run on MindsDB (MySQL-like).\n"
            f"Use only tables under '{settings.nl2sql_db_prefix}.' schema.\n"
            "Date columns are TEXT 'YYYY-MM-DD'; CAST(NULLIF(col,'None') AS DATE) and EXTRACT(YEAR|MONTH ...) must be used.\n"
            f"Every FROM/JOIN must reference tables as '{settings.nl2sql_db_prefix}.table' and assign an alias (e.g. FROM {settings.nl2sql_db_prefix}.tickets_jira AS t).\n"
            "After introducing an alias, reuse it everywhere (SELECT, WHERE, subqueries) instead of the raw table name.\n"
            "Never invent table or column names: use them exactly as provided (if a table is 'tickets_jira', do NOT rename it).\n"
            "Return JSON only with the shape: {\"queries\":[{\"purpose\":str,\"sql\":str}, ...]} — no prose."
        )
        user = (
            f"Available tables and columns:\n{tables_blob}\n\n"
            + (f"Samples:\n{samples_blob}\n\n" if samples_blob else "")
            + f"Max steps: {max_steps}. Question: {question}"
        )
        resp = client.chat_completions(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0,
        )
        text = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        # Extract JSON
        blob = text
        if "```" in text:
            parts = text.split("```")
            if len(parts) >= 2:
                blob = parts[1]
                if blob.lower().startswith("json\n"):
                    blob = blob.split("\n", 1)[-1]
        try:
            data = json.loads(blob)
        except Exception as e:
            raise RuntimeError(f"Plan JSON invalid: {e}")
        queries = data.get("queries") if isinstance(data, dict) else None
        if not isinstance(queries, list) or not queries:
            raise RuntimeError("Plan vide ou invalide")
        out: List[Dict[str, str]] = []
        for q in queries[:max_steps]:
            purpose = str(q.get("purpose", "")).strip()
            sql = _extract_sql(str(q.get("sql", "")))
            if not purpose or not sql:
                continue
            sql = _rewrite_date_functions(sql)
            if not _is_select_only(sql):
                raise RuntimeError("Une requête du plan n'est pas un SELECT")
            _ensure_required_prefix(sql)
            out.append({"purpose": purpose, "sql": sql})
        if not out:
            raise RuntimeError("Aucune requête exploitable dans le plan")
        return out

    def synthesize(self, *, question: str, evidence: List[Dict[str, object]]) -> str:
        client, model = self._client_and_model()
        system = (
            "You are an analyst. Given a question and the results of prior SQL queries,"
            " write a concise answer in French. Use numbers and be precise."
            " If data is insufficient, say so. Do not include SQL in the final answer."
        )
        user = json.dumps({"question": question, "evidence": evidence}, ensure_ascii=False)
        resp = client.chat_completions(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0,
        )
        return resp.get("choices", [{}])[0].get("message", {}).get("content", "")

    # --- Multi‑agent helpers -------------------------------------------------
    def explore(
        self,
        *,
        question: str,
        schema: Dict[str, List[str]],
        max_steps: int,
        observations: str | None = None,
    ) -> List[Dict[str, str]]:
        """Ask the LLM to propose small exploratory SELECT queries.

        The goal is to quickly learn about value ranges and categories related to the question
        (e.g., DISTINCT values, MIN/MAX, sample rows, small GROUP BY counts).
        Returns a list of {"purpose", "sql"}.
        """
        client, model = self._client_and_model()
        tables_desc = []
        for t, cols in schema.items():
            col_list = ", ".join(cols)
            tables_desc.append(f"- {settings.nl2sql_db_prefix}.{t}({col_list})")
        tables_blob = "\n".join(tables_desc)

        system = (
            "You are a data explorer agent. Propose up to N short SELECT queries that help\n"
            "understand the data relevant to the question: small DISTINCT lists, MIN/MAX for dates\n"
            "or numbers, COUNTs by key categories, and a few sample rows (LIMIT ≤ 20).\n"
            f"Use only the '{settings.nl2sql_db_prefix}.' schema and always add an alias after each table.\n"
            "All queries must be SELECT‑only, safe to execute, and return quickly.\n"
            "Return JSON only: {\"queries\":[{\"purpose\":str,\"sql\":str}, ...]}. No prose."
        )
        obs_section = (f"\nObservations to consider:\n{observations}\n" if observations else "")
        user = (
            f"Available tables and columns:\n{tables_blob}\n\n"
            f"Max steps: {max_steps}. Question: {question}\n"
            f"Focus on columns likely involved in the question.\n"
            + obs_section
        )
        resp = client.chat_completions(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0,
        )
        text = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        blob = text
        if "```" in text:
            parts = text.split("```")
            if len(parts) >= 2:
                blob = parts[1]
                if blob.lower().startswith("json\n"):
                    blob = blob.split("\n", 1)[-1]
        try:
            data = json.loads(blob)
        except Exception as e:
            raise RuntimeError(f"Exploration JSON invalide: {e}")
        queries = data.get("queries") if isinstance(data, dict) else None
        if not isinstance(queries, list) or not queries:
            raise RuntimeError("Aucune requête exploratoire proposée")
        out: List[Dict[str, str]] = []
        for q in queries[:max_steps]:
            purpose = str(q.get("purpose", "")).strip()
            sql = _extract_sql(str(q.get("sql", "")))
            if not purpose or not sql:
                continue
            sql = _rewrite_date_functions(sql)
            if not _is_select_only(sql):
                raise RuntimeError("Une requête exploratoire n'est pas un SELECT")
            _ensure_required_prefix(sql)
            out.append({"purpose": purpose, "sql": sql})
        if not out:
            raise RuntimeError("Aucune requête exploratoire exploitable")
        return out

    def generate_with_evidence(
        self,
        *,
        question: str,
        schema: Dict[str, List[str]],
        evidence: List[Dict[str, object]],
    ) -> str:
        """Produce a single final SELECT using prior exploration evidence.

        The model must return only one SELECT that answers the question precisely.
        """
        client, model = self._client_and_model()
        tables_desc = []
        for t, cols in schema.items():
            col_list = ", ".join(cols)
            tables_desc.append(f"- {settings.nl2sql_db_prefix}.{t}({col_list})")
        system = (
            "You are an analyst agent. Given a natural language question and the results of prior\n"
            "exploratory queries, write ONE SQL SELECT that directly answers the question.\n"
            "Dialect: MindsDB (MySQL-like). Rules: SELECT-only; prefix tables with the allowed schema;\n"
            "CAST(NULLIF(date_col,'None') AS DATE) and use EXTRACT for date parts.\n"
            "Return only the SQL (optionally fenced). No explanation."
        )
        user = json.dumps(
            {
                "question": question,
                "tables": tables_desc,
                "evidence": evidence,
                "rules": {
                    "schema_prefix": settings.nl2sql_db_prefix,
                },
            },
            ensure_ascii=False,
        )
        resp = client.chat_completions(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0,
        )
        text = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        sql = _extract_sql(text)
        sql = _rewrite_date_functions(sql)
        if not _is_select_only(sql):
            raise RuntimeError("La requête finale générée n'est pas un SELECT")
        _ensure_required_prefix(sql)
        return sql

    def propose_axes(
        self,
        *,
        question: str,
        schema: Dict[str, List[str]],
        evidence: List[Dict[str, object]] | None = None,
        max_items: int = 3,
    ) -> List[Dict[str, str]]:
        """Suggest chart axes and aggregations based on the question and exploration evidence.

        Returns a list of objects with keys: x, y (optional), agg (optional), chart (bar|line|pie|table), reason.
        """
        client, model = self._client_and_model()
        tables_desc = []
        for t, cols in schema.items():
            col_list = ", ".join(cols)
            tables_desc.append(f"- {settings.nl2sql_db_prefix}.{t}({col_list})")
        payload = {
            "question": question,
            "tables": tables_desc,
            "evidence_preview": (
                [
                    {
                        "purpose": str(e.get("purpose", "")),
                        "sql": str(e.get("sql", ""))[:200],
                        "columns": e.get("columns", []),
                        "row_count": len(e.get("rows", []) if isinstance(e.get("rows"), list) else []),
                    }
                    for e in (evidence or [])
                ]
            ),
            "max_items": max_items,
        }
        system = (
            "You are a visualization assistant. Propose up to N concise axis suggestions\n"
            "for charts that would best communicate the answer to the question, based on the columns\n"
            "available and any exploratory findings. Prefer simple bar/line charts; fall back to 'table' when unclear.\n"
            "Return ONLY JSON: {\"axes\":[{\"x\":str,\"y\":str?,\"agg\":str?,\"chart\":str,\"reason\":str}...]}."
        )
        resp = client.chat_completions(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            temperature=0,
        )
        text = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        blob = text
        if "```" in text:
            parts = text.split("```")
            if len(parts) >= 2:
                blob = parts[1]
                if blob.lower().startswith("json\n"):
                    blob = blob.split("\n", 1)[-1]
        try:
            data = json.loads(blob)
        except Exception as e:
            raise RuntimeError(f"Axes JSON invalide: {e}")
        axes = data.get("axes") if isinstance(data, dict) else None
        if not isinstance(axes, list) or not axes:
            raise RuntimeError("Aucune proposition d'axes")
        out: List[Dict[str, str]] = []
        for a in axes[: max(1, max_items)]:
            x = str(a.get("x", "")).strip()
            y = str(a.get("y", "")).strip() if a.get("y") is not None else ""
            chart = str(a.get("chart", "")).strip() or "table"
            reason = str(a.get("reason", "")).strip()
            agg = str(a.get("agg", "")).strip() if a.get("agg") is not None else ""
            if not x:
                continue
            out.append({"x": x, "y": y, "agg": agg, "chart": chart, "reason": reason})
        if not out:
            raise RuntimeError("Aucune proposition d'axes exploitable")
        return out

    # Writer agent: interpret results with Constat / Action / Question
    def write(self, *, question: str, evidence: List[Dict[str, object]]) -> str:
        client, model = self._client_and_model()
        system = (
            "Tu es un rédacteur‑analyste français. À partir des tableaux de résultats fournis, "
            "rédige une synthèse brève en prose directe, en 1 à 2 paragraphes courts.\n"
            "Paragraphe 1: intègre le constat avec des chiffres précis (comptes, pourcentages, tendances). 2–4 phrases.\n"
            "Paragraphe 2 (si pertinent): formule UNE recommandation concrète (si justifiée) OU une question claire en cas d’incertitude. 1–2 phrases.\n"
            "Contraintes: pas de SQL, pas de jargon inutile; français professionnel; 3–6 phrases au total; pas d’intitulés ni d’en‑têtes; "
            "n’emploie jamais explicitement les mots ‘Constat’, ‘Action proposée’ ou ‘Question à trancher’. Pas de listes/puces.\n"
            "Sépare bien les paragraphes par une ligne vide."
        )
        payload = {
            "question": question,
            "evidence": evidence,
        }
        resp = client.chat_completions(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            temperature=0,
        )
        return resp.get("choices", [{}])[0].get("message", {}).get("content", "")

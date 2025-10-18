from __future__ import annotations

from dataclasses import dataclass
import re
import csv
from pathlib import Path
from typing import Dict, List, Optional
import json

from ..core.config import settings
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


@dataclass
class NL2SQLService:
    """Generate SQL from NL using the configured OpenAI‑compatible LLM.

    Strict rules: SELECT‑only, target DB prefix (e.g., files.), row limit.
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
        return OpenAICompatibleClient(base_url=base_url, api_key=api_key), str(model)

    def generate(self, *, question: str, schema: Dict[str, List[str]]) -> str:
        client, model = self._client_and_model()
        tables_desc = []
        for t, cols in schema.items():
            col_list = ", ".join(cols)
            tables_desc.append(f"- {settings.nl2sql_db_prefix}.{t}({col_list})")
        tables_blob = "\n".join(tables_desc)
        limit = settings.nl2sql_max_rows
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
            f"Return exactly ONE SELECT query with LIMIT {limit}. No comments. No explanations.\n"
            "Rules: SELECT-only; never modify data. Date-like columns are TEXT in 'YYYY-MM-DD'.\n"
            "Always CAST(NULLIF(date_col,'None') AS DATE) before date filters and use EXTRACT(YEAR|MONTH FROM ...)."
        )
        hints = ""
        if date_hints:
            hint_lines = [f"- {settings.nl2sql_db_prefix}.{t}: {', '.join(cols)}" for t, cols in date_hints.items()]
            hints = "\nDate-like columns (cast before date ops):\n" + "\n".join(hint_lines)
        samples_section = f"\n\nSamples:\n{samples_blob}" if samples_blob else ""
        user = (
            f"Available tables and columns:\n{tables_blob}{hints}{samples_section}\n\n"
            f"Question: {question}\n"
            f"Produce a single SQL query using only {settings.nl2sql_db_prefix}.* tables. Always include LIMIT {limit}."
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
        # Enforce LIMIT if missing (belt & suspenders) and avoid duplicates
        low = sql.lower()
        if re.search(r"\blimit\b", low) is None:
            sql = f"{sql} LIMIT {limit}"
        else:
            # If a trailing duplicate LIMIT was accidentally appended by a prior run, drop the last one
            if re.search(r"\blimit\b.*\blimit\b", low):
                sql = re.sub(r"(?is)\s+limit\s+\d+\s*$", "", sql)
        return sql

    def plan(self, *, question: str, schema: Dict[str, List[str]], max_steps: int) -> List[Dict[str, str]]:
        client, model = self._client_and_model()
        tables_desc = []
        for t, cols in schema.items():
            col_list = ", ".join(cols)
            tables_desc.append(f"- {settings.nl2sql_db_prefix}.{t}({col_list})")
        tables_blob = "\n".join(tables_desc)
        limit = settings.nl2sql_max_rows
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
            f"Use only tables under '{settings.nl2sql_db_prefix}.' and always include LIMIT {limit}.\n"
            "Date columns are TEXT 'YYYY-MM-DD'; CAST(NULLIF(col,'None') AS DATE) and EXTRACT(YEAR|MONTH ...) must be used.\n"
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
            low = sql.lower()
            if re.search(r"\blimit\b", low) is None:
                sql = f"{sql} LIMIT {limit}"
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

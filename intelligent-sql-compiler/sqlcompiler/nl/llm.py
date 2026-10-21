"""Optional LLM-based NL-to-SQL and rewrite generator with compiler-in-the-loop repair."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Callable, Optional
from urllib import request as url_request

from sqlcompiler.frontend.parser import parse_sql, ParseError
from sqlcompiler.semantic.symbols import Catalog
from sqlcompiler.semantic.typecheck import SemanticAnalyzer
from sqlcompiler.nl.nl_to_sql import generate_sql as generate_sql_template


def get_llm_config() -> dict[str, str]:
    """Retrieve LLM provider settings from environment variables or Streamlit secrets."""
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    model = os.getenv("LLM_MODEL", "").strip()
    api_key = os.getenv("LLM_API_KEY", "").strip()
    base_url = os.getenv("LLM_BASE_URL", "").strip()

    # Attempt to read from Streamlit secrets if running inside Streamlit
    try:
        import streamlit as st
        if hasattr(st, "secrets"):
            provider = provider or st.secrets.get("LLM_PROVIDER", "")
            model = model or st.secrets.get("LLM_MODEL", "")
            api_key = api_key or st.secrets.get("LLM_API_KEY", "")
            base_url = base_url or st.secrets.get("LLM_BASE_URL", "")
    except Exception:
        pass

    return {
        "provider": provider or ("openai" if api_key else "none"),
        "model": model or "gpt-4o-mini",
        "api_key": api_key,
        "base_url": base_url or "https://api.openai.com/v1",
    }


def is_llm_configured() -> bool:
    """Returns True only if an LLM provider and credentials/URL are configured."""
    cfg = get_llm_config()
    return bool(cfg["api_key"] or (cfg["base_url"] and cfg["provider"] in ("ollama", "local")))


def format_schema_prompt(catalog: Catalog) -> str:
    """Format catalog schema metadata for LLM prompt."""
    lines = ["DATABASE SCHEMA (SQLite):"]
    for table_name, table_sym in sorted(catalog.tables.items()):
        cols = []
        for col_sym in table_sym.columns.values():
            null_str = "NULL" if col_sym.nullable else "NOT NULL"
            pk_str = " PRIMARY KEY" if col_sym.is_pk else ""
            cols.append(f"{col_sym.name} {col_sym.canonical_type} {null_str}{pk_str}")
        lines.append(f"CREATE TABLE {table_sym.name} (\n  " + ",\n  ".join(cols) + "\n);")
    return "\n".join(lines)


def strip_code_fences(text: str) -> str:
    """Remove markdown code blocks and extra whitespace from LLM output."""
    cleaned = text.strip()
    # Match ```sql ... ``` or ``` ... ```
    match = re.search(r"```(?:sql)?\s*([\s\S]*?)\s*```", cleaned, re.IGNORECASE)
    if match:
        cleaned = match.group(1).strip()
    # Strip any trailing semicolons or leading prompts
    lines = [line for line in cleaned.splitlines() if not line.strip().startswith("--")]
    cleaned = " ".join(lines).strip()
    return cleaned


def call_llm_api(
    prompt: str,
    system_prompt: str,
    config: Optional[dict[str, str]] = None,
    client: Optional[Callable[[str, str], str]] = None
) -> str:
    """
    Call the LLM provider API. If a client callable is passed (e.g. in tests),
    it is invoked directly without network calls.
    """
    if client is not None:
        return client(system_prompt, prompt)

    cfg = config or get_llm_config()
    if not is_llm_configured():
        raise RuntimeError("LLM is not configured. Set LLM_API_KEY or LLM_BASE_URL.")

    base_url = cfg["base_url"].rstrip("/")
    endpoint = f"{base_url}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg['api_key']}",
    }
    payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.0,
    }

    req = url_request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST"
    )
    with url_request.urlopen(req, timeout=10.0) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]


def generate_sql_with_compiler_guardrail(
    question: str,
    catalog: Optional[Catalog] = None,
    client: Optional[Callable[[str, str], str]] = None,
    max_repairs: int = 2
) -> dict[str, Any]:
    """
    Compiler-in-the-loop generator:
    1. Prompts LLM for SQL.
    2. Treats LLM output as UNTRUSTED source code.
    3. Runs parser + semantic analyzer + safety check.
    4. If it fails, feeds structured diagnostics back to LLM for repair (max 2 attempts).
    5. Falls back to deterministic template generator if LLM fails or is not configured.
    """
    if catalog is None:
        catalog = Catalog.default_university()

    repair_logs = []

    # If LLM is not configured and no mock client is supplied, fall back directly
    if not is_llm_configured() and client is None:
        try:
            sql = generate_sql_template(question)
            return {
                "success": True,
                "sql": sql,
                "source": "template",
                "repairs_attempted": 0,
                "repair_logs": [],
                "note": "Generative AI is disabled/unconfigured; deterministic template generator was used.",
            }
        except ValueError as exc:
            return {
                "success": False,
                "sql": None,
                "source": "none",
                "error": str(exc),
                "repairs_attempted": 0,
                "repair_logs": [],
            }

    system_prompt = (
        "You are an expert SQL compiler generator.\n"
        f"{format_schema_prompt(catalog)}\n\n"
        "Instructions:\n"
        "- Generate exactly one SQLite SELECT statement that answers the user's request.\n"
        "- Output ONLY the SELECT statement. Do NOT include markdown code fences, comments, or explanations."
    )

    current_prompt = f"User request: {question}"

    for attempt in range(max_repairs + 1):
        try:
            raw_response = call_llm_api(current_prompt, system_prompt, client=client)
            candidate_sql = strip_code_fences(raw_response)
        except Exception as exc:
            repair_logs.append(f"LLM API call failed: {exc}")
            break

        # Safety check 1: Disallow multi-statement or non-SELECT
        if not candidate_sql.upper().strip().startswith("SELECT"):
            error_msg = "Security constraint: Only SELECT queries are permitted."
            repair_logs.append(f"Attempt {attempt}: Rejected non-SELECT response: '{candidate_sql}'")
            if attempt < max_repairs:
                current_prompt = f"Previous SQL: {candidate_sql}\nError: {error_msg}\nPlease correct the query to be a single SELECT statement."
                continue
            break

        # Compiler Check 1: Hand-written Parser
        try:
            ast = parse_sql(candidate_sql)
        except ParseError as exc:
            repair_logs.append(f"Attempt {attempt} ParseError: {exc.message}")
            if attempt < max_repairs:
                current_prompt = f"Previous SQL: {candidate_sql}\nSyntax Error: {exc.message}\nSuggestion: {exc.suggestion}\nPlease fix the syntax error."
                continue
            break

        # Compiler Check 2: Semantic Analyzer (Symbols & Type Checker)
        analyzer = SemanticAnalyzer(catalog)
        val_result = analyzer.analyze(ast, raw_sql=candidate_sql)
        if not val_result["valid"]:
            repair_logs.append(f"Attempt {attempt} SemanticError: {val_result['error_message']}")
            if attempt < max_repairs:
                current_prompt = f"Previous SQL: {candidate_sql}\nSemantic Error: {val_result['error_message']}\nPlease correct the query using the provided schema."
                continue
            break

        # Both compiler front-end stages passed!
        source_label = "llm" if attempt == 0 else f"llm (after {attempt} repair{'s' if attempt > 1 else ''})"
        return {
            "success": True,
            "sql": candidate_sql,
            "source": source_label,
            "repairs_attempted": attempt,
            "repair_logs": repair_logs,
            "note": f"Validated by hand-written compiler front end after {attempt} repair attempt(s).",
        }

    # All LLM attempts failed -> Fall back to deterministic template generator
    try:
        sql = generate_sql_template(question)
        return {
            "success": True,
            "sql": sql,
            "source": "template (fallback)",
            "repairs_attempted": len(repair_logs),
            "repair_logs": repair_logs,
            "note": "LLM generation failed compiler verification; fell back safely to deterministic template generator.",
        }
    except ValueError as exc:
        return {
            "success": False,
            "sql": None,
            "source": "failed",
            "error": f"LLM generation failed compiler guardrails ({'; '.join(repair_logs)}) and template fallback was not matched.",
            "repairs_attempted": len(repair_logs),
            "repair_logs": repair_logs,
        }

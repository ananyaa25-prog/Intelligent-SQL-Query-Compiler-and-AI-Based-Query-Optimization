"""Natural Language processing module: templates, optional LLM, and compiler-in-the-loop."""

from sqlcompiler.nl.nl_to_sql import generate_sql
from sqlcompiler.nl.llm import (
    is_llm_configured,
    get_llm_config,
    generate_sql_with_compiler_guardrail,
    strip_code_fences,
)

__all__ = [
    "generate_sql",
    "is_llm_configured",
    "get_llm_config",
    "generate_sql_with_compiler_guardrail",
    "strip_code_fences",
]

"""chinese_workflow.llm — the shared, cached, replayable model client (docs/outliner-design.md §10).

    from chinese_workflow.llm import LLMConfig, call
    out = call("gloss", {"system": ..., "messages": [...], "schema_name": "gloss"}, schema,
               LLMConfig(adapter="replay", cassette="tests/fixtures/llm-cassettes/x.jsonl"))

  client    call(), LLMConfig, the errors, request_hash(), api_schema(), DEFAULT_MODEL
  adapters  none | replay | claude | interactive
  cache     <run_dir>/llm/responses.jsonl (and cassettes of the same shape)
  ledger    <run_dir>/llm/ledger.json: tokens, cost, budget cap

This package imports only the standard library, jsonschema and chinese_workflow.common; the
`anthropic` SDK (the optional `llm` extra) is imported lazily by the claude adapter only.
"""

from .client import (
    ADAPTER_NAMES,
    DEFAULT_MODEL,
    BudgetExceeded,
    InvalidResponse,
    LLMConfig,
    LLMError,
    NoModel,
    PendingInteractive,
    Refusal,
    ReplayMiss,
    api_schema,
    call,
    request_hash,
    validation_errors,
)

__all__ = [
    "ADAPTER_NAMES",
    "DEFAULT_MODEL",
    "BudgetExceeded",
    "InvalidResponse",
    "LLMConfig",
    "LLMError",
    "NoModel",
    "PendingInteractive",
    "Refusal",
    "ReplayMiss",
    "api_schema",
    "call",
    "request_hash",
    "validation_errors",
]

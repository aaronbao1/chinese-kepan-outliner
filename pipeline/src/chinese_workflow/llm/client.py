"""chinese_workflow.llm.client — one validated, cached, replayable structured-output model call.

docs/outliner-design.md §10; plan TR5 ("llm/"), M6, Appendix C (run directory), Appendix E (cost).

Input : call(task, request, schema, config)
          task     a short task name, e.g. 'resolver/root-spans', 'gloss'
          request  {"system": str, "messages": [{"role": "user", "content": str | [blocks]}, ...],
                    "schema_name": str, "meta": {...}}   ("meta" is optional: caller bookkeeping,
                    part of the hash, never sent to the model)
          schema   the JSON Schema (draft 2020-12) the structured output must satisfy
          config   LLMConfig
Output: the response object (a dict), validated against `schema` with jsonschema.
Files (all under <run_dir>/llm/, only when config.run_dir is set):
          responses.jsonl   the cache, one record per answered request:
                            {hash, task, model, adapter, request, response, usage, returned_model,
                            date}
          invalid.jsonl     responses that failed parsing or validation, or were refused (never
                            used)
          ledger.json       token and cost ledger of the claude adapter (llm/ledger.py)
          requests/<hash>.json, requests/<hash>.md, responses/<hash>.json   interactive adapter

Cache key: sha256 of the canonical JSON (common.jsonio.canonical) of {task, model, request, schema}.
The cache is consulted first by every adapter, so a re-run makes no repeated model call.

Adapters (llm/adapters.py):
  none         raises NoModel (callers degrade: the pipeline runs with no model, design §2 rule 6);
  replay       looks the hash up in config.cassette (JSONL, same record shape); a miss raises
               ReplayMiss;
  claude       the Anthropic Messages API with JSON-schema structured output (output_config.format),
               streamed; the SDK (`anthropic`, the optional `llm` extra) is imported lazily;
               credentials from ANTHROPIC_API_KEY (or the SDK's other sources); usage and cost go to
               the ledger; a budget cap (config.budget_usd) is checked before every call with a
               count_tokens pre-flight;
  interactive  writes requests/<hash>.json and a human/Claude-Code-readable requests/<hash>.md,
               returns responses/<hash>.json when that file exists and validates, else raises
               PendingInteractive.

Default model: DEFAULT_MODEL = "claude-opus-5". Chosen 2026-09-27 from the bundled claude-api skill
(model table cached 2026-06-24), which makes claude-opus-5 the default for new code unless the user
names another model; the plan (TR5; Appendix H item 13 "opus-5 default") and design §10 fix the same
default. The skill lists Claude Fable 5.1 (`claude-fable-5-1`, $10 / $50 per MTok input / output) as
the most capable widely released model, but reserves it for an explicit request; claude-opus-5 costs
$5 / $25 per MTok. Change it with LLMConfig.model (the ledger prices both).

Determinism: the cache key, the request files and the cache records are canonical JSON; only the
record's `date` and the ledger's timestamps depend on the clock.
"""

from __future__ import annotations

import copy
import datetime as _dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jsonschema

from ..common.jsonio import sha256_json

DEFAULT_MODEL = "claude-opus-5"
ADAPTER_NAMES = ("none", "replay", "claude", "interactive")


# --------------------------------------------------------------------------------------- errors


class LLMError(RuntimeError):
    """Base class of every error the client raises."""


class NoModel(LLMError):
    """Adapter 'none' (and no cached response): no model is available; callers degrade."""


class PendingInteractive(LLMError):
    """Interactive adapter: request files were written and await a response file.

    .requests = [paths of the request .json files awaiting a response] (a .md prompt sits beside
    each)."""

    def __init__(self, requests, message: str | None = None):
        self.requests = [str(p) for p in requests]
        super().__init__(
            message
            or "%d interactive request(s) await a response: %s"
            % (len(self.requests), ", ".join(self.requests))
        )


class InvalidResponse(LLMError):
    """A response that is not JSON, was truncated, or fails its schema: recorded, never used."""

    def __init__(self, message: str, errors: list | None = None):
        self.errors = list(errors or [])
        super().__init__(message)


class Refusal(LLMError):
    """The model declined the request (stop_reason 'refusal', after any server-side fallback)."""


class ReplayMiss(LLMError):
    """Adapter 'replay': the request hash is not in the cassette."""


class BudgetExceeded(LLMError):
    """The claude adapter would exceed config.budget_usd (or cannot price the model)."""


# --------------------------------------------------------------------------------------- config


@dataclass
class LLMConfig:
    """How model calls are made. Only adapter, model, run_dir and cassette affect what is returned;
    the rest shape claude-adapter calls (not part of the cache key)."""

    adapter: str = "none"
    model: str = DEFAULT_MODEL
    run_dir: Path | None = None
    cassette: Path | None = None
    max_tokens: int = 64000  # thinking + output; the claude adapter streams, so no HTTP timeout
    budget_usd: float | None = None
    effort: str | None = "high"  # output_config.effort; None = the model's default
    fallbacks: str | None = "default"  # server-side refusal fallbacks (skill default); None = off
    cache_ttl: str = "5m"  # prompt-cache TTL of the system block: '5m' or '1h' (plan TR5)
    client: Any = field(default=None, repr=False, compare=False)  # injected SDK client (tests)
    _memory_ledger: Any = field(default=None, init=False, repr=False, compare=False)

    def __post_init__(self):
        if self.adapter not in ADAPTER_NAMES:
            raise ValueError(
                "unknown adapter %r (one of %s)" % (self.adapter, ", ".join(ADAPTER_NAMES))
            )
        if self.run_dir is not None:
            self.run_dir = Path(self.run_dir)
        if self.cassette is not None:
            self.cassette = Path(self.cassette)
        if self.cache_ttl not in ("5m", "1h"):
            raise ValueError("cache_ttl must be '5m' or '1h'")

    @property
    def llm_dir(self) -> Path | None:
        return self.run_dir / "llm" if self.run_dir is not None else None


# ---------------------------------------------------------------------------------- the call


def request_hash(task: str, request: dict, schema: dict, model: str) -> str:
    """The cache key: sha256 of canonical {task, model, request, schema}."""
    return sha256_json({"task": task, "model": model, "request": request, "schema": schema})


def check_request(request: dict) -> None:
    if not isinstance(request, dict):
        raise TypeError("request must be a dict")
    missing = [k for k in ("system", "messages", "schema_name") if k not in request]
    if missing:
        raise ValueError("request lacks %s" % ", ".join(missing))
    if not isinstance(request["system"], str) or not isinstance(request["messages"], list):
        raise TypeError("request.system must be a str and request.messages a list")
    extra = set(request) - {"system", "messages", "schema_name", "meta"}
    if extra:
        raise ValueError("unknown request keys: %s" % ", ".join(sorted(extra)))


def validation_errors(schema: dict, response) -> list:
    """Sorted, rendered jsonschema errors of `response` against `schema` ([] = valid)."""
    cls = jsonschema.validators.validator_for(schema, default=jsonschema.Draft202012Validator)
    out = []
    for err in cls(schema).iter_errors(response):
        where = "/".join(str(p) for p in err.absolute_path) or "<root>"
        out.append("%s: %s" % (where, err.message))
    return sorted(out)


def today() -> str:
    return _dt.datetime.now(_dt.UTC).date().isoformat()


def call(
    task: str, request: dict, schema: dict, config: LLMConfig, info: dict | None = None
) -> dict:
    """One structured-output call: cache, then the configured adapter; the response is validated
    against `schema`. Raises NoModel, PendingInteractive, ReplayMiss, InvalidResponse, Refusal or
    BudgetExceeded (all LLMError). When `info` is a dict it receives {hash, cached, returned_model}
    (returned_model: the model id the API reported, which differs from config.model after a
    server-side fallback; None for interactive answers)."""
    from . import adapters  # adapters import this module
    from .cache import ResponseCache, record_invalid

    check_request(request)
    key = request_hash(task, request, schema, config.model)
    cache = ResponseCache(config.llm_dir / "responses.jsonl") if config.llm_dir else None
    if cache is not None:
        hit = cache.get(key)
        if hit is not None:
            errors = validation_errors(schema, hit.get("response"))
            if errors:
                raise InvalidResponse("cached response %s fails its schema" % key[:12], errors)
            if info is not None:
                info.update(hash=key, cached=True, returned_model=hit.get("returned_model"))
            return copy.deepcopy(hit["response"])

    result = adapters.ADAPTERS[config.adapter](task, request, schema, config, key)
    base = {"hash": key, "task": task, "model": config.model, "adapter": config.adapter}
    if result.get("error"):
        if config.llm_dir:
            record_invalid(
                config.llm_dir / "invalid.jsonl",
                dict(base, error=result["error"], raw=result.get("raw"), date=today()),
            )
        exc = Refusal if result.get("error_kind") == "refusal" else InvalidResponse
        raise exc("%s (%s, request %s)" % (result["error"], task, key[:12]))
    response = result["response"]
    errors = validation_errors(schema, response)
    if errors:
        if config.llm_dir:
            record_invalid(
                config.llm_dir / "invalid.jsonl",
                dict(base, error="schema", errors=errors, raw=response, date=today()),
            )
        raise InvalidResponse(
            "response to %s (request %s) fails its schema: %s"
            % (task, key[:12], "; ".join(errors[:3])),
            errors,
        )
    if cache is not None:
        cache.put(
            dict(
                base,
                request=request,
                response=response,
                usage=result.get("usage"),
                returned_model=result.get("returned_model"),
                date=today(),
            )
        )
    if info is not None:
        info.update(hash=key, cached=False, returned_model=result.get("returned_model"))
    return copy.deepcopy(response)


# ------------------------------------------------------------------ schema for the Messages API

# JSON-Schema keywords structured outputs do not accept (claude-api skill,
# shared/tool-use-concepts.md "JSON Schema Limitations": numerical, string-length and complex array
# constraints). They stay in the repository schema and are enforced client-side by
# validation_errors().
_UNSUPPORTED = {
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    "minLength",
    "maxLength",
    "pattern",
    "minItems",
    "maxItems",
    "uniqueItems",
    "$schema",
    "$id",
    "$comment",
}
_SUPPORTED_FORMATS = {
    "date-time",
    "time",
    "date",
    "duration",
    "email",
    "hostname",
    "uri",
    "ipv4",
    "ipv6",
    "uuid",
}
_SCHEMA_MAPS = ("properties", "$defs", "definitions", "patternProperties")
_SCHEMA_LISTS = ("anyOf", "allOf", "oneOf", "prefixItems")
_SCHEMA_ONE = ("items", "additionalProperties", "not", "contains", "if", "then", "else")


def api_schema(schema):
    """The schema as sent in output_config.format: unsupported constraint keywords removed (only
    where they are keywords, never property names), everything else kept."""
    if not isinstance(schema, dict):
        return schema
    out = {}
    for key, value in schema.items():
        if key in _SCHEMA_MAPS and isinstance(value, dict):
            out[key] = {name: api_schema(sub) for name, sub in value.items()}
        elif key in _SCHEMA_LISTS and isinstance(value, list):
            out[key] = [api_schema(sub) for sub in value]
        elif key in _SCHEMA_ONE and isinstance(value, dict):
            out[key] = api_schema(value)
        elif key in _UNSUPPORTED or key == "format" and value not in _SUPPORTED_FORMATS:
            continue
        else:
            out[key] = copy.deepcopy(value)
    return out

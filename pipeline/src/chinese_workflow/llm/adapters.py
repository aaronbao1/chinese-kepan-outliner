"""chinese_workflow.llm.adapters — the four ways a request is answered (docs/outliner-design.md
§10).

Input : (task, request, schema, config, key) from client.call(), after a cache miss.
Output: {"response": obj, "usage": dict | None, "returned_model": str | None}, or
        {"error": str, "error_kind": "invalid" | "refusal", "raw": ...} for a response that must be
        recorded and rejected. client.call() validates and caches; adapters never touch the cache.

  none         raise NoModel.
  replay       the cassette record with this hash (config.cassette, JSONL); a miss raises
               ReplayMiss.
  claude       Anthropic Messages API, structured output via output_config.format (json_schema),
               streamed (.get_final_message()), system prompt as one text block with a cache_control
               breakpoint (the resolver's frozen prefix, plan M6), effort in output_config,
               server-side refusal fallbacks ("default", beta server-side-fallback-2026-07-01)
               unless config.fallbacks is None; thinking left at the model default (adaptive on Opus
               5). SDK usage per the bundled claude-api skill (python/claude-api README, tool-use.md
               "Structured Outputs", shared/model-migration.md "Migrating to Claude Opus 5").
  interactive  a Claude Code session answers: requests/<hash>.json + requests/<hash>.md are written;
               responses/<hash>.json is read when present.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..common.jsonio import dumps
from .cache import ResponseCache
from .client import LLMConfig, NoModel, PendingInteractive, ReplayMiss, api_schema, today
from .ledger import Ledger

FALLBACK_BETA = "server-side-fallback-2026-07-01"


# ------------------------------------------------------------------------------------------ none


def none_adapter(task, request, schema, config: LLMConfig, key):
    raise NoModel("adapter 'none': no model call for %s (request %s)" % (task, key[:12]))


# ---------------------------------------------------------------------------------------- replay


def replay_adapter(task, request, schema, config: LLMConfig, key):
    if config.cassette is None:
        raise ReplayMiss("adapter 'replay' needs config.cassette")
    rec = ResponseCache(config.cassette).get(key)
    if rec is None:
        raise ReplayMiss(
            "request %s (%s) is not in cassette %s; re-record it with the interactive "
            "or claude adapter" % (key, task, config.cassette)
        )
    return {
        "response": rec.get("response"),
        "usage": rec.get("usage"),
        "returned_model": rec.get("returned_model"),
    }


# ---------------------------------------------------------------------------------------- claude


def _make_client():
    try:
        import anthropic  # the optional `llm` extra: pip install -e 'pipeline[llm]'
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise RuntimeError(
            "adapter 'claude' needs the anthropic SDK: pip install -e 'pipeline[llm]'"
        ) from exc
    return anthropic.Anthropic()  # credentials: ANTHROPIC_API_KEY, else the SDK's other sources


def _cache_control(ttl: str) -> dict:
    return {"type": "ephemeral"} if ttl == "5m" else {"type": "ephemeral", "ttl": "1h"}


def _usage(u) -> dict:
    keys = (
        "input_tokens",
        "output_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
    )
    return {k: int(getattr(u, k, 0) or 0) for k in keys}


def _estimate_input_tokens(client, model, system, messages) -> int:
    """count_tokens pre-flight (claude-api skill, shared/token-counting.md); on any failure a
    conservative character count (CJK text runs at about one token per character or more)."""
    try:
        return int(
            client.messages.count_tokens(model=model, system=system, messages=messages).input_tokens
        )
    except Exception:  # noqa: BLE001 - the estimate must never block on a counting failure
        return len(json.dumps([system, messages], ensure_ascii=False))


def claude_adapter(task, request, schema, config: LLMConfig, key):
    client = config.client if config.client is not None else _make_client()
    ledger = Ledger.for_config(config)
    system = [
        {
            "type": "text",
            "text": request["system"],
            "cache_control": _cache_control(config.cache_ttl),
        }
    ]
    messages = request["messages"]
    if config.budget_usd is not None:
        ledger.check_budget(
            config.budget_usd,
            config.model,
            _estimate_input_tokens(client, config.model, system, messages),
        )
    output_config = {"format": {"type": "json_schema", "schema": api_schema(schema)}}
    if config.effort:
        output_config["effort"] = config.effort
    params = {
        "model": config.model,
        "max_tokens": config.max_tokens,
        "system": system,
        "messages": messages,
        "output_config": output_config,
    }
    if config.fallbacks:
        stream_cm = client.beta.messages.stream(
            betas=[FALLBACK_BETA], fallbacks=config.fallbacks, **params
        )
    else:
        stream_cm = client.messages.stream(**params)
    with stream_cm as stream:
        message = stream.get_final_message()

    usage = _usage(getattr(message, "usage", None))
    returned = getattr(message, "model", None) or config.model
    ledger.add(
        key=key,
        task=task,
        model=config.model,
        returned_model=returned,
        usage=usage,
        cache_ttl=config.cache_ttl,
    )
    stop = getattr(message, "stop_reason", None)
    text = "".join(
        getattr(b, "text", "")
        for b in (getattr(message, "content", None) or [])
        if getattr(b, "type", None) == "text"
    )
    if stop == "refusal":
        details = getattr(message, "stop_details", None)
        return {
            "error": "model refused (category %s)" % getattr(details, "category", None),
            "error_kind": "refusal",
            "raw": text,
        }
    if stop == "max_tokens":
        return {
            "error": "truncated at max_tokens=%d" % config.max_tokens,
            "error_kind": "invalid",
            "raw": text,
        }
    try:
        response = json.loads(text)
    except json.JSONDecodeError as exc:
        return {"error": "response is not JSON: %s" % exc, "error_kind": "invalid", "raw": text}
    return {"response": response, "usage": usage, "returned_model": returned}


# ----------------------------------------------------------------------------------- interactive


def _message_text(message: dict) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    return "\n\n".join(b.get("text", "") for b in content or [] if isinstance(b, dict))


def render_request_md(task: str, request: dict, schema: dict, key: str, response_path: Path) -> str:
    """The prompt a Claude Code session answers (skills/chinese-kepan-outliner, resolve step)."""
    parts = [
        "# Model request %s" % key[:12],
        "",
        "- task: `%s`" % task,
        "- schema: `%s`" % request.get("schema_name"),
        "- full hash: `%s`" % key,
        "",
        "## What to do",
        "",
        (
            "Read the system prompt and the user message below and answer as the model would: a "
            "single JSON object that validates against the JSON Schema at the end, nothing else. "
            "Write it, UTF-8, to"
        ),
        "",
        "    %s" % response_path,
        "",
        (
            "then re-run the command that wrote this request; the pipeline validates the file "
            "before it uses it (an invalid file is rejected and logged in llm/invalid.jsonl)."
        ),
        "",
        "## System prompt",
        "",
        request["system"],
        "",
    ]
    for i, msg in enumerate(request["messages"], 1):
        parts += ["## Message %d (%s)" % (i, msg.get("role")), "", _message_text(msg), ""]
    parts += [
        "## JSON Schema of the answer",
        "",
        "```json",
        json.dumps(schema, ensure_ascii=False, indent=1),
        "```",
        "",
    ]
    return "\n".join(parts)


def interactive_adapter(task, request, schema, config: LLMConfig, key):
    if config.llm_dir is None:
        raise ValueError("adapter 'interactive' needs config.run_dir")
    req_json = config.llm_dir / "requests" / ("%s.json" % key)
    req_md = config.llm_dir / "requests" / ("%s.md" % key)
    resp = config.llm_dir / "responses" / ("%s.json" % key)
    if resp.exists():
        raw = resp.read_text(encoding="utf-8")
        try:
            response = json.loads(raw)
        except json.JSONDecodeError as exc:
            return {
                "error": "response file %s is not JSON: %s" % (resp, exc),
                "error_kind": "invalid",
                "raw": raw,
            }
        return {"response": response, "usage": None, "returned_model": None}
    req_json.parent.mkdir(parents=True, exist_ok=True)
    resp.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "hash": key,
        "task": task,
        "model": config.model,
        "request": request,
        "schema": schema,
        "response_path": str(resp),
        "date": today(),
    }
    if not req_json.exists():
        req_json.write_text(dumps(record), encoding="utf-8")
    req_md.write_text(render_request_md(task, request, schema, key, resp), encoding="utf-8")
    raise PendingInteractive([req_json])


ADAPTERS = {
    "none": none_adapter,
    "replay": replay_adapter,
    "claude": claude_adapter,
    "interactive": interactive_adapter,
}

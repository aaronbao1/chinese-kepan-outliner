"""chinese_workflow.llm: cache, replay, none, interactive and (with a fake SDK client) claude
adapters.

Fully offline: the anthropic SDK is not installed in the test venv and no API key is used; the
claude adapter is exercised through an injected fake client object that records the parameters it
receives.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from chinese_workflow.llm import (
    DEFAULT_MODEL,
    BudgetExceeded,
    InvalidResponse,
    LLMConfig,
    NoModel,
    PendingInteractive,
    Refusal,
    ReplayMiss,
    api_schema,
    call,
    request_hash,
)
from chinese_workflow.llm.adapters import FALLBACK_BETA
from chinese_workflow.llm.cache import read_records
from chinese_workflow.llm.ledger import cost_usd

LLM_PKG = Path(__file__).resolve().parents[2] / "pipeline" / "src" / "chinese_workflow" / "llm"

SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": ["answer", "score"],
    "properties": {
        "answer": {"type": "string", "minLength": 1},
        "score": {"type": "number", "minimum": 0, "maximum": 1},
    },
}
REQUEST = {
    "system": "You answer toy questions.",
    "messages": [{"role": "user", "content": "合成問題：一加一？"}],
    "schema_name": "toy",
}
GOOD = {"answer": "二", "score": 0.9}


def test_default_model_and_config_checks():
    assert DEFAULT_MODEL == "claude-opus-5"
    cfg = LLMConfig()
    assert cfg.adapter == "none" and cfg.model == DEFAULT_MODEL and cfg.llm_dir is None
    with pytest.raises(ValueError):
        LLMConfig(adapter="openai")
    assert LLMConfig(run_dir="x").llm_dir == Path("x") / "llm"


def test_request_hash_is_canonical_and_sensitive():
    a = request_hash("t", REQUEST, SCHEMA, "m")
    reordered = {k: REQUEST[k] for k in reversed(list(REQUEST))}
    assert request_hash("t", reordered, SCHEMA, "m") == a
    assert request_hash("t", REQUEST, SCHEMA, "m2") != a
    assert request_hash("t2", REQUEST, SCHEMA, "m") != a
    assert request_hash("t", dict(REQUEST, system="x"), SCHEMA, "m") != a


def test_bad_request_rejected():
    with pytest.raises(ValueError):
        call("t", {"system": "s", "messages": []}, SCHEMA, LLMConfig())
    with pytest.raises(ValueError):
        call("t", dict(REQUEST, model="x"), SCHEMA, LLMConfig())


def test_none_raises_nomodel(tmp_path):
    with pytest.raises(NoModel):
        call("t", REQUEST, SCHEMA, LLMConfig())
    with pytest.raises(NoModel):
        call("t", REQUEST, SCHEMA, LLMConfig(run_dir=tmp_path))


def test_interactive_roundtrip_and_cache(tmp_path):
    cfg = LLMConfig(adapter="interactive", run_dir=tmp_path)
    with pytest.raises(PendingInteractive) as exc:
        call("toy", REQUEST, SCHEMA, cfg)
    key = request_hash("toy", REQUEST, SCHEMA, cfg.model)
    [req] = exc.value.requests
    assert Path(req) == tmp_path / "llm" / "requests" / ("%s.json" % key)
    rec = json.loads(Path(req).read_text(encoding="utf-8"))
    assert rec["request"] == REQUEST and rec["schema"] == SCHEMA and rec["task"] == "toy"
    md = (tmp_path / "llm" / "requests" / ("%s.md" % key)).read_text(encoding="utf-8")
    assert rec["response_path"] in md and "合成問題" in md and '"score"' in md
    # still pending on a second call; writing the response file answers it
    with pytest.raises(PendingInteractive):
        call("toy", REQUEST, SCHEMA, cfg)
    Path(rec["response_path"]).write_text(json.dumps(GOOD, ensure_ascii=False), encoding="utf-8")
    assert call("toy", REQUEST, SCHEMA, cfg) == GOOD
    [cached] = read_records(tmp_path / "llm" / "responses.jsonl")
    assert cached["hash"] == key and cached["adapter"] == "interactive"
    assert cached["response"] == GOOD and cached["request"] == REQUEST
    assert set(cached) >= {
        "hash",
        "task",
        "model",
        "request",
        "response",
        "usage",
        "returned_model",
        "date",
    }
    # the cache is consulted first by every adapter, 'none' included
    assert call("toy", REQUEST, SCHEMA, LLMConfig(adapter="none", run_dir=tmp_path)) == GOOD


def test_interactive_invalid_response_rejected(tmp_path):
    cfg = LLMConfig(adapter="interactive", run_dir=tmp_path)
    with pytest.raises(PendingInteractive) as exc:
        call("toy", REQUEST, SCHEMA, cfg)
    resp = Path(
        json.loads(Path(exc.value.requests[0]).read_text(encoding="utf-8"))["response_path"]
    )
    resp.write_text(json.dumps({"answer": "二", "score": 2}), encoding="utf-8")  # maximum 1
    with pytest.raises(InvalidResponse) as bad:
        call("toy", REQUEST, SCHEMA, cfg)
    assert any("score" in e for e in bad.value.errors)
    resp.write_text("not json", encoding="utf-8")
    with pytest.raises(InvalidResponse):
        call("toy", REQUEST, SCHEMA, cfg)
    invalid = read_records(tmp_path / "llm" / "invalid.jsonl")
    assert len(invalid) == 2 and invalid[0]["error"] == "schema"
    assert not (tmp_path / "llm" / "responses.jsonl").exists()


def test_interactive_needs_run_dir():
    with pytest.raises(ValueError):
        call("toy", REQUEST, SCHEMA, LLMConfig(adapter="interactive"))


def _cassette(path: Path, response, model=DEFAULT_MODEL, task="toy") -> Path:
    rec = {
        "hash": request_hash(task, REQUEST, SCHEMA, model),
        "task": task,
        "model": model,
        "adapter": "interactive",
        "request": REQUEST,
        "response": response,
        "usage": None,
        "returned_model": None,
        "date": "2026-09-27",
    }
    path.write_text(json.dumps(rec, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def test_replay_hit_miss_and_invalid(tmp_path):
    cas = _cassette(tmp_path / "c.jsonl", GOOD)
    run = tmp_path / "run"
    assert (
        call("toy", REQUEST, SCHEMA, LLMConfig(adapter="replay", cassette=cas, run_dir=run)) == GOOD
    )
    assert len(read_records(run / "llm" / "responses.jsonl")) == 1  # replayed into the run's cache
    with pytest.raises(ReplayMiss):
        call(
            "toy", dict(REQUEST, system="other"), SCHEMA, LLMConfig(adapter="replay", cassette=cas)
        )
    with pytest.raises(ReplayMiss):  # the model is part of the key
        call(
            "toy",
            REQUEST,
            SCHEMA,
            LLMConfig(adapter="replay", cassette=cas, model="claude-sonnet-5"),
        )
    with pytest.raises(ReplayMiss):
        call("toy", REQUEST, SCHEMA, LLMConfig(adapter="replay"))
    bad = _cassette(tmp_path / "bad.jsonl", {"answer": ""})
    with pytest.raises(InvalidResponse):
        call("toy", REQUEST, SCHEMA, LLMConfig(adapter="replay", cassette=bad))


def test_api_schema_strips_constraint_keywords_only():
    schema = {
        "$schema": "x",
        "type": "object",
        "additionalProperties": False,
        "required": ["pattern", "minimum"],
        "properties": {
            "pattern": {"type": "string", "pattern": "^a", "maxLength": 3},
            "minimum": {
                "type": "array",
                "minItems": 2,
                "items": {"anyOf": [{"type": "number", "maximum": 1}, {"type": "null"}]},
            },
            "when": {"type": "string", "format": "date"},
            "odd": {"type": "string", "format": "linehead"},
        },
    }
    out = api_schema(schema)
    assert "$schema" not in out and set(out["properties"]) == {"pattern", "minimum", "when", "odd"}
    assert out["properties"]["pattern"] == {"type": "string"}
    assert out["properties"]["minimum"] == {
        "type": "array",
        "items": {"anyOf": [{"type": "number"}, {"type": "null"}]},
    }
    assert (
        out["properties"]["when"]["format"] == "date" and "format" not in out["properties"]["odd"]
    )
    assert out["required"] == ["pattern", "minimum"] and out["additionalProperties"] is False
    assert schema["properties"]["pattern"]["pattern"] == "^a"  # input untouched


def test_every_repository_schema_is_api_compatible():
    root = LLM_PKG.parents[2] / "schemas"
    for name in ("resolver-root-spans", "resolver-subdivide", "resolver-adjudicate", "gloss"):
        schema = json.loads((root / ("%s.schema.json" % name)).read_text(encoding="utf-8"))
        sent = api_schema(schema)

        def walk(s, where, name=name):
            if isinstance(s, dict):
                if s.get("type") == "object":
                    assert s.get("additionalProperties") is False, (name, where)
                for k, v in s.items():
                    assert k not in ("minimum", "maximum", "minItems", "pattern"), (name, where, k)
                    walk(v, where + "/" + k)
            elif isinstance(s, list):
                for i, v in enumerate(s):
                    walk(v, "%s/%d" % (where, i))

        walk(sent, name)


# -------------------------------------------------------------------------- claude, with a fake SDK


class _Stream:
    def __init__(self, message):
        self.message = message

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self.message


class _Messages:
    def __init__(self, owner, beta: bool):
        self.owner, self.beta = owner, beta

    def stream(self, **kwargs):
        self.owner.calls.append(("beta" if self.beta else "plain", kwargs))
        return _Stream(self.owner.message)

    def count_tokens(self, **kwargs):
        self.owner.counted.append(kwargs)
        return SimpleNamespace(input_tokens=self.owner.count)


class FakeClient:
    """The slice of anthropic.Anthropic the claude adapter uses."""

    def __init__(self, text, stop="end_turn", model=DEFAULT_MODEL, count=1200):
        usage = SimpleNamespace(
            input_tokens=1000,
            output_tokens=50,
            cache_creation_input_tokens=200,
            cache_read_input_tokens=300,
        )
        self.message = SimpleNamespace(
            content=[
                SimpleNamespace(type="thinking", thinking=""),
                SimpleNamespace(type="text", text=text),
            ],
            stop_reason=stop,
            model=model,
            usage=usage,
            stop_details=SimpleNamespace(category="cyber"),
        )
        self.count = count
        self.calls: list = []
        self.counted: list = []
        self.messages = _Messages(self, beta=False)
        self.beta = SimpleNamespace(messages=_Messages(self, beta=True))


def test_claude_adapter_params_ledger_and_cache(tmp_path):
    fake = FakeClient(json.dumps(GOOD, ensure_ascii=False))
    cfg = LLMConfig(adapter="claude", run_dir=tmp_path, client=fake, budget_usd=5.0)
    assert call("toy", REQUEST, SCHEMA, cfg) == GOOD
    [(kind, kw)] = fake.calls
    assert kind == "beta" and kw["betas"] == [FALLBACK_BETA] and kw["fallbacks"] == "default"
    assert kw["model"] == DEFAULT_MODEL and kw["max_tokens"] == 64000
    assert kw["system"] == [
        {"type": "text", "text": REQUEST["system"], "cache_control": {"type": "ephemeral"}}
    ]
    assert kw["messages"] == REQUEST["messages"]
    fmt = kw["output_config"]["format"]
    assert fmt["type"] == "json_schema" and kw["output_config"]["effort"] == "high"
    assert fmt["schema"] == api_schema(SCHEMA) and "minimum" not in json.dumps(fmt["schema"])
    assert "thinking" not in kw and "temperature" not in kw
    assert len(fake.counted) == 1  # count_tokens pre-flight under a budget
    ledger = json.loads((tmp_path / "llm" / "ledger.json").read_text(encoding="utf-8"))
    expected = cost_usd(
        DEFAULT_MODEL,
        {
            "input_tokens": 1000,
            "output_tokens": 50,
            "cache_creation_input_tokens": 200,
            "cache_read_input_tokens": 300,
        },
    )
    assert expected == pytest.approx((5 * (1000 + 1.25 * 200 + 0.1 * 300) + 25 * 50) / 1e6)
    assert ledger["totals"]["calls"] == 1 and ledger["totals"]["cost_usd"] == pytest.approx(
        expected
    )
    [rec] = read_records(tmp_path / "llm" / "responses.jsonl")
    assert rec["returned_model"] == DEFAULT_MODEL and rec["usage"]["output_tokens"] == 50
    # a re-run makes no repeated paid call
    assert call("toy", REQUEST, SCHEMA, cfg) == GOOD
    assert len(fake.calls) == 1


def test_claude_adapter_without_fallbacks_and_with_1h_ttl():
    fake = FakeClient(json.dumps(GOOD))
    cfg = LLMConfig(
        adapter="claude",
        client=fake,
        fallbacks=None,
        cache_ttl="1h",
        effort=None,
        model="claude-sonnet-5",
    )
    assert call("toy", REQUEST, SCHEMA, cfg) == GOOD
    [(kind, kw)] = fake.calls
    assert kind == "plain" and "betas" not in kw and "fallbacks" not in kw
    assert kw["system"][0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
    assert "effort" not in kw["output_config"] and kw["model"] == "claude-sonnet-5"
    assert fake.counted == []  # no budget, no pre-flight


def test_claude_adapter_budget_cap(tmp_path):
    fake = FakeClient(json.dumps(GOOD), count=2_000_000)  # $10 of input at $5 / MTok
    cfg = LLMConfig(adapter="claude", run_dir=tmp_path, client=fake, budget_usd=1.0)
    with pytest.raises(BudgetExceeded):
        call("toy", REQUEST, SCHEMA, cfg)
    assert fake.calls == []
    cheap = FakeClient(json.dumps(GOOD), count=10)
    cfg = LLMConfig(adapter="claude", client=cheap, budget_usd=0.0001)
    call("toy", REQUEST, SCHEMA, cfg)  # spends more than the cap (output is not pre-estimated)
    with pytest.raises(BudgetExceeded):
        call("toy", dict(REQUEST, system="another"), SCHEMA, cfg)
    with pytest.raises(BudgetExceeded):  # a model the ledger cannot price cannot run under a budget
        call(
            "toy",
            REQUEST,
            SCHEMA,
            LLMConfig(adapter="claude", client=cheap, budget_usd=1.0, model="claude-unknown-9"),
        )


def test_claude_adapter_refusal_truncation_and_non_json(tmp_path):
    cases = [
        (FakeClient("", stop="refusal"), Refusal),
        (FakeClient('{"answer": "二"', stop="max_tokens"), InvalidResponse),
        (FakeClient("I think the answer is 二."), InvalidResponse),
        (FakeClient(json.dumps({"answer": "二"})), InvalidResponse),
    ]  # schema: score missing
    for k, (fake, err) in enumerate(cases):
        run = tmp_path / str(k)
        with pytest.raises(err):
            call("toy", REQUEST, SCHEMA, LLMConfig(adapter="claude", run_dir=run, client=fake))
        assert len(read_records(run / "llm" / "invalid.jsonl")) == 1
        assert not (run / "llm" / "responses.jsonl").exists()
        ledger = json.loads((run / "llm" / "ledger.json").read_text(encoding="utf-8"))
        assert ledger["totals"]["calls"] == 1  # usage is recorded even for a rejected response


def test_ledger_prices_fallback_model():
    usage = {"input_tokens": 1_000_000, "output_tokens": 0}
    assert cost_usd("claude-opus-4-8", usage) == pytest.approx(5.0)
    assert cost_usd("claude-fable-5-1", usage) == pytest.approx(10.0)
    assert cost_usd("anthropic.claude-sonnet-5", usage) == pytest.approx(2.0)
    assert cost_usd("claude-unknown-9", usage) is None
    assert cost_usd(
        "claude-opus-5", {"cache_creation_input_tokens": 1_000_000}, "1h"
    ) == pytest.approx(10.0)


def test_llm_imports_anthropic_only_lazily():
    """No module of chinese_workflow.llm imports anthropic at module level."""
    for py in sorted(LLM_PKG.glob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in tree.body:
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            assert not any(n.split(".")[0] == "anthropic" for n in names), py.name

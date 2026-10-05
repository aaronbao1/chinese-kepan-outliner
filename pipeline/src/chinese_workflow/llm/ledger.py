"""chinese_workflow.llm.ledger — token and cost ledger of the claude adapter, and the budget cap.

Input : the usage of each Messages API response ({input_tokens, output_tokens,
        cache_creation_input_tokens, cache_read_input_tokens}), the model that answered, the cache
        TTL.
Output: <run_dir>/llm/ledger.json
          {schema: "llm-ledger/1", prices_as_of, calls: [{hash, task, model, returned_model, usage,
           cost_usd, date}], totals: {calls, input_tokens, output_tokens,
           cache_creation_input_tokens, cache_read_input_tokens, cost_usd}}
        (kept in memory on the LLMConfig when the config has no run_dir).

Prices: USD per million tokens, from the bundled claude-api skill's model table (cached 2026-06-24,
read 2026-09-27; plan Appendix E says "[API] facts, re-checked at build"). Cache writes cost 1.25x
the input price with the 5-minute TTL and 2x with the 1-hour TTL; cache reads 0.1x (0.025x on Claude
Fable 5.1). HYPOTHESIS until a live run's invoice confirms them; the ledger records the rates it
used.

Budget: check_budget() refuses a call when the money already spent plus the pre-flight input
estimate would exceed the cap. Output tokens are not estimated, so a run can overshoot by one call's
output.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

PRICES_AS_OF = "claude-api skill model table, cached 2026-06-24 (read 2026-09-27)"
# model id -> (input $/MTok, output $/MTok, cache-read multiplier)
PRICES = {
    "claude-fable-5-1": (10.0, 50.0, 0.025),
    "claude-fable-5": (10.0, 50.0, 0.1),
    "claude-opus-5-5": (4.0, 20.0, 0.05),  # cache reads $0.20 / MTok (skill)
    "claude-opus-5": (5.0, 25.0, 0.1),
    "claude-opus-4-8": (5.0, 25.0, 0.1),
    "claude-opus-4-7": (5.0, 25.0, 0.1),
    "claude-opus-4-6": (5.0, 25.0, 0.1),
    "claude-sonnet-5": (2.0, 10.0, 0.1),
    "claude-sonnet-4-6": (3.0, 15.0, 0.1),
    "claude-haiku-4-5": (1.0, 5.0, 0.1),
}
CACHE_WRITE = {"5m": 1.25, "1h": 2.0}
USAGE_KEYS = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)


def price(model: str | None):
    """(input, output, cache-read multiplier) for a model id, or None when unknown. A Bedrock-style
    'anthropic.' prefix is ignored."""
    if not model:
        return None
    return PRICES.get(model.removeprefix("anthropic."))


def cost_usd(model: str | None, usage: dict, cache_ttl: str = "5m") -> float | None:
    """Cost of one response in USD (None when the model is not in PRICES)."""
    p = price(model)
    if p is None:
        return None
    inp, out, read = p
    u = {k: int(usage.get(k) or 0) for k in USAGE_KEYS}
    dollars = (
        inp
        * (
            u["input_tokens"]
            + CACHE_WRITE[cache_ttl] * u["cache_creation_input_tokens"]
            + read * u["cache_read_input_tokens"]
        )
        + out * u["output_tokens"]
    ) / 1e6
    return round(dollars, 6)


def _empty() -> dict:
    return {
        "schema": "llm-ledger/1",
        "prices_as_of": PRICES_AS_OF,
        "calls": [],
        "totals": {"calls": 0, **{k: 0 for k in USAGE_KEYS}, "cost_usd": 0.0},
    }


class Ledger:
    """File-backed (path) or in-memory (path None) ledger."""

    def __init__(self, path=None):
        self.path = Path(path) if path is not None else None
        if self.path is not None and self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self.data = _empty()

    @classmethod
    def for_config(cls, config) -> Ledger:
        if config.llm_dir is not None:
            return cls(config.llm_dir / "ledger.json")
        if config._memory_ledger is None:
            config._memory_ledger = cls(None)
        return config._memory_ledger

    @property
    def spent_usd(self) -> float:
        return float(self.data["totals"]["cost_usd"])

    def check_budget(
        self, budget_usd: float | None, model: str, input_tokens_estimate: int
    ) -> None:
        """Raise BudgetExceeded when the spent amount plus this call's estimated input cost would
        exceed the budget, or when the model cannot be priced under a budget."""
        from .client import BudgetExceeded

        if budget_usd is None:
            return
        p = price(model)
        if p is None:
            raise BudgetExceeded("no price for model %r: cannot enforce budget_usd" % model)
        estimate = self.spent_usd + p[0] * max(int(input_tokens_estimate), 0) / 1e6
        if self.spent_usd >= budget_usd or estimate > budget_usd:
            raise BudgetExceeded(
                "budget $%.2f: spent $%.4f, this call's input alone ~$%.4f"
                % (budget_usd, self.spent_usd, estimate - self.spent_usd)
            )

    def add(
        self,
        *,
        key: str,
        task: str,
        model: str,
        returned_model: str | None,
        usage: dict,
        cache_ttl: str = "5m",
    ) -> float | None:
        cost = cost_usd(returned_model or model, usage, cache_ttl)
        if cost is None:  # a fallback to an unpriced model: price at the requested model's rates
            cost = cost_usd(model, usage, cache_ttl)
        row = {
            "hash": key,
            "task": task,
            "model": model,
            "returned_model": returned_model,
            "usage": {k: int(usage.get(k) or 0) for k in USAGE_KEYS},
            "cost_usd": cost,
            "date": _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds"),
        }
        self.data["calls"].append(row)
        tot = self.data["totals"]
        tot["calls"] += 1
        for k in USAGE_KEYS:
            tot[k] += row["usage"][k]
        tot["cost_usd"] = round(tot["cost_usd"] + (cost or 0.0), 6)
        self.save()
        return cost

    def save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )

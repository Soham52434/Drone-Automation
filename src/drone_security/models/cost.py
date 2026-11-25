from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPrice:
    """Paid-tier price per 1M tokens and the free tier's requests per day for one model."""

    input_per_m: float
    output_per_m: float
    free_requests_per_day: int | None
    paid_available: bool = True


# Google AI Studio pricing and rate-limit pages, read 2026-11-25
# (Standard tier, prices valid through 2026-12-31).
# The default LLM has no paid tier: it is free only, so its cost is always $0.
PRICES: dict[str, ModelPrice] = {
    "gemma-4-26b-a4b-it": ModelPrice(0.0, 0.0, 14_400, paid_available=False),
    "gemini-decision-1": ModelPrice(0.10, 0.0, 10_000),  # no output tokens: input only
}

JOB_LABELS = {
    "decision": "Alert classifier",
    "summaries": "Summaries & alert write-ups",
    "chat": "Chat",
    "analytics": "Advanced analytics",
}


def price_of(model: str) -> ModelPrice | None:
    name = model.removeprefix("models/")
    if name in PRICES:
        return PRICES[name]
    return next((price for key, price in PRICES.items() if name.startswith(key)), None)


def usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """What these tokens would cost at paid-tier prices (0 for free-only or unknown models)."""
    price = price_of(model)
    if price is None:
        return 0.0
    return input_tokens / 1e6 * price.input_per_m + output_tokens / 1e6 * price.output_per_m


@dataclass(frozen=True)
class UsageRecord:
    """One model request, measured from the provider's reply."""

    session_id: str
    job: str
    model: str
    input_tokens: int
    output_tokens: int
    ok: bool
    at_ms: int


@dataclass(frozen=True)
class CostLine:
    """Totals for one job or one model."""

    key: str
    label: str
    requests: int
    failed: int
    input_tokens: int
    output_tokens: int
    usd: float


@dataclass(frozen=True)
class ModelQuota:
    """Free-tier requests used today (project-wide, Pacific day) against the model's daily limit."""

    model: str
    requests_today: int
    free_per_day: int | None
    #: What the model does here ("Alert classifier", "Language model"), shown instead of its ID.
    label: str = ""


@dataclass(frozen=True)
class SessionCost:
    requests: int
    failed: int
    input_tokens: int
    output_tokens: int
    #: At paid-tier prices; the free tier bills nothing.
    usd: float
    by_job: tuple[CostLine, ...]
    by_model: tuple[CostLine, ...]
    quotas: tuple[ModelQuota, ...]


def build_session_cost(records: list[UsageRecord], requests_today: dict[str, int]) -> SessionCost:
    """Totals for one session, by job and by model, plus today's free-tier use of each model it called."""

    def lines(key_of, label_of) -> tuple[CostLine, ...]:
        groups: dict[str, list[UsageRecord]] = {}
        for r in records:
            groups.setdefault(key_of(r), []).append(r)
        out = [
            CostLine(
                key=key,
                label=label_of(key),
                requests=len(items),
                failed=sum(not r.ok for r in items),
                input_tokens=sum(r.input_tokens for r in items),
                output_tokens=sum(r.output_tokens for r in items),
                usd=sum(usd(r.model, r.input_tokens, r.output_tokens) for r in items),
            )
            for key, items in groups.items()
        ]
        return tuple(sorted(out, key=lambda line: -line.requests))

    models = sorted({r.model for r in records})
    jobs_of: dict[str, set[str]] = {}
    for r in records:
        jobs_of.setdefault(r.model, set()).add(r.job)

    def role(model: str) -> str:
        return "Alert classifier" if jobs_of.get(model) == {"decision"} else "Language model"

    return SessionCost(
        requests=len(records),
        failed=sum(not r.ok for r in records),
        input_tokens=sum(r.input_tokens for r in records),
        output_tokens=sum(r.output_tokens for r in records),
        usd=sum(usd(r.model, r.input_tokens, r.output_tokens) for r in records),
        by_job=lines(lambda r: r.job, lambda key: JOB_LABELS.get(key, key)),
        by_model=lines(lambda r: r.model, role),
        quotas=tuple(
            ModelQuota(m, requests_today.get(m, 0), price.free_requests_per_day if (price := price_of(m)) else None, role(m))
            for m in models
        ),
    )

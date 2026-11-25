import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from drone_security.agent.llm import answered_by
from drone_security.indexing.usage_ledger import UsageLedger
from drone_security.models.cost import UsageRecord

_SESSION: ContextVar[str] = ContextVar("usage_session", default="")


@contextmanager
def metered_session(session_id: str) -> Iterator[None]:
    """Attribute every model call inside this block to `session_id` (threads started here inherit it)."""
    token = _SESSION.set(session_id)
    try:
        yield
    finally:
        _SESSION.reset(token)


class UsageMeter:
    """Records each request's tokens, read from the provider's reply, into the usage ledger."""

    def __init__(self, ledger: UsageLedger | None, clock: Callable[[], float] = time.time) -> None:
        self._ledger = ledger
        self._clock = clock

    def record(self, job: str, model: str, response: object | None, ok: bool) -> None:
        if self._ledger is None:
            return
        tokens_in, tokens_out = _tokens(response)
        self._ledger.record(
            UsageRecord(_SESSION.get(), job, model, tokens_in, tokens_out, ok, int(self._clock() * 1000))
        )


def metered(inner: object | None, meter: UsageMeter | None, job: str, model: str) -> object | None:
    """`inner` wrapped for metering, or unchanged when there is no model or no meter."""
    if inner is None or meter is None:
        return inner
    return MeteredModel(inner, meter, job, model)


class MeteredModel:
    """Wraps a chat model or the alert classifier: same `invoke`, plus a ledger entry per call."""

    def __init__(self, inner: object, meter: UsageMeter, job: str, model: str) -> None:
        self._inner = inner
        self._meter = meter
        self._job = job
        self._model = model

    def invoke(self, payload: object) -> object:
        try:
            response = self._inner.invoke(payload)  # type: ignore[attr-defined]
        except Exception:
            self._meter.record(self._job, self._model, None, ok=False)  # a failed request still counts
            raise
        self._meter.record(self._job, answered_by(response, self._model), response, ok=True)
        return response


def _tokens(response: object | None) -> tuple[int, int]:
    if response is None:
        return 0, 0
    usage = getattr(response, "usage_metadata", None) or getattr(response, "usage", None)
    if usage is None:
        return 0, 0
    get = usage.get if isinstance(usage, dict) else (lambda key, default=None: getattr(usage, key, default))
    return int(get("input_tokens", 0) or 0), int(get("output_tokens", 0) or 0)

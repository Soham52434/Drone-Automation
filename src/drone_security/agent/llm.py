import json
import re
from typing import Protocol


class ChatModel(Protocol):
    """The slice of a LangChain chat model the graphs use."""

    def invoke(self, messages: list[object]) -> object: ...


def model_chain(models: str) -> tuple[str, ...]:
    """'a, b' → ('a', 'b'): the first model answers; the rest are tried in order if it fails."""
    return tuple(m.strip() for m in models.split(",") if m.strip())


def build_llm(api_key: str, models: str) -> ChatModel | None:
    """A hosted chat model (Google AI Studio API) through LangChain, with fallbacks, or None without a key.

    `models` is one id or a comma-separated chain. Earlier models fail over fast (no retry, 30 s)
    on errors such as 503 high demand or 429 quota; the last one gets the full patience.
    """
    key = api_key.strip()
    chain = model_chain(models)
    if not key or not chain:
        return None
    from langchain_google_genai import ChatGoogleGenerativeAI

    def client(model: str, last: bool) -> ChatGoogleGenerativeAI:
        return ChatGoogleGenerativeAI(
            model=model,
            api_key=key,
            temperature=0.2,
            retries=2 if last else 0,
            request_timeout=120 if last else 30,
        )

    primary = client(chain[0], last=len(chain) == 1)
    if len(chain) == 1:
        return primary
    return primary.with_fallbacks([client(m, last=i == len(chain) - 2) for i, m in enumerate(chain[1:])])


def answered_by(response: object, default: str = "") -> str:
    """The model that actually produced a reply (useful when a fallback answered)."""
    metadata = getattr(response, "response_metadata", None)
    if isinstance(metadata, dict):
        name = metadata.get("model_name") or metadata.get("model")
        if isinstance(name, str) and name:
            return name.removeprefix("models/")
    return default


def response_text(response: object) -> str:
    text = getattr(response, "text", None)
    if isinstance(text, str):
        return str(text)
    if callable(text):
        text = text()
    if isinstance(text, str):
        return text
    content = getattr(response, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)
    return str(content)


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def parse_json_object(text: str) -> dict[str, object]:
    """The first JSON object in a model reply, fenced or bare."""
    fenced = _FENCE.search(text)
    candidate = fenced.group(1) if fenced else text
    start, end = candidate.find("{"), candidate.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in the reply")
    value = json.loads(candidate[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("reply JSON is not an object")
    return value

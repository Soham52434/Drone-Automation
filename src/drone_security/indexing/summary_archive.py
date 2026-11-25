import json
import threading
from pathlib import Path

from drone_security.models.summaries import LlmSummary, SummaryKind

_ORDER = {SummaryKind.PERIOD: 0, SummaryKind.ALERT: 0, SummaryKind.FINAL: 1}


class SummaryArchive:
    """LLM summaries for one session as `<kind>_….summary.json` files beside the vision logs."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self._lock = threading.Lock()

    def write(self, summary: LlmSummary) -> Path:
        path = self._directory / summary.file_name
        with self._lock:
            self._directory.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(summary.to_dict(), indent=2, ensure_ascii=False))
        return path

    def list(self) -> list[LlmSummary]:
        """Oldest first; the final summary always sorts last."""
        if not self._directory.is_dir():
            return []
        summaries: list[LlmSummary] = []
        for path in self._directory.glob("*.summary.json"):
            try:
                summaries.append(LlmSummary.from_dict(json.loads(path.read_text())))
            except (ValueError, KeyError, TypeError):
                continue
        return sorted(summaries, key=lambda s: (_ORDER[s.kind], s.start_ms, s.created_ms))

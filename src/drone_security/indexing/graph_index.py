import json
import os
import signal
import threading
from pathlib import Path

import psutil
import redis

from drone_security.models.entities import EntitySighting
from drone_security.models.index import (
    ClassCount,
    DayLog,
    FrameQuery,
    FrameQueryResult,
    HourDigest,
    IndexedFrame,
    TimeBucket,
)
from drone_security.models.perception import SceneObservation
from drone_security.models.session import SessionKind
from drone_security.models.summaries import AlertNote
from drone_security.models.telemetry import TaggedReading

GRAPH_NAME = "drone_security"

# Every node is looked up by `key` (ObjectClass by `name`); index them so MERGE stays O(log n).
_INDEXES = (
    ("Session", "key"),
    ("Day", "key"),
    ("Hour", "key"),
    ("Minute", "key"),
    ("Observation", "key"),
    ("Alert", "key"),
    ("ObjectClass", "name"),
    ("Observation", "session_id"),
    ("Sighting", "session_id"),
)

_PATH = (
    "(s:Session {key: $sid})-[:HAS_DAY]->(d:Day)-[:HAS_HOUR]->(h:Hour)"
    "-[:HAS_MINUTE]->(m:Minute)-[:HAS_OBSERVATION]->(o:Observation)"
)

# One query writes the whole branch for a reading: tree nodes, the reading, and its classes.
_RECORD_OBSERVATION = """
MATCH (s:Session {key: $sid})
MERGE (d:Day {key: $day_key}) ON CREATE SET d.session_id = $sid, d.date = $date
MERGE (s)-[:HAS_DAY]->(d)
MERGE (h:Hour {key: $hour_key}) ON CREATE SET h.session_id = $sid, h.day = $date, h.label = $hour_label, h.start_ms = $hour_start
MERGE (d)-[:HAS_HOUR]->(h)
MERGE (m:Minute {key: $minute_key}) ON CREATE SET m.session_id = $sid, m.label = $minute_label, m.start_ms = $minute_start
MERGE (h)-[:HAS_MINUTE]->(m)
MERGE (o:Observation {key: $oid})
SET o.session_id = $sid, o.timestamp_ms = $ts, o.frame_index = $fi, o.label = $label, o.summary = $summary,
    o.confidence = $conf, o.event_detected = $event, o.scene = $scene, o.raw = $raw
MERGE (m)-[:HAS_OBSERVATION]->(o)
WITH o
UNWIND $classes AS hit
MERGE (c:ObjectClass {name: hit.name})
MERGE (o)-[e:SEEN]->(c)
SET e.score = hit.score, e.count = hit.count
"""

_RECORD_ALERT = """
MATCH (o:Observation {key: $oid})
MERGE (a:Alert {key: $key})
SET a.session_id = $sid, a.window_start_ms = $ws, a.detection_ms = $dm, a.rule = $rule, a.severity = $sev,
    a.summary = $summary, a.chunk_file = $chunk, a.seek_offset_sec = $seek
MERGE (o)-[:RAISED]->(a)
"""


def observation_id(session_id: str, observation: SceneObservation) -> str:
    return f"{session_id}:{observation.timestamp_ms}:{observation.frame_index}"


class GraphIndex:
    """Embedded property graph (FalkorDBLite, Cypher) of every vision reading.

    Session → Day → Hour → Minute → Observation, with Observation -SEEN-> ObjectClass and
    Observation -RAISED-> Alert. Traversal by time or by class is a single path match.
    FalkorDBLite runs FalkorDB in a child process over a Unix socket and persists to `path`.
    """

    def __init__(self, path: Path) -> None:
        from redislite.falkordb_client import FalkorDB

        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = FalkorDB(str(path))
        self._graph = self._db.select_graph(GRAPH_NAME)
        self._lock = threading.Lock()
        self._clocks: dict[str, tuple[SessionKind, int]] = {}
        existing = {(row[0], row[1]) for row in self._indexes()}
        for label, prop in _INDEXES:
            if (label, prop) not in existing:
                self._query(f"CREATE INDEX FOR (n:{label}) ON (n.{prop})")

    # ---- writes -----------------------------------------------------------------

    def register_session(self, session_id: str, kind: SessionKind, title: str, watch_brief: str, anchor_ms: int) -> None:
        self._query(
            "MERGE (s:Session {key: $sid}) SET s.session_id = $sid, s.kind = $kind, s.title = $title,"
            " s.watch_brief = $brief, s.anchor_ms = $anchor",
            {"sid": session_id, "kind": kind.value, "title": title, "brief": watch_brief, "anchor": anchor_ms},
        )
        self._clocks[session_id] = (kind, anchor_ms)

    def record_observation(self, session_id: str, observation: SceneObservation) -> str:
        kind, anchor = self._session_clock(session_id)
        bucket = TimeBucket.of(kind, observation.timestamp_ms, anchor)
        day_key = f"{session_id}|{bucket.day}"
        hour_key = f"{day_key}|{bucket.hour}"
        oid = observation_id(session_id, observation)
        self._query(
            _RECORD_OBSERVATION,
            {
                "sid": session_id,
                "day_key": day_key,
                "date": bucket.day,
                "hour_key": hour_key,
                "hour_label": bucket.hour_label,
                "hour_start": bucket.hour_start_ms,
                "minute_key": f"{hour_key}|{bucket.minute}",
                "minute_label": bucket.minute_label,
                "minute_start": bucket.minute_start_ms,
                "oid": oid,
                "ts": observation.timestamp_ms,
                "fi": observation.frame_index,
                "label": observation.label,
                "summary": observation.summary,
                "conf": float(observation.confidence),
                "event": observation.event_detected,
                "scene": observation.scene,
                "raw": json.dumps(observation.raw, ensure_ascii=False),
                "classes": [{"name": h.name, "score": float(h.score), "count": h.count} for h in observation.classes],
            },
        )
        return oid

    def record_alert(self, session_id: str, note: AlertNote, raised_by: str) -> None:
        """Hang the alert off the reading that raised it."""
        self._query(
            _RECORD_ALERT,
            {
                "oid": raised_by,
                "key": f"{session_id}|{note.key}",
                "sid": session_id,
                "ws": note.window_start_ms,
                "dm": note.detection_ms,
                "rule": note.rule,
                "sev": note.severity or "",
                "summary": note.summary,
                "chunk": note.chunk_file or "",
                "seek": note.seek_offset_sec,
            },
        )

    def record_sightings(self, session_id: str, sightings: tuple[EntitySighting, ...]) -> None:
        """Hang the LLM's entity descriptions off the reading they came from (advanced analytics)."""
        for i, s in enumerate(sightings):
            self._query(
                "MATCH (o:Observation {key: $oid})"
                " MERGE (e:Sighting {key: $key})"
                " SET e.session_id = $sid, e.timestamp_ms = $ts, e.class = $cls, e.description = $description,"
                " e.color = $color, e.make = $make, e.model = $model, e.kind = $kind, e.clothing = $clothing,"
                " e.signature = $signature"
                " MERGE (o)-[:DESCRIBED]->(e)",
                {
                    "oid": s.observation_id,
                    "key": f"{s.observation_id}|{i}",
                    "sid": session_id,
                    "ts": s.timestamp_ms,
                    "cls": s.class_name,
                    "description": s.description,
                    "color": s.color,
                    "make": s.make,
                    "model": s.model,
                    "kind": s.kind,
                    "clothing": s.clothing,
                    "signature": s.signature,
                },
            )

    def sightings(self, session_id: str) -> list[EntitySighting]:
        """Every entity the LLM described in this session, oldest first."""
        rows = self._rows(
            "MATCH (o:Observation)-[:DESCRIBED]->(e:Sighting {session_id: $sid})"
            " RETURN e.timestamp_ms, e.class, e.description, e.color, e.make, e.model, e.kind, e.clothing, o.key"
            " ORDER BY e.timestamp_ms",
            {"sid": session_id},
        )
        return [
            EntitySighting(int(r[0]), r[1] or "", r[2] or "", r[3] or "", r[4] or "", r[5] or "", r[6] or "", r[7] or "", r[8] or "")
            for r in rows
        ]

    def delete_session(self, session_id: str) -> None:
        self._query("MATCH (n) WHERE n.session_id = $sid DETACH DELETE n", {"sid": session_id})
        self._clocks.pop(session_id, None)

    # ---- reads ------------------------------------------------------------------

    def tagged_readings(self, session_id: str) -> list[TaggedReading]:
        """Every reading with its class tags (and any alert it raised), oldest first."""
        rows = self._rows(
            "MATCH (o:Observation {session_id: $sid})"
            " OPTIONAL MATCH (o)-[e:SEEN]->(c:ObjectClass)"
            " OPTIONAL MATCH (o)-[:RAISED]->(a:Alert)"
            " OPTIONAL MATCH (o)-[:DESCRIBED]->(x:Sighting)"
            " RETURN o.timestamp_ms, o.scene, o.summary, o.label, collect(DISTINCT [c.name, e.score]), a.rule,"
            " collect(DISTINCT x.description)"
            " ORDER BY o.timestamp_ms",
            {"sid": session_id},
        )
        readings = []
        for ts, scene, summary, label, hits, rule, described in rows:
            classes = sorted(
                ((str(name), float(score or 0)) for name, score in (hits or []) if name),
                key=lambda hit: -hit[1],
            )
            readings.append(
                TaggedReading(
                    int(ts), tuple(classes), scene or "", summary or "", label or "", rule or None,
                    tuple(d for d in (described or []) if d),
                )
            )
        return readings

    def classes(self, session_id: str) -> list[ClassCount]:
        """Every class seen in the session, most frequent first."""
        rows = self._rows(
            f"MATCH {_PATH}-[e:SEEN]->(c:ObjectClass)"
            " OPTIONAL MATCH (o)-[:RAISED]->(a:Alert)"
            " RETURN c.name, count(DISTINCT o), max(e.score), count(DISTINCT a)",
            {"sid": session_id},
        )
        counts = [ClassCount(name, int(frames), float(score or 0), int(alerts)) for name, frames, score, alerts in rows]
        return sorted(counts, key=lambda c: (-c.frames, c.name))

    def find_frames(self, session_id: str, query: FrameQuery) -> FrameQueryResult:
        where, params = ["true"], {"sid": session_id}
        if query.start_ms is not None:
            where.append("o.timestamp_ms >= $from_ms")
            params["from_ms"] = query.start_ms
        if query.end_ms is not None:
            where.append("o.timestamp_ms <= $to_ms")
            params["to_ms"] = query.end_ms
        match = f"MATCH {_PATH} WHERE {' AND '.join(where)}"
        if query.classes:
            match += " MATCH (o)-[:SEEN]->(q:ObjectClass) WHERE q.name IN $classes"
            params["classes"] = list(query.classes)
        if query.alerts_only:
            match += " MATCH (o)-[:RAISED]->(:Alert)"
        rows = self._rows(
            f"{match} WITH DISTINCT d, h, m, o"
            " OPTIONAL MATCH (o)-[:SEEN]->(c:ObjectClass)"
            " OPTIONAL MATCH (o)-[:RAISED]->(a:Alert)"
            " RETURN o.key, o.timestamp_ms, d.date, h.label, m.label, o.summary, o.label, o.confidence,"
            " collect(DISTINCT c.name), o.scene, a.rule, a.severity, a.chunk_file,"
            " a.seek_offset_sec ORDER BY o.timestamp_ms",
            params,
        )
        frames = tuple(
            IndexedFrame(
                observation_id=r[0],
                timestamp_ms=int(r[1]),
                day=r[2],
                hour_label=r[3],
                minute_label=r[4],
                summary=r[5] or "",
                label=r[6] or "",
                confidence=float(r[7] or 0),
                classes=tuple(sorted(name for name in (r[8] or []) if name)),
                scene=r[9] or "",
                alert_rule=r[10],
                alert_severity=r[11] or None,
                chunk_file=r[12] or None,
                seek_offset_sec=r[13],
            )
            for r in rows
        )
        return FrameQueryResult(query=query, total=len(frames), frames=frames[: query.limit])

    def day_log(self, session_id: str) -> DayLog:
        """Day → hour digests: readings, alerts, and classes per hour."""
        rows = self._rows(
            f"MATCH {_PATH} OPTIONAL MATCH (o)-[:RAISED]->(a:Alert)"
            " RETURN d.date, h.label, h.start_ms, count(DISTINCT o), count(DISTINCT a),"
            " min(o.timestamp_ms), max(o.timestamp_ms)",
            {"sid": session_id},
        )
        class_rows = self._rows(
            f"MATCH {_PATH}-[e:SEEN]->(c:ObjectClass) RETURN d.date, h.label, c.name, count(DISTINCT o), max(e.score)",
            {"sid": session_id},
        )
        alert_rows = self._rows(
            f"MATCH {_PATH}-[:SEEN]->(c:ObjectClass) MATCH (o)-[:RAISED]->(a:Alert)"
            " RETURN d.date, h.label, c.name, count(DISTINCT a)",
            {"sid": session_id},
        )
        alerts_by = {(day, hour, name): int(n) for day, hour, name, n in alert_rows}
        classes_by: dict[tuple[str, str], list[ClassCount]] = {}
        for day, hour, name, frames, score in class_rows:
            classes_by.setdefault((day, hour), []).append(
                ClassCount(name, int(frames), float(score or 0), alerts_by.get((day, hour, name), 0))
            )
        days: dict[str, list[HourDigest]] = {}
        for day, hour, start, frames, alerts, first, last in rows:
            classes = sorted(classes_by.get((day, hour), []), key=lambda c: (-c.frames, c.name))
            days.setdefault(day, []).append(
                HourDigest(day, hour, int(start), int(frames), int(alerts), tuple(classes), first, last)
            )
        return DayLog(session_id, {day: tuple(sorted(hours, key=lambda h: h.start_ms)) for day, hours in days.items()})

    def close(self) -> None:
        """Persist, then stop the embedded server.

        FalkorDB's own SHUTDOWN spends ~4 s unloading the module. The data is already on disk after
        SAVE, so the server process is stopped directly and redislite only tidies up its files.
        """
        with self._lock:
            client = self._db.client
            pid = getattr(client, "pid", 0)
            try:
                client.execute_command("SAVE")
                if pid:
                    os.kill(pid, signal.SIGKILL)
                    psutil.Process(pid).wait(timeout=2)
            except (OSError, psutil.Error, redis.RedisError):
                pass  # fall back to redislite's own shutdown below
            self._db.close()

    # ---- helpers ----------------------------------------------------------------

    def _session_clock(self, session_id: str) -> tuple[SessionKind, int]:
        clock = self._clocks.get(session_id)
        if clock is not None:
            return clock
        rows = self._rows("MATCH (s:Session {key: $sid}) RETURN s.kind, s.anchor_ms", {"sid": session_id})
        if not rows:
            raise KeyError(f"session {session_id} is not registered in the graph index")
        clock = (SessionKind(rows[0][0]), int(rows[0][1] or 0))
        self._clocks[session_id] = clock
        return clock

    def _indexes(self) -> list[tuple[str, str]]:
        try:
            result = self._graph.query("CALL db.indexes() YIELD label, properties RETURN label, properties")
        except Exception:
            return []
        return [(label, prop) for label, props in result.result_set for prop in props]

    def _query(self, statement: str, params: dict[str, object] | None = None):
        with self._lock:
            return self._graph.query(statement, params)

    def _rows(self, statement: str, params: dict[str, object]) -> list[list]:
        return self._query(statement, params).result_set

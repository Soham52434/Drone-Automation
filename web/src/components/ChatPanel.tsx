import {
  Bot,
  CircleAlert,
  Clock3,
  CornerDownLeft,
  Film,
  ListChecks,
  LoaderCircle,
  MapPin,
  MessagesSquare,
  Search,
  Sparkles,
  X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { api } from "../api/client";
import type { ChatClip, ChatTurn, ClassCount, IndexedFrame, Session } from "../api/types";
import { ruleLabel } from "../lib/analysisFeed";
import { groupFramesByHour } from "../lib/chat";
import { formatTimeline } from "../lib/format";
import { ClassChips, classIcon, keyClassesFirst } from "./ClassChips";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  turn?: ChatTurn;
  pending?: boolean;
  error?: boolean;
  /** Classes the human confirmed for a paused query. */
  confirmed?: string[];
}

interface ChatPanelProps {
  session: Session;
  onClose: () => void;
}

const SUGGESTIONS = ["Show all alerts", "Summarize each hour", "What happened today?"];

/** Ask about the day log: find frames by class and time, or get hourly / daily summaries. */
export function ChatPanel({ session, onClose }: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [classes, setClasses] = useState<ClassCount[]>([]);
  const [busy, setBusy] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    let alive = true;
    api
      .indexClasses(session.id)
      .then((list) => alive && setClasses(list))
      .catch(() => undefined);
    input.current?.focus();
    return () => {
      alive = false;
    };
  }, [session.id, messages.length]);

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const ask = async (question: string) => {
    const text = question.trim();
    if (!text || busy) return;
    const id = crypto.randomUUID();
    setDraft("");
    setBusy(true);
    setMessages((m) => [...m, { id: `${id}-q`, role: "user", text }, { id, role: "assistant", text: "", pending: true }]);
    try {
      const turn = await api.askChat(session.id, text);
      setMessages((m) => m.map((msg) => (msg.id === id ? { ...msg, pending: false, text: turn.answer, turn } : msg)));
    } catch (error) {
      const message = error instanceof Error ? error.message : "The chat request failed.";
      setMessages((m) => m.map((msg) => (msg.id === id ? { ...msg, pending: false, error: true, text: message } : msg)));
    } finally {
      setBusy(false);
    }
  };

  const verify = async (messageId: string, threadId: string, chosen: string[]) => {
    setBusy(true);
    setMessages((m) => m.map((msg) => (msg.id === messageId ? { ...msg, pending: true, confirmed: chosen } : msg)));
    try {
      const turn = await api.verifyChat(session.id, threadId, chosen);
      setMessages((m) => m.map((msg) => (msg.id === messageId ? { ...msg, pending: false, text: turn.answer, turn } : msg)));
    } catch (error) {
      const message = error instanceof Error ? error.message : "Could not run the search.";
      setMessages((m) => m.map((msg) => (msg.id === messageId ? { ...msg, pending: false, error: true, text: message } : msg)));
    } finally {
      setBusy(false);
    }
  };

  return (
    <aside className="chat-panel" aria-label="Ask about this session">
      <header className="chat-head">
        <span className="chat-mark">
          <MessagesSquare size={17} />
        </span>
        <div>
          <strong>Ask the day log</strong>
          <span>
            {session.llm.enabled ? (
              <>
                <Sparkles size={11} /> The LLM plans the search
              </>
            ) : (
              "Local search · LLM is off for this session"
            )}
          </span>
        </div>
        <button type="button" className="icon-btn ghost" aria-label="Close chat" onClick={onClose}>
          <X size={18} />
        </button>
      </header>

      <div className="chat-scroll" ref={scroller}>
        {messages.length === 0 ? (
          <div className="chat-empty">
            <Bot size={26} />
            <p>Find moments by class and time, or ask for an hourly or daily summary.</p>
            {classes.length > 0 ? (
              <>
                <h5>Classes in this session</h5>
                <div className="chat-classes">
                  {keyClassesFirst(classes).map((c) => {
                    const Icon = classIcon(c.name);
                    return (
                      <button key={c.name} type="button" className="class-pick" onClick={() => ask(`Show all ${c.name} events`)}>
                        <Icon size={13} /> {c.name}
                        <em>{c.frames}</em>
                        {c.alerts ? <span className="alert-count">{c.alerts}</span> : null}
                      </button>
                    );
                  })}
                </div>
              </>
            ) : (
              <p className="muted small">Nothing indexed yet. Classes appear as the vision model reads frames.</p>
            )}
            <h5>Try</h5>
            <div className="chat-suggestions">
              {SUGGESTIONS.map((s) => (
                <button key={s} type="button" className="suggestion" onClick={() => ask(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : null}

        {messages.map((message) =>
          message.role === "user" ? (
            <div key={message.id} className="bubble user">
              {message.text}
            </div>
          ) : (
            <AssistantMessage key={message.id} message={message} session={session} busy={busy} onVerify={verify} />
          ),
        )}
      </div>

      <form
        className="chat-input"
        onSubmit={(event) => {
          event.preventDefault();
          void ask(draft);
        }}
      >
        <textarea
          ref={input}
          rows={1}
          value={draft}
          maxLength={500}
          placeholder="e.g. vehicles between 14:00 and 15:00"
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void ask(draft);
            }
          }}
        />
        <button type="submit" className="icon-btn send" disabled={busy || !draft.trim()} aria-label="Send">
          {busy ? <LoaderCircle size={17} className="spin" /> : <CornerDownLeft size={17} />}
        </button>
      </form>
    </aside>
  );
}

function AssistantMessage({
  message,
  session,
  busy,
  onVerify,
}: {
  message: ChatMessage;
  session: Session;
  busy: boolean;
  onVerify: (messageId: string, threadId: string, classes: string[]) => void;
}) {
  const turn = message.turn;
  if (message.pending && !turn) {
    return (
      <div className="bubble bot pending">
        <LoaderCircle size={15} className="spin" /> Searching the day log…
      </div>
    );
  }
  if (message.error) {
    return (
      <div className="bubble bot error">
        <CircleAlert size={15} /> {message.text}
      </div>
    );
  }
  if (!turn) return null;
  if (turn.status === "needs_verification" && turn.verification) {
    return (
      <>
        {turn.notice ? (
          <p className="chat-notice">
            <CircleAlert size={13} /> {turn.notice}
          </p>
        ) : null}
        <VerifyCard
        turn={turn}
        busy={busy || Boolean(message.pending)}
          onConfirm={(classes) => onVerify(message.id, turn.thread_id, classes)}
        />
      </>
    );
  }
  return (
    <div className="bubble bot">
      {message.confirmed ? (
        <p className="confirmed">
          <ListChecks size={13} /> You confirmed: {message.confirmed.length ? message.confirmed.join(", ") : "all classes"}
        </p>
      ) : null}
      <PlanLine turn={turn} session={session} />
      {turn.notice ? (
        <p className="chat-notice">
          <CircleAlert size={13} /> {turn.notice}
        </p>
      ) : null}
      <p className="answer">{turn.answer}</p>
      {turn.intent === "sightings" ? <EntityCards turn={turn} session={session} /> : null}
      {turn.intent === "frames" || turn.intent === "sightings" ? (
        <FrameResults turn={turn} session={session} />
      ) : (
        <HourTable turn={turn} session={session} />
      )}
    </div>
  );
}

function EntityCards({ turn, session }: { turn: ChatTurn; session: Session }) {
  if (turn.entities.length === 0) return null;
  return (
    <div className="entity-cards">
      {turn.entities.map((entity) => {
        const Icon = classIcon(entity.class_name);
        return (
          <div key={entity.signature} className="entity-card">
            <div className="entity-head">
              <Icon size={14} />
              <strong>{entity.description}</strong>
              <span className="entity-count">
                {entity.visits.length} visit{entity.visits.length === 1 ? "" : "s"}
              </span>
            </div>
            <ol className="entity-visits">
              {entity.visits.map((v) => (
                <li key={v.start_ms} className="mono">
                  {formatTimeline(session.kind, v.start_ms)}
                  {v.end_ms > v.start_ms ? `–${formatTimeline(session.kind, v.end_ms)}` : ""}
                  <em>
                    {v.sightings} sighting{v.sightings === 1 ? "" : "s"}
                  </em>
                </li>
              ))}
            </ol>
          </div>
        );
      })}
    </div>
  );
}

function PlanLine({ turn, session }: { turn: ChatTurn; session: Session }) {
  const plan = turn.plan;
  if (turn.intent === "sightings") {
    return (
      <p className="plan-line">
        <span className={`planner ${turn.llm_used ? "llm" : "local"}`}>{turn.llm_used ? "LLM" : "Local"}</span>
        Advanced analytics · LLM descriptions
      </p>
    );
  }
  if (!plan) {
    return (
      <p className="plan-line">
        <span className={`planner ${turn.llm_used ? "llm" : "local"}`}>{turn.llm_used ? "LLM" : "Local"}</span>
        Hourly digest
      </p>
    );
  }
  const span =
    plan.start_ms !== null || plan.end_ms !== null
      ? `${plan.start_ms !== null ? formatTimeline(session.kind, plan.start_ms) : "start"} – ${plan.end_ms !== null ? formatTimeline(session.kind, plan.end_ms) : "end"}`
      : "whole session";
  return (
    <div className="plan-line">
      <span className={`planner ${plan.planner === "llm" ? "llm" : "local"}`}>{plan.planner === "llm" ? "LLM" : "Local"}</span>
      <Search size={12} />
      {plan.classes.length ? <ClassChips classes={plan.classes} showScore={false} /> : <span>{plan.alerts_only ? "alerts" : "all classes"}</span>}
      <span className="plan-span">
        <Clock3 size={12} /> {span}
      </span>
      {plan.alerts_only && plan.classes.length ? <span className="pill sev critical">alerts only</span> : null}
    </div>
  );
}

function VerifyCard({ turn, busy, onConfirm }: { turn: ChatTurn; busy: boolean; onConfirm: (classes: string[]) => void }) {
  const verification = turn.verification!;
  const [chosen, setChosen] = useState<Set<string>>(() => new Set(verification.proposed));
  const toggle = (name: string) =>
    setChosen((current) => {
      const next = new Set(current);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  return (
    <div className="bubble bot verify">
      <p className="verify-title">
        <ListChecks size={15} /> Confirm the classes to search
      </p>
      {verification.unmatched_terms.length ? (
        <p className="verify-note">
          No exact class for{" "}
          {verification.unmatched_terms.map((term) => (
            <q key={term}>{term}</q>
          ))}
          . Pick what you meant:
        </p>
      ) : (
        <p className="verify-note">{verification.interpretation || "The question was broad. Pick the classes you meant:"}</p>
      )}
      {verification.available.length === 0 ? (
        <p className="muted small">No classes have been indexed yet.</p>
      ) : (
        <div className="verify-grid">
          {keyClassesFirst(verification.available).map((c) => {
            const Icon = classIcon(c.name);
            const on = chosen.has(c.name);
            return (
              <button
                key={c.name}
                type="button"
                className={`class-pick${on ? " on" : ""}`}
                aria-pressed={on}
                onClick={() => toggle(c.name)}
                disabled={busy}
              >
                <Icon size={13} /> {c.name}
                <em>{c.frames}</em>
                {c.alerts ? <span className="alert-count">{c.alerts}</span> : null}
              </button>
            );
          })}
        </div>
      )}
      <div className="verify-actions">
        <button type="button" className="btn btn-ghost sm" disabled={busy} onClick={() => onConfirm([])}>
          Search all
        </button>
        <button type="button" className="btn btn-primary sm" disabled={busy || chosen.size === 0} onClick={() => onConfirm([...chosen])}>
          {busy ? <LoaderCircle size={14} className="spin" /> : <Search size={14} />} Search {chosen.size || ""} class
          {chosen.size === 1 ? "" : "es"}
        </button>
      </div>
    </div>
  );
}

function FrameResults({ turn, session }: { turn: ChatTurn; session: Session }) {
  const [clip, setClip] = useState<ChatClip | null>(turn.clips[0] ?? null);
  const groups = useMemo(() => groupFramesByHour(turn.frames), [turn.frames]);
  if (turn.total === 0) return null;
  const playFrame = (frame: IndexedFrame) => {
    if (frame.alert?.video_url) {
      setClip({ source: "alert", url: frame.alert.video_url, start_sec: frame.alert.seek_offset_sec ?? 0, label: "Alert clip" });
    } else if (session.kind === "upload" && session.source_url) {
      setClip({ source: "video", url: session.source_url, start_sec: Math.max(0, frame.timestamp_ms / 1000 - 2), label: formatTimeline(session.kind, frame.timestamp_ms) });
    }
  };
  return (
    <div className="results">
      {clip ? (
        <div className="result-video">
          <video key={`${clip.url}-${clip.start_sec}`} src={`${clip.url}#t=${clip.start_sec.toFixed(2)}`} controls autoPlay muted playsInline />
          <div className="clip-pills">
            {turn.clips.map((c) => (
              <button
                key={`${c.url}-${c.start_sec}`}
                type="button"
                className={`clip-pill${c === clip ? " on" : ""} ${c.source}`}
                onClick={() => setClip(c)}
              >
                <Film size={11} /> {c.label}
              </button>
            ))}
          </div>
        </div>
      ) : session.kind === "live" ? (
        <p className="muted small">Live video is not recorded; only alert clips can be replayed.</p>
      ) : null}

      <div className="timeline">
        {groups.map((group) => (
          <section key={group.key}>
            <h6>
              {group.day} · {group.hour}
              <span>{group.frames.length} readings</span>
            </h6>
            {group.minutes.map((minute) => (
              <div key={minute.label} className="minute">
                <span className="minute-label mono">{minute.label}</span>
                <div className="minute-frames">
                  {minute.frames.map((frame) => (
                    <button
                      key={frame.observation_id}
                      type="button"
                      className={`frame-row${frame.alert ? " alert" : ""}`}
                      onClick={() => playFrame(frame)}
                    >
                      <span className="frame-top">
                        <time className="mono">{formatTimeline(session.kind, frame.timestamp_ms)}</time>
                        {frame.scene ? (
                          <span className="frame-zone">
                            <MapPin size={11} /> {frame.scene}
                          </span>
                        ) : null}
                        {frame.alert ? <span className={`pill sev ${frame.alert.severity || "warn"}`}>{ruleLabel(frame.alert.rule)}</span> : null}
                      </span>
                      <span className="frame-summary">{frame.summary}</span>
                      <ClassChips classes={frame.classes} showScore={false} max={5} />
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </section>
        ))}
        {turn.total > turn.frames.length ? (
          <p className="muted small">Showing the first {turn.frames.length} of {turn.total}. Narrow the time or classes to see the rest.</p>
        ) : null}
      </div>
    </div>
  );
}

function HourTable({ turn, session }: { turn: ChatTurn; session: Session }) {
  if (turn.hours.length === 0) return null;
  return (
    <table className="hour-table">
      <thead>
        <tr>
          <th>Hour</th>
          <th>Readings</th>
          <th>Alerts</th>
          <th>Top classes</th>
        </tr>
      </thead>
      <tbody>
        {turn.hours.map((hour) => (
          <tr key={`${hour.day}-${hour.hour}`}>
            <td className="mono">
              {session.kind === "live" ? `${hour.day.slice(5)} ` : ""}
              {hour.hour}
            </td>
            <td>{hour.frames}</td>
            <td className={hour.alerts ? "hot" : ""}>{hour.alerts}</td>
            <td>
              <ClassChips classes={keyClassesFirst(hour.classes).map((c) => c.name)} showScore={false} max={3} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

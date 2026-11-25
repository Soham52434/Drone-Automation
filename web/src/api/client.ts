import { type SessionSetup, llmPayload } from "../lib/sessionSetup";
import type {
  ChatTurn,
  Chunk,
  ClassCount,
  Session,
  SessionDescriptionMessage,
  SessionDetail,
  Summary,
  SessionCost,
  SessionTelemetry,
} from "./types";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type Fetch = typeof fetch;

export class ApiClient {
  constructor(
    private readonly fetchImpl: Fetch = (...args) => fetch(...args),
    private readonly baseUrl = "",
  ) {}

  getSession(id: string): Promise<SessionDetail> {
    return this.request(`/api/sessions/${id}`);
  }

  createLiveSession(input: { title?: string; setup?: SessionSetup } = {}): Promise<Session> {
    const brief = input.setup?.watchBrief.trim();
    return this.request("/api/sessions/live", {
      method: "POST",
      json: {
        title: input.title ?? null,
        watch_brief: brief || null,
        llm: input.setup ? llmPayload(input.setup.llm) : null,
      },
    });
  }

  uploadVideo(file: File, setup?: SessionSetup): Promise<Session> {
    const body = new FormData();
    body.append("file", file);
    const brief = setup?.watchBrief.trim();
    if (brief) body.append("watch_brief", brief);
    if (setup) {
      const llm = llmPayload(setup.llm);
      body.append("llm_enabled", String(llm.enabled));
      body.append("summary_interval_minutes", String(llm.summary_interval_minutes));
      body.append("detailed_alerts", String(llm.detailed_alerts));
      body.append("advanced_analytics", String(llm.advanced_analytics));
    }
    return this.request("/api/sessions/upload", { method: "POST", body });
  }

  cost(id: string): Promise<SessionCost> {
    return this.request(`/api/sessions/${id}/cost`);
  }

  telemetry(id: string): Promise<SessionTelemetry> {
    return this.request(`/api/sessions/${id}/telemetry`);
  }

  indexClasses(id: string): Promise<ClassCount[]> {
    return this.request(`/api/sessions/${id}/index/classes`);
  }

  askChat(id: string, question: string): Promise<ChatTurn> {
    return this.request(`/api/sessions/${id}/chat`, { method: "POST", json: { question } });
  }

  verifyChat(id: string, threadId: string, classes: string[]): Promise<ChatTurn> {
    return this.request(`/api/sessions/${id}/chat/${threadId}/verify`, { method: "POST", json: { classes } });
  }

  listSummaries(id: string): Promise<Summary[]> {
    return this.request(`/api/sessions/${id}/summaries`);
  }

  deleteSession(id: string): Promise<void> {
    return this.request(`/api/sessions/${id}`, { method: "DELETE" });
  }

  sendOffer(id: string, offer: SessionDescriptionMessage): Promise<SessionDescriptionMessage> {
    return this.request(`/api/sessions/${id}/webrtc/offer`, { method: "POST", json: offer });
  }

  stopLive(id: string): Promise<Session> {
    return this.request(`/api/sessions/${id}/live/stop`, { method: "POST" });
  }

  saveClip(id: string, detectionMs?: number): Promise<Chunk> {
    return this.request(`/api/sessions/${id}/chunks`, {
      method: "POST",
      json: { detection_ms: detectionMs ?? null },
    });
  }

  private async request<T>(
    path: string,
    options: { method?: string; json?: unknown; body?: BodyInit } = {},
  ): Promise<T> {
    const init: RequestInit = { method: options.method ?? "GET" };
    if (options.json !== undefined) {
      init.headers = { "Content-Type": "application/json" };
      init.body = JSON.stringify(options.json);
    } else if (options.body !== undefined) {
      init.body = options.body;
    }
    const response = await this.fetchImpl(`${this.baseUrl}${path}`, init);
    if (!response.ok) {
      throw new ApiError(response.status, await errorDetail(response));
    }
    if (response.status === 204) {
      return undefined as T;
    }
    return (await response.json()) as T;
  }
}

async function errorDetail(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") return body.detail;
    if (Array.isArray(body?.detail)) return body.detail.map((d: { msg?: string }) => d.msg).join("; ");
  } catch {
    // fall through to the status text
  }
  return response.statusText || `Request failed (${response.status})`;
}

export const api = new ApiClient();

import { describe, expect, it, vi } from "vitest";

import { ApiClient, ApiError } from "./client";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("ApiClient", () => {
  it("posts JSON and parses the response", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(201, { id: "abc", kind: "live" }));
    const client = new ApiClient(fetchMock);

    const session = await client.createLiveSession({
      title: "Gate",
      setup: { watchBrief: " Only boats. ", llm: { enabled: true, summaryIntervalMinutes: 15, detailedAlerts: true, advancedAnalytics: false } },
    });

    expect(session).toEqual({ id: "abc", kind: "live" });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/sessions/live");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({
      title: "Gate",
      watch_brief: "Only boats.",
      llm: { enabled: true, summary_interval_minutes: 15, detailed_alerts: true, advanced_analytics: false },
    });
  });

  it("sends the watch brief and LLM settings with an uploaded video", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(201, { id: "up" }));
    const file = new Blob(["video"], { type: "video/mp4" }) as File;
    await new ApiClient(fetchMock).uploadVideo(file, {
      watchBrief: "Only boats.",
      llm: { enabled: false, summaryIntervalMinutes: 5, detailedAlerts: true, advancedAnalytics: true },
    });
    const body = fetchMock.mock.calls[0][1].body as FormData;
    expect(body.get("watch_brief")).toBe("Only boats.");
    expect(body.get("file")).toBeInstanceOf(Blob);
    expect(body.get("llm_enabled")).toBe("false");
    expect(body.get("summary_interval_minutes")).toBe("5");
    expect(body.get("detailed_alerts")).toBe("false");
    expect(body.get("advanced_analytics")).toBe("false");
  });

  it("asks the chat and resumes a paused query with the confirmed classes", async () => {
    const fetchMock = vi.fn().mockImplementation(async () => jsonResponse(200, { thread_id: "t1", status: "answered" }));
    const client = new ApiClient(fetchMock);
    await client.askChat("s1", "show trucks");
    await client.verifyChat("s1", "t1", ["vehicle"]);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/sessions/s1/chat");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ question: "show trucks" });
    expect(fetchMock.mock.calls[1][0]).toBe("/api/sessions/s1/chat/t1/verify");
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ classes: ["vehicle"] });
  });

  it("fetches a session's summaries", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, []));
    await new ApiClient(fetchMock).listSummaries("s1");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/sessions/s1/summaries");
  });

  it("sends the video position when saving an upload clip", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(201, { chunk_file: "chunk_1.mp4" }));
    await new ApiClient(fetchMock).saveClip("s1", 9000);
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ detection_ms: 9000 });
  });

  it("returns undefined for 204 responses", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    await expect(new ApiClient(fetchMock).deleteSession("s1")).resolves.toBeUndefined();
  });

  it("raises ApiError with the server detail", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(409, { detail: "live feed is not running" }));
    const error = await new ApiClient(fetchMock).saveClip("s1").catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(409);
    expect(error.message).toBe("live feed is not running");
  });

  it("joins validation error messages", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(422, { detail: [{ msg: "bad type" }, { msg: "bad sdp" }] }));
    const error = await new ApiClient(fetchMock).sendOffer("s1", { sdp: "", type: "answer" }).catch((e) => e);
    expect(error.message).toBe("bad type; bad sdp");
  });
});

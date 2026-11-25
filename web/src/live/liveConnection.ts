import type { ApiClient } from "../api/client";

export type LiveState = "connecting" | "connected" | "disconnected" | "failed" | "closed";

export const CAMERA_CONSTRAINTS: MediaStreamConstraints = {
  audio: false,
  video: { width: { ideal: 1280 }, height: { ideal: 720 }, frameRate: { ideal: 30 } },
};

interface IceGatheringTarget {
  iceGatheringState: RTCIceGatheringState;
  addEventListener(type: "icegatheringstatechange", listener: () => void): void;
  removeEventListener(type: "icegatheringstatechange", listener: () => void): void;
}

export function waitForIceGathering(pc: IceGatheringTarget, timeoutMs: number): Promise<void> {
  if (pc.iceGatheringState === "complete") return Promise.resolve();
  return new Promise((resolve) => {
    const done = () => {
      clearTimeout(timer);
      pc.removeEventListener("icegatheringstatechange", onChange);
      resolve();
    };
    const onChange = () => {
      if (pc.iceGatheringState === "complete") done();
    };
    const timer = setTimeout(done, timeoutMs);
    pc.addEventListener("icegatheringstatechange", onChange);
  });
}

/** Sends one camera stream to the backend over WebRTC (send-only, video only). */
export class LiveConnection {
  private listeners = new Set<(state: LiveState) => void>();
  private currentState: LiveState = "connecting";

  private constructor(
    readonly sessionId: string,
    readonly stream: MediaStream,
    private readonly pc: RTCPeerConnection,
  ) {
    pc.addEventListener("connectionstatechange", () => this.onConnectionState());
  }

  static async start(api: ApiClient, sessionId: string, stream: MediaStream): Promise<LiveConnection> {
    const pc = new RTCPeerConnection();
    const connection = new LiveConnection(sessionId, stream, pc);
    try {
      for (const track of stream.getVideoTracks()) {
        pc.addTransceiver(track, { direction: "sendonly", streams: [stream] });
      }
      await pc.setLocalDescription(await pc.createOffer());
      await waitForIceGathering(pc, 3000);
      const local = pc.localDescription;
      if (!local) throw new Error("WebRTC offer was not created");
      const answer = await api.sendOffer(sessionId, { sdp: local.sdp, type: local.type });
      await pc.setRemoteDescription({ sdp: answer.sdp, type: answer.type as RTCSdpType });
    } catch (error) {
      connection.close();
      throw error;
    }
    return connection;
  }

  get state(): LiveState {
    return this.currentState;
  }

  subscribe(listener: (state: LiveState) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  close(): void {
    this.stream.getTracks().forEach((track) => track.stop());
    this.pc.close();
    this.setState("closed");
  }

  private onConnectionState(): void {
    const state = this.pc.connectionState;
    if (state === "connected" || state === "disconnected" || state === "failed" || state === "closed") {
      this.setState(state);
    }
  }

  private setState(state: LiveState): void {
    if (this.currentState === state) return;
    this.currentState = state;
    this.listeners.forEach((listener) => listener(state));
  }
}

/** Keeps live connections alive while the user switches between sessions. */
export class LiveRegistry {
  private connections = new Map<string, LiveConnection>();

  get(sessionId: string): LiveConnection | undefined {
    return this.connections.get(sessionId);
  }

  add(connection: LiveConnection): void {
    this.connections.get(connection.sessionId)?.close();
    this.connections.set(connection.sessionId, connection);
  }

  close(sessionId: string): void {
    this.connections.get(sessionId)?.close();
    this.connections.delete(sessionId);
  }

  closeAll(): void {
    for (const id of [...this.connections.keys()]) this.close(id);
  }
}

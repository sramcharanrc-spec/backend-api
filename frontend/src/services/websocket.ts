import { normalizePipelineEventPayload } from "../utils/pipelineSync";

export type WebSocketHealthStatus =
  | "CONNECTED"
  | "CONNECTING"
  | "DISCONNECTED"
  | "DEGRADED"
  | "ERROR";

export type WebSocketHealth = {
  status: WebSocketHealthStatus;
  connected: boolean;
  attempts: number;
  reason?: string;
  lastSeenAt?: string;
  lastHeartbeatAt?: string;
  degraded?: boolean;
};

export type AgentDetail = {
  key: string;
  agent: string;
  stage: string;
  status: string;
  active_step?: string;
  message?: string;
  started_at?: string | null;
  completed_at?: string | null;
  duration_seconds?: number | null;
  progress?: number | null;
  passed?: boolean;
  score?: number | null;
  risk_score?: number | null;
  risk_score_percent?: number | null;
  errors?: any[];
  warnings?: any[];
  output?: Record<string, any>;
  next_agent?: string | null;
};

export type PipelineEvent = {
  type?: string;
  event?: string;
  claim_id?: string;
  claimId?: string;
  status?: string;
  stage?: string;
  step?: string;
  agent?: string;
  current_stage?: string;
  current_agent?: string;
  active_step?: string;
  pipeline_state?: string;
  pipeline_status?: string;
  pipeline_result?: string;
  progress?: number;
  timestamp?: string;
  message?: string;
  data?: any;
  metadata?: any;
  details?: any;
  claim?: any;
  pipeline?: any;
  agent_detail?: AgentDetail;
  [key: string]: any;
};

export type AgentEvent = {
  claim_id?: string;
  agent?: string;
  stage?: string;
  status:
    | "pending"
    | "running"
    | "completed"
    | "failed"
    | "warning"
    | "hitl"
    | "escalated"
    | string;
  started_at?: string;
  completed_at?: string | null;
  processing_time?: number;
  confidence?: number;
  reasoning?: string;
  input?: any;
  output?: any;
  warnings?: any;
  metrics?: {
    cpu?: number;
    memory?: number;
    tokens?: number;
    latency?: number;
    throughput?: number;
  };
  ai_summary?: string;
  next_agent?: string;
  event_history?: any[];
};
const DEBUG_PIPELINE_WS = false;

const wsProtocol = window.location.protocol === "https:" ? "wss" : "ws";
const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

const now = () => new Date().toISOString();

const cleanHost = (value: string) =>
  String(value)
    .replace(/^wss?:\/\//, "")
    .replace(/^https?:\/\//, "")
    .replace(/\/$/, "");

const buildWsUrl = () => {
  const explicitHost = import.meta.env.VITE_API_HOST;

  if (explicitHost) {
    return `${wsProtocol}://${cleanHost(explicitHost)}/ws/analytics`;

  }

  try {
    const parsed = new URL(API_URL);
    return `${parsed.protocol === "https:" ? "wss" : "ws"}://${parsed.host}/ws/analytics`;
  } catch {
    return `${wsProtocol}://localhost:8000/ws/analytics`;
  }
};

const buildClaimWsUrl = (claimId: string) => {
  const encodedClaimId = encodeURIComponent(claimId);
  const explicitHost = import.meta.env.VITE_API_HOST;

  if (explicitHost) {
    return `${wsProtocol}://${cleanHost(explicitHost)}/ws/claims/${encodedClaimId}`;
  }

  try {
    const parsed = new URL(API_URL);
    return `${parsed.protocol === "https:" ? "wss" : "ws"}://${parsed.host}/ws/claims/${encodedClaimId}`;
  } catch {
    return `${wsProtocol}://localhost:8000/ws/claims/${encodedClaimId}`;
  }
};

const WS_URL = buildWsUrl();

const isHeartbeatMessage = (payload: any) => {
  const type = String(payload?.type || "").toLowerCase();
  const event = String(payload?.event || "").toLowerCase();
  const status = String(payload?.status || "").toLowerCase();

  return (
    type === "pong" ||
    type === "ping" ||
    type === "heartbeat" ||
    event === "heartbeat" ||
    status === "heartbeat"
  );
};

const isConnectionLifecycleMessage = (payload: any) => {
  const type = String(payload?.type || "").toLowerCase();
  const event = String(payload?.event || "").toLowerCase();

  return (
    type === "connection" ||
    event === "connection" ||
    type === "ws_reconnected" ||
    event === "ws_reconnected" ||
    type === "connected" ||
    event === "connected" ||
    type === "disconnected" ||
    event === "disconnected"
  );
};

const extractClaimId = (event: any): string | undefined => {
  return (
    event?.claim_id ||
    event?.claimId ||
    event?.data?.claim_id ||
    event?.data?.claimId ||
    event?.data?.claim?.claim_id ||
    event?.metadata?.claim_id ||
    event?.details?.claim_id ||
    event?.details?.claim?.claim_id ||
    event?.claim?.claim_id ||
    event?.pipeline?.claim_id
  );
};

const hasClaimSignal = (event: PipelineEvent) => {
  return Boolean(extractClaimId(event));
};

const normalizePipelineEvent = (payload: any): PipelineEvent => {
  const normalized = normalizePipelineEventPayload(payload || {}) as PipelineEvent;
  const claimId = extractClaimId(normalized);

  return {
    ...normalized,
    claim_id: claimId,
    agent_detail:
      normalized.agent_detail ||
      normalized.data?.agent_detail ||
      normalized.details?.agent_detail,
    timestamp: normalized.timestamp || normalized.data?.timestamp || now(),
  };
};

class PipelineWebSocket {
  private socket: WebSocket | null = null;

  private listeners = new Set<(event: PipelineEvent) => void>();

  private healthListeners = new Set<(health: WebSocketHealth) => void>();

  private reconnectTimer: number | null = null;

  private cooldownTimer: number | null = null;

  private heartbeatTimer: number | null = null;

  private reconnectAttempts = 0;

  private manuallyClosed = false;

  private lastPongAt = 0;

  private health: WebSocketHealth = {
    status: "DISCONNECTED",
    connected: false,
    attempts: 0,
  };

  private throttledLogs: Record<string, number> = {};

  subscribe(listener: (event: PipelineEvent) => void) {
    this.listeners.add(listener);
    this.connect();

    return () => {
      this.listeners.delete(listener);

      if (this.listeners.size === 0 && this.healthListeners.size === 0) {
        window.setTimeout(() => {
          if (this.listeners.size === 0 && this.healthListeners.size === 0) {
            this.disconnect();
          }
        }, 500);
      }
    };
  }

  subscribeHealth(listener: (health: WebSocketHealth) => void) {
    this.healthListeners.add(listener);
    listener(this.health);
    this.connect();

    return () => {
      this.healthListeners.delete(listener);

      if (this.listeners.size === 0 && this.healthListeners.size === 0) {
        window.setTimeout(() => {
          if (this.listeners.size === 0 && this.healthListeners.size === 0) {
            this.disconnect();
          }
        }, 500);
      }
    };
  }

  connect() {
    if (
      this.socket &&
      [WebSocket.CONNECTING, WebSocket.OPEN].includes(this.socket.readyState)
    ) {
      return;
    }

    this.manuallyClosed = false;

    this.setHealth({
      status: "CONNECTING",
      connected: false,
      attempts: this.reconnectAttempts,
      reason: "connecting",
    });

    try {
      this.socket = new WebSocket(WS_URL);
    } catch {
      this.setHealth({
        status: "ERROR",
        connected: false,
        attempts: this.reconnectAttempts,
        reason: "websocket initialization failed",
      });
      this.scheduleReconnect();
      return;
    }

    this.socket.onopen = () => {
      const recovered = this.reconnectAttempts > 0;

      this.reconnectAttempts = 0;
      this.lastPongAt = Date.now();

      this.setHealth({
        status: "CONNECTED",
        connected: true,
        attempts: 0,
        lastSeenAt: now(),
        lastHeartbeatAt: now(),
        degraded: false,
        reason: recovered ? "reconnected" : "connected",
      });

      this.startHeartbeat();

      if (import.meta.env.DEV && DEBUG_PIPELINE_WS) {
        console.info(
          "[pipeline-ws] connection state",
          recovered ? "reconnected" : "connected"
        );
      }
    };

    this.socket.onmessage = (event) => {
      let parsed: any;

      try {
        parsed = JSON.parse(event.data);
      } catch {
        if (import.meta.env.DEV && DEBUG_PIPELINE_WS) {
          console.warn("[pipeline-ws] ignored non-json websocket message", event.data);
        }
        return;
      }

      if (isHeartbeatMessage(parsed)) {
        this.lastPongAt = Date.now();

        this.setHealth({
          status: "CONNECTED",
          connected: true,
          attempts: this.reconnectAttempts,
          lastSeenAt: now(),
          lastHeartbeatAt: now(),
          degraded: false,
        });

        return;
      }

      if (isConnectionLifecycleMessage(parsed)) {
        this.setHealth({
          status: "CONNECTED",
          connected: true,
          attempts: this.reconnectAttempts,
          lastSeenAt: now(),
          degraded: false,
          reason: parsed?.message || "connection lifecycle event",
        });

        if (import.meta.env.DEV && DEBUG_PIPELINE_WS) {
          console.debug("[pipeline-ws] lifecycle event", parsed);
        }

        return;
      }

      const normalized = normalizePipelineEvent(parsed);

      if (!hasClaimSignal(normalized)) {
        if (import.meta.env.DEV && DEBUG_PIPELINE_WS) {
          console.debug("[pipeline-ws] ignored non-claim event", normalized);
        }

        return;
      }

      this.setHealth({
        status: "CONNECTED",
        connected: true,
        attempts: this.reconnectAttempts,
        lastSeenAt: now(),
        degraded: false,
      });

      if (import.meta.env.DEV && DEBUG_PIPELINE_WS) {
        console.groupCollapsed(
          "[pipeline-ws] Incoming websocket event",
          normalized.claim_id || normalized.type,
          normalized.stage || normalized.step || "",
          normalized.status || ""
        );
        console.log("Incoming websocket event", parsed);
        console.log("Normalized event", normalized);
        console.groupEnd();
      }

      this.emit(normalized);
    };

    this.socket.onerror = () => {
      this.setHealth({
        status: "ERROR",
        connected: false,
        attempts: this.reconnectAttempts,
        reason: "websocket error",
      });
    };

    this.socket.onclose = (event) => {
      this.stopHeartbeat();

      if (this.manuallyClosed) {
        this.setHealth({
          status: "DISCONNECTED",
          connected: false,
          attempts: this.reconnectAttempts,
          reason: "manual disconnect",
        });
        return;
      }

      this.setHealth({
        status: "DISCONNECTED",
        connected: false,
        attempts: this.reconnectAttempts,
        reason: event.reason || `closed ${event.code}`,
      });

      this.scheduleReconnect();
    };
  }

  disconnect() {
    this.manuallyClosed = true;
    this.stopHeartbeat();

    if (this.reconnectTimer) {
      window.clearTimeout(this.reconnectTimer);
    }

    if (this.cooldownTimer) {
      window.clearTimeout(this.cooldownTimer);
    }

    this.reconnectTimer = null;
    this.cooldownTimer = null;

    const socket = this.socket;
    this.socket = null;

    if (socket) {
      socket.onopen = null;
      socket.onmessage = null;
      socket.onerror = null;
      socket.onclose = null;

      if ([WebSocket.CONNECTING, WebSocket.OPEN].includes(socket.readyState)) {
        socket.close();
      }
    }

    this.setHealth({
      status: "DISCONNECTED",
      connected: false,
      reason: "manual disconnect",
    });
  }

  private emit(event: PipelineEvent) {
    this.listeners.forEach((listener) => {
      try {
        listener(event);
      } catch (error) {
        this.logThrottled(
          "listener-error",
          "error",
          "[pipeline-ws] listener failed",
          error
        );
      }
    });
  }

  private setHealth(update: Partial<WebSocketHealth>) {
    this.health = {
      ...this.health,
      ...update,
      attempts: update.attempts ?? this.reconnectAttempts,
    };

    this.healthListeners.forEach((listener) => {
      try {
        listener(this.health);
      } catch (error) {
        this.logThrottled(
          "health-listener-error",
          "error",
          "[pipeline-ws] health listener failed",
          error
        );
      }
    });
  }

  private scheduleReconnect() {
    if (this.manuallyClosed) return;
    if (this.reconnectTimer) return;
    if (this.listeners.size === 0 && this.healthListeners.size === 0) return;

    this.reconnectAttempts += 1;

    const delay = Math.min(30000, 1000 * 2 ** Math.min(this.reconnectAttempts, 5));

    this.setHealth({
      status: this.reconnectAttempts >= 5 ? "DEGRADED" : "CONNECTING",
      connected: false,
      attempts: this.reconnectAttempts,
      degraded: this.reconnectAttempts >= 5,
      reason: `reconnecting in ${Math.round(delay / 1000)}s`,
    });

    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, delay);
  }

  private startHeartbeat() {
    this.stopHeartbeat();

    this.heartbeatTimer = window.setInterval(() => {
      if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
        return;
      }

      try {
        this.socket.send(JSON.stringify({ type: "ping", timestamp: now() }));
      } catch (error) {
        this.logThrottled(
          "heartbeat-send",
          "warn",
          "[pipeline-ws] heartbeat send failed",
          error
        );
      }

      const age = Date.now() - this.lastPongAt;

      if (age > 45000) {
        this.setHealth({
          status: "DEGRADED",
          connected: true,
          degraded: true,
          reason: "heartbeat delayed",
        });
      }
    }, 15000);
  }

  private stopHeartbeat() {
    if (this.heartbeatTimer) {
      window.clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  private logThrottled(
    key: string,
    level: "debug" | "info" | "warn" | "error",
    message: string,
    detail?: any
  ) {
    if (!import.meta.env.DEV || !DEBUG_PIPELINE_WS) return;

    const nowMs = Date.now();

    if (nowMs - (this.throttledLogs[key] || 0) < 15000) {
      return;
    }

    this.throttledLogs[key] = nowMs;

    if (detail !== undefined) {
      console[level](message, detail);
    } else {
      console[level](message);
    }
  }
}

export const pipelineWS = new PipelineWebSocket();

export const addPipelineEventListener = (listener: (event: PipelineEvent) => void) =>
  pipelineWS.subscribe(listener);

export const addConnectionHealthListener = (listener: (health: WebSocketHealth) => void) =>
  pipelineWS.subscribeHealth(listener);

export type ClaimAgentWSConnection = {
  close: () => void;
};

export const connectClaimAgentWS = (
  claimId: string,
  onMessage: (data: PipelineEvent) => void,
  onHealth?: (health: WebSocketHealth) => void
): ClaimAgentWSConnection => {
  let socket: WebSocket | null = null;
  let heartbeatTimer: number | null = null;
  let reconnectTimer: number | null = null;
  let manuallyClosed = false;
  let attempts = 0;
  let lastPongAt = 0;

  const emitHealth = (update: Partial<WebSocketHealth>) => {
    onHealth?.({
      status: update.status || "DISCONNECTED",
      connected: Boolean(update.connected),
      attempts: update.attempts ?? attempts,
      reason: update.reason,
      lastSeenAt: update.lastSeenAt,
      lastHeartbeatAt: update.lastHeartbeatAt,
      degraded: update.degraded,
    });
  };

  const stopHeartbeat = () => {
    if (heartbeatTimer) {
      window.clearInterval(heartbeatTimer);
      heartbeatTimer = null;
    }
  };

  const scheduleReconnect = () => {
    if (manuallyClosed) return;
    if (reconnectTimer) return;

    attempts += 1;

    const delay = Math.min(30000, 1000 * 2 ** Math.min(attempts, 5));

    emitHealth({
      status: attempts >= 5 ? "DEGRADED" : "CONNECTING",
      connected: false,
      attempts,
      degraded: attempts >= 5,
      reason: `reconnecting in ${Math.round(delay / 1000)}s`,
    });

    reconnectTimer = window.setTimeout(() => {
      reconnectTimer = null;
      connect();
    }, delay);
  };

  const connect = () => {
    if (!claimId) {
      emitHealth({
        status: "ERROR",
        connected: false,
        reason: "claimId is required",
      });
      return;
    }

    manuallyClosed = false;

    emitHealth({
      status: "CONNECTING",
      connected: false,
      attempts,
      reason: "connecting to claim websocket",
    });

    try {
      socket = new WebSocket(buildClaimWsUrl(claimId));
    } catch {
      emitHealth({
        status: "ERROR",
        connected: false,
        attempts,
        reason: "claim websocket initialization failed",
      });
      scheduleReconnect();
      return;
    }

    socket.onopen = () => {
      attempts = 0;
      lastPongAt = Date.now();

      emitHealth({
        status: "CONNECTED",
        connected: true,
        attempts: 0,
        lastSeenAt: now(),
        lastHeartbeatAt: now(),
        degraded: false,
        reason: "connected",
      });

      try {
        socket?.send(JSON.stringify({ type: "ping", timestamp: now() }));
      } catch {
        // Ignore one-time ping failure; heartbeat/reconnect handles future state.
      }

      stopHeartbeat();

      heartbeatTimer = window.setInterval(() => {
        if (!socket || socket.readyState !== WebSocket.OPEN) {
          return;
        }

        try {
          socket.send(JSON.stringify({ type: "ping", timestamp: now() }));
        } catch {
          emitHealth({
            status: "DEGRADED",
            connected: true,
            degraded: true,
            reason: "heartbeat send failed",
          });
        }

        const age = Date.now() - lastPongAt;

        if (age > 45000) {
          emitHealth({
            status: "DEGRADED",
            connected: true,
            degraded: true,
            reason: "heartbeat delayed",
          });
        }
      }, 15000);
    };

    socket.onmessage = (event) => {
      let parsed: any;

      try {
        parsed = JSON.parse(event.data);
      } catch {
        return;
      }

      if (isHeartbeatMessage(parsed)) {
        lastPongAt = Date.now();

        emitHealth({
          status: "CONNECTED",
          connected: true,
          attempts,
          lastSeenAt: now(),
          lastHeartbeatAt: now(),
          degraded: false,
        });

        return;
      }

      if (isConnectionLifecycleMessage(parsed)) {
        emitHealth({
          status: "CONNECTED",
          connected: true,
          attempts,
          lastSeenAt: now(),
          degraded: false,
          reason: parsed?.message || "connection lifecycle event",
        });

        return;
      }

      const normalized = normalizePipelineEvent(parsed);

      emitHealth({
        status: "CONNECTED",
        connected: true,
        attempts,
        lastSeenAt: now(),
        degraded: false,
      });

      onMessage(normalized);
    };

    socket.onerror = () => {
      emitHealth({
        status: "ERROR",
        connected: false,
        attempts,
        reason: "claim websocket error",
      });
    };

    socket.onclose = (event) => {
      stopHeartbeat();

      if (manuallyClosed) {
        emitHealth({
          status: "DISCONNECTED",
          connected: false,
          attempts,
          reason: "manual disconnect",
        });
        return;
      }

      emitHealth({
        status: "DISCONNECTED",
        connected: false,
        attempts,
        reason: event.reason || `closed ${event.code}`,
      });

      scheduleReconnect();
    };
  };

  connect();

  return {
    close: () => {
      manuallyClosed = true;
      stopHeartbeat();

      if (reconnectTimer) {
        window.clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }

      if (socket) {
        socket.onopen = null;
        socket.onmessage = null;
        socket.onerror = null;
        socket.onclose = null;

        if ([WebSocket.CONNECTING, WebSocket.OPEN].includes(socket.readyState)) {
          socket.close();
        }

        socket = null;
      }

      emitHealth({
        status: "DISCONNECTED",
        connected: false,
        reason: "manual disconnect",
      });
    },
  };
};

export const connectPipelineWS = async (
  claimId: string,
  onMessage: (data: PipelineEvent) => void,
  options: {
    startPipeline?: boolean;
    useGlobalSocket?: boolean;
    onHealth?: (health: WebSocketHealth) => void;
  } = {}
) => {
  let connection: { close: () => void };

  if (options.useGlobalSocket) {
    const unsubscribe = pipelineWS.subscribe((event) => {
      if (!event.claim_id || event.claim_id === claimId) {
        onMessage(event);
      }
    });

    connection = {
      close: unsubscribe,
    };
  } else {
    connection = connectClaimAgentWS(claimId, onMessage, options.onHealth);
  }

  if (options.startPipeline) {
    try {
      await fetch(`${API_URL}/api/rcm/start-pipeline/${encodeURIComponent(claimId)}`, {
        method: "POST",
      });
    } catch (error) {
      if (import.meta.env.DEV && DEBUG_PIPELINE_WS) {
        console.error("Failed to start pipeline", error);
      }
    }
  }

  return connection;
};
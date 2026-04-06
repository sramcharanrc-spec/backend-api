// import { useCallback, useState, useRef } from "react";
// import type { Agent } from "../types/agent";
// import { runAgentApi } from "../api/agentApi";

// export function useAgents(initial: Agent[]) {
//   const [agents, setAgents] = useState<Agent[]>(initial);
//   const [logs, setLogs] = useState<string[]>([]);
//   const busyRef = useRef<Record<string, boolean>>({});

//   const pushLog = useCallback((msg: string) => {
//     setLogs((s) => [msg, ...s]);
//   }, []);

//   const runAgent = useCallback(async (id: string) => {
//     if (busyRef.current[id]) return;
//     busyRef.current[id] = true;

//     setAgents((prev) => prev.map(a => a.id === id ? { ...a, status: "running" } : a));
//     pushLog(`🚀 ${id} started`);

//     const controller = new AbortController();
//     try {
//       const data = await runAgentApi(id, controller.signal);

//       setAgents((prev) =>
//         prev.map((a) =>
//           a.id === id
//             ? { ...a, status: "completed", lastRun: new Date().toLocaleString(), successRate: typeof data.successRate === "number" ? data.successRate : a.successRate }
//             : a
//         )
//       );

//       pushLog(`✅ ${id} completed — ${JSON.stringify(data)}`);
//       return data;
//     } catch (err: any) {
//       pushLog(`❌ ${id} FAILED — ${err?.response?.data || err?.message || "unknown"}`);
//       setAgents((prev) => prev.map(a => a.id === id ? { ...a, status: "idle" } : a));
//       throw err;
//     } finally {
//       delete busyRef.current[id];
//     }
//   }, [pushLog]);

//   const runAllSequential = useCallback(async () => {
//     pushLog("🧠 Super Agent started");
//     for (const a of agents) {
//       try {
//         await runAgent(a.id);
//       } catch {
//         pushLog(`🛑 Super pipeline stopped — ${a.id} failed`);
//         return;
//       }
//     }
//     pushLog("🎉 Super Agent pipeline completed");
//   }, [agents, runAgent, pushLog]);

//   return { agents, setAgents, logs, runAgent, runAllSequential };
// }


// src/hooks/useAgents.ts
import { useEffect, useRef, useState } from "react";
import { initiateClaim } from "../apiAgent/agentApis";

type AgentInfo = {
  status: "pending" | "running" | "completed" | "failed" | "needs_fix";
  data?: any;
};

type AgentsState = Record<string, AgentInfo>;

type PipelineState = {
  agents: AgentsState;
  logs: string[];
  suggestions: any[]; // AI suggestions (denial / correction)
};

const WS_URL = process.env.REACT_APP_WS_URL || "ws://localhost:8000/ws";

export default function useAgents() {
  const [pipeline, setPipeline] = useState<PipelineState>({
    agents: {},
    logs: [],
    suggestions: [],
  });

  const wsRef = useRef<WebSocket | null>(null);
  const retryRef = useRef(0);

  useEffect(() => {
    function connect() {
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log("✅ WS connected");
        retryRef.current = 0;
      };

      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);

          console.log("📡 WS EVENT:", msg);

          // 🔥 Handle agent events
          if (msg.type === "agent_event") {
            const { step, status, data } = msg;

            setPipeline((prev) => ({
              ...prev,
              agents: {
                ...prev.agents,
                [step]: { status, data },
              },
              logs: [
                ...prev.logs,
                `⚙️ ${step.toUpperCase()} → ${status}`,
              ],
              // collect AI suggestions if present
              suggestions: data?.suggestion
                ? [...prev.suggestions, data]
                : prev.suggestions,
            }));
          }
        } catch (e) {
          console.warn("❌ WS parse error", ev.data);
        }
      };

      ws.onclose = () => {
        console.warn("⚠️ WS closed. Reconnecting...");
        retryRef.current = Math.min(10000, retryRef.current + 1000);

        setTimeout(connect, retryRef.current);
      };

      ws.onerror = (err) => {
        console.error("❌ WS error", err);
        ws.close();
      };
    }

    connect();

    return () => {
      wsRef.current?.close();
    };
  }, []);

  async function startJob(payload: any) {
    await initiateClaim(payload);

    // reset UI
    setPipeline({
      agents: {},
      logs: ["🚀 Pipeline started"],
      suggestions: [],
    });
  }

  return {
    pipeline,
    startJob,
  };
}
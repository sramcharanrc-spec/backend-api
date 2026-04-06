import React, { useState } from "react";
import axios from "axios";
import { PlayCircle, CheckCircle2, Loader2, Activity } from "lucide-react";

interface Agent {
  name: string;
  description: string;
  status: "idle" | "running" | "completed";
  successRate: number;
  lastRun?: string;
}

// ⬅ FIX: Use Vite env variable
const API_BASE = import.meta.env.VITE_API_BASE;

// Optional: if you later add auth
const authToken = localStorage.getItem("id_token") || "";
const apiKey = localStorage.getItem("api_key") || "";

// Axios client
const axiosClient = axios.create({
  baseURL: API_BASE,
  headers: {
    "Content-Type": "application/json",
    ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
    ...(apiKey ? { "x-api-key": apiKey } : {}),
  },
  timeout: 30000,
});

const Agents: React.FC = () => {
  const [agents, setAgents] = useState<Agent[]>([
    {
      name: "ETL Agent",
      description: "Extracts, cleans, and validates uploaded EHR data.",
      status: "idle",
      successRate: 96,
      lastRun: "10 Feb 2025 · 09:40",
    },
    {
      name: "Summarizer Agent",
      description: "Generates clinical summaries for doctors and staff.",
      status: "idle",
      successRate: 92,
      lastRun: "10 Feb 2025 · 09:10",
    },
    {
      name: "Claim Agent",
      description: "Auto-generates and validates insurance claims.",
      status: "idle",
      successRate: 89,
      lastRun: "09 Feb 2025 · 17:25",
    },
    {
      name: "Analytics Agent",
      description: "Creates insights, KPIs, and predictive analytics.",
      status: "idle",
      successRate: 94,
      lastRun: "09 Feb 2025 · 16:05",
    },
    {
      name: "Payment Agent",
      description: "Tracks and reconciles ERA/EFT payment data.",
      status: "idle",
      successRate: 88,
      lastRun: "08 Feb 2025 · 14:30",
    },
  ]);

  const [logs, setLogs] = useState<string[]>([]);
  const [busyAgents, setBusyAgents] = useState<Record<string, boolean>>({});

  const pushLog = (msg: string) => {
    setLogs((prev) => [msg, ...prev]);
  };

  // 🔥 API call to your Lambda → API Gateway /agentRun
  const callAgentApi = async (agentName: string) => {
    const payload = { agentName, action: "run" };
    const response = await axiosClient.post("/agentRun", payload);
    return response.data;
  };

  // Agent executor
  const runAgent = async (name: string) => {
    if (busyAgents[name]) return;

    setBusyAgents((prev) => ({ ...prev, [name]: true }));

    setAgents((prev) =>
      prev.map((a) => (a.name === name ? { ...a, status: "running" } : a))
    );

    pushLog(`🚀 ${name} started`);

    try {
      const data = await callAgentApi(name);

      setAgents((prev) =>
        prev.map((a) =>
          a.name === name
            ? {
                ...a,
                status: "completed",
                lastRun: new Date().toLocaleString(),
                successRate:
                  typeof data.successRate === "number"
                    ? data.successRate
                    : a.successRate,
              }
            : a
        )
      );

      pushLog(`✅ ${name} completed — response: ${JSON.stringify(data)}`);
    } catch (err: any) {
      console.error(err);
      pushLog(
        `❌ ${name} FAILED — ${JSON.stringify(
          err.response?.data || err.message
        )}`
      );

      setAgents((prev) =>
        prev.map((a) =>
          a.name === name ? { ...a, status: "idle" } : a
        )
      );
    } finally {
      setBusyAgents((prev) => {
        const copy = { ...prev };
        delete copy[name];
        return copy;
      });
    }
  };

  // Super agent to run all sequentially
  const runSuperAgent = async () => {
    pushLog("🧠 Super Agent started");

    for (const a of agents) {
      try {
        await runAgent(a.name);
      } catch {
        pushLog(`🛑 Stopped — ${a.name} failed`);
        return;
      }
    }

    pushLog("🎉 Super Agent pipeline completed");
  };

  const getStatusIcon = (status: Agent["status"]) => {
    switch (status) {
      case "running":
        return <Loader2 className="animate-spin text-blue-500" size={18} />;
      case "completed":
        return <CheckCircle2 className="text-emerald-500" size={18} />;
      default:
        return <Activity className="text-gray-400" size={18} />;
    }
  };

  const getStatusPill = (status: Agent["status"]) => {
    switch (status) {
      case "running":
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-blue-50 px-2 py-1 text-[11px] font-medium text-blue-700">
            <span className="h-1.5 w-1.5 rounded-full bg-blue-500 animate-pulse" />
            Running
          </span>
        );
      case "completed":
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-1 text-[11px] font-medium text-emerald-700">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
            Completed
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2 py-1 text-[11px] font-medium text-gray-700">
            <span className="h-1.5 w-1.5 rounded-full bg-gray-400" />
            Idle
          </span>
        );
    }
  };

  const total = agents.length;
  const running = agents.filter((a) => a.status === "running").length;
  const completed = agents.filter((a) => a.status === "completed").length;
  const idle = agents.filter((a) => a.status === "idle").length;

  const anyRunning = running > 0;
  const allCompleted = completed === total;
  const superStatus: "idle" | "running" | "completed" =
    anyRunning ? "running" : allCompleted ? "completed" : "idle";

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="page-title text-2xl font-bold text-blue-900">
            Agentic AI — Active Agents
          </h2>
          <p className="text-sm text-gray-500">
            Orchestrate your EHR, claims, analytics and payment workflows
            with autonomous agents.
          </p>
        </div>
        <div className="flex items-center gap-2 rounded-full bg-blue-50 px-4 py-1.5 text-xs font-medium text-blue-700 border border-blue-100">
          <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
          Orchestration healthy
        </div>
      </div>

      {/* Summary */}
      <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
        <div className="bg-white rounded-2xl shadow-sm border p-4">
          <div className="text-xs text-gray-400">Total Agents</div>
          <div className="text-2xl">{total}</div>
          <div className="text-xs text-gray-500">Configured</div>
        </div>

        <div className="bg-white rounded-2xl shadow-sm border p-4">
          <div className="text-xs text-gray-400">Running</div>
          <div className="text-2xl text-blue-700">{running}</div>
        </div>

        <div className="bg-white rounded-2xl shadow-sm border p-4">
          <div className="text-xs text-gray-400">Completed</div>
          <div className="text-2xl text-emerald-700">{completed}</div>
        </div>

        <div className="bg-white rounded-2xl shadow-sm border p-4">
          <div className="text-xs text-gray-400">Idle</div>
          <div className="text-2xl text-amber-600">{idle}</div>
        </div>
      </div>

      {/* Agent Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
        {agents.map((agent) => (
          <div
            key={agent.name}
            className="bg-white rounded-2xl shadow-sm border p-5"
          >
            <h3 className="text-base font-semibold flex items-center gap-2">
              {agent.name}
              {getStatusIcon(agent.status)}
            </h3>

            <p className="text-xs text-gray-500 mt-1">{agent.description}</p>

            <div className="mt-3">
              <div className="flex justify-between text-xs text-gray-500">
                <span>Success</span>
                <span className="font-semibold text-gray-800">
                  {agent.successRate}%
                </span>
              </div>
              <div className="h-1.5 bg-gray-100 rounded-full mt-1 overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-emerald-500 to-emerald-400"
                  style={{ width: `${agent.successRate}%` }}
                ></div>
              </div>
            </div>

            <div className="mt-4 flex justify-between items-center">
              <span className="text-[11px] text-gray-500">
                Last run: {agent.lastRun}
              </span>

              <button
                disabled={agent.status === "running"}
                onClick={() => runAgent(agent.name)}
                className={`px-3 py-1.5 rounded-full text-xs font-medium inline-flex items-center gap-1.5 ${
                  agent.status === "running"
                    ? "bg-gray-300 text-gray-600"
                    : "bg-blue-600 text-white hover:bg-blue-700"
                }`}
              >
                <PlayCircle size={14} />
                {agent.status === "running" ? "Running..." : "Run Agent"}
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* Super Agent */}
      <div className="bg-white rounded-2xl shadow-sm border p-5 flex justify-between items-center">
        <div>
          <h4 className="font-semibold">🧠 Super Agent</h4>
          <p className="text-xs text-gray-500">
            Coordinates ETL, Summarizer, Claim, Analytics & Payment agents.
          </p>
        </div>

        <button
          onClick={runSuperAgent}
          disabled={superStatus === "running"}
          className={`px-4 py-2 rounded-full text-xs font-medium inline-flex items-center gap-2 ${
            superStatus === "running"
              ? "bg-gray-300 text-gray-600"
              : "bg-indigo-600 text-white hover:bg-indigo-700"
          }`}
        >
          <PlayCircle size={14} />
          {superStatus === "running"
            ? "Super Agent Running..."
            : "Run Super Agent"}
        </button>
      </div>

      {/* Logs */}
      <div className="bg-white rounded-2xl shadow-sm border p-5">
        <h4 className="font-semibold mb-2">Agent Logs</h4>
        <div className="bg-gray-50 p-3 rounded-xl max-h-60 overflow-y-auto">
          {logs.length === 0 ? (
            <p className="text-gray-400 italic text-sm">
              No logs yet. Trigger an agent to see activity.
            </p>
          ) : (
            <ul className="space-y-1.5 text-sm">
              {logs.map((l, idx) => (
                <li key={idx} className="flex gap-2">
                  <span className="h-1.5 w-1.5 rounded-full bg-blue-500 mt-1"></span>
                  <span>{l}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
};

export default Agents;

// // src/pages/Agents/Agents.tsx
// import React, { useState } from 'react';
// import AgentCard from './components/AgentCard';
// import AgentLogPanel from './components/AgentLogPanel';
// import AgentResultModal from './components/AgentResultModal';
// import useAgents from './hooks/useAgents';

// export default function AgentsPage() {
//   const { job } = useAgents();
//   const [openResult, setOpenResult] = useState(false);

//   return (
//     <div style={{ padding: 20 }}>
//       <h2>Agents</h2>

//       {/* Example: pass patientId or a selected patient from your app state */}
//       <AgentCard patientId="P001" />

//       <div style={{ marginTop: 20 }}>
//         <AgentLogPanel logs={job.logs} />
//       </div>

//       <div style={{ marginTop: 16 }}>
//         <button onClick={() => setOpenResult(true)} disabled={!job.jobId}>
//           View Result
//         </button>
//       </div>

//       <AgentResultModal open={openResult} jobId={job.jobId} onClose={() => setOpenResult(false)} />
//     </div>
//   );
// }


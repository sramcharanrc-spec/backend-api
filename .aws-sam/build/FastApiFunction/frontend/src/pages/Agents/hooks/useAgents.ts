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

// src/pages/Agents/hooks/useAgents.ts
import { useCallback, useEffect, useRef, useState } from "react";
import {
  initiateClaim,
  getPresignUpload,
  notifyUploadComplete,
  getStatus,
  // getResultPresign — not required here but available in api file
} from "../api/agentApi";

/**
 * Hook returns a minimal API used by AgentsPage & AgentCard
 * - job: { jobId, status, progress, resultKey, logs }
 * - startJob(payload, file?) : starts a job and manages uploading/polling
 */

export type JobInfo = {
  jobId?: string | null;
  status?: string;
  progress?: number;
  resultKey?: string | null;
  logs?: string[];
};

const POLL_INTERVAL_MS = 2000;
const POLL_TIMEOUT_MS = 1000 * 60 * 5; // 5 minutes default timeout for polling

export default function useAgents() {
  const [job, setJob] = useState<JobInfo>({ jobId: null, status: undefined, progress: undefined, resultKey: null, logs: [] });
  const pollingRef = useRef<number | null>(null);
  const pollStartRef = useRef<number | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, []);

  const pushLog = useCallback((msg: string) => {
    setJob((j) => ({ ...j, logs: [msg, ...(j.logs ?? [])] }));
  }, []);

  const pollStatus = useCallback(async (jobId: string) => {
    // stop any existing polling
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }

    pollStartRef.current = Date.now();

    const check = async () => {
      try {
        const statusResp = await getStatus(jobId);
        if (!mountedRef.current) return;

        setJob((prev) => ({
          ...prev,
          jobId,
          status: statusResp.status,
          progress: statusResp.progress,
          resultKey: statusResp.resultKey ?? prev.resultKey,
        }));

        // finished
        if (statusResp.status === "completed" || statusResp.status === "failed") {
          pushLog(`Job ${jobId} ${statusResp.status}`);
          if (pollingRef.current) {
            clearInterval(pollingRef.current);
            pollingRef.current = null;
          }
        } else {
          // timeout guard
          if (pollStartRef.current && Date.now() - pollStartRef.current > POLL_TIMEOUT_MS) {
            pushLog(`Job ${jobId} polling timed out`);
            if (pollingRef.current) {
              clearInterval(pollingRef.current);
              pollingRef.current = null;
            }
          }
        }
      } catch (err) {
        console.error("Error polling status:", err);
        pushLog(`Error polling status: ${(err as any)?.message ?? err}`);
      }
    };

    // first immediate check
    await check();

    // then interval-based checks
    pollingRef.current = window.setInterval(check, POLL_INTERVAL_MS);
  }, [pushLog]);

  /**
   * startJob:
   *  - calls initiateClaim(payload)
   *  - if presignKey returned and file provided -> uploads file via PUT to presigned URL
   *  - calls notifyUploadComplete
   *  - starts polling status
   */
  const startJob = useCallback(
    async (payload: { patientId?: string; [k: string]: any } = {}, file?: File | undefined) => {
      try {
        pushLog("Initiating claim...");
        const init = await initiateClaim(payload);
        const jobId = init.jobId;
        const presignKey = init.presignKey ?? undefined;

        setJob({ jobId, status: "initiated", progress: 0, resultKey: null, logs: [`initiated job ${jobId}`] });

        // if there's a file and we got a presign key — fetch presign url and upload
        if (file && presignKey) {
          pushLog("Requesting presigned upload URL...");
          const presignResp = await getPresignUpload(presignKey);
          const uploadUrl = presignResp.url;

          pushLog("Uploading file to presigned URL...");
          // do a straight PUT (no axios needed) with file
          await fetch(uploadUrl, {
            method: "PUT",
            body: file,
            // content-type header is often required to match signature provider; omit or set based on backend requirements
          });

          pushLog("Upload complete — notifying backend");
          await notifyUploadComplete(jobId, presignKey);
        } else {
          pushLog("No file to upload or no presign key returned");
        }

        // start polling job status
        pushLog(`Polling status for job ${jobId}...`);
        await pollStatus(jobId);

        return jobId;
      } catch (err) {
        console.error("startJob error:", err);
        pushLog(`Failed to start job: ${(err as any)?.message ?? err}`);
        setJob((prev) => ({ ...prev, status: "failed" }));
        throw err;
      }
    },
    [pollStatus, pushLog]
  );

  return {
    job,
    startJob,
    // optional extras you may later want:
    // cancelPolling, manualPoll, results map, runAgent, runAllSequential etc.
  };
}

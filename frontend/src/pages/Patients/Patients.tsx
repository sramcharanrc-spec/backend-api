

import React, { useEffect, useRef, useState } from "react";
import axios from "axios";
import "../../styles/main.css";
import {
  Activity,
  AlertTriangle,
  Brain,
  ChevronDown,
  ChevronRight,
  DollarSign,
  FileCheck,
  Search,
  ShieldCheck,
  Users as UsersIcon,
} from "lucide-react";
import { API_URL } from "../../config";


/* ================= TYPES ================= */

interface Patient {
  patient_id?: string;
  patient_name?: string;
  age?: string | number;
  phone?: string;
  cpt_codes?: string[];
}

interface PatientsProps {
  ehrData?: Patient[] | null;
}

/* ================= CONSTANTS ================= */

const CLAIM_STAGES = ["INITIATE", "EXT", "VALIDATED", "PDF", "EDI", "SUCCESS"];
const PAGE_SIZE = 5;

const PIPELINE_AGENTS = [
  {
    id: "INITIATION",
    label: "Initiation",
    icon: "🚀",
  },
  {
    id: "EXTRACTION",
    label: "Extraction",
    icon: "📄",
  },
  {
    id: "VALIDATION",
    label: "Validation",
    icon: "✅",
  },
  {
    id: "CMS1500",
    label: "CMS1500 PDF",
    icon: "📑",
  },
  {
    id: "EDI",
    label: "EDI",
    icon: "📨",
  },
  {
    id: "CLEARINGHOUSE",
    label: "Clearinghouse",
    icon: "🏢",
  },
  {
    id: "DENIAL_AI",
    label: "Denial AI",
    icon: "🧠",
  },
  {
    id: "PAYMENT",
    label: "Payment",
    icon: "💰",
  },
  {
    id: "LEARNING",
    label: "Learning",
    icon: "🎓",
  },
  {
    id: "ANALYTICS",
    label: "Analytics",
    icon: "📊",
  },
];

const PIPELINE_AGENT_ICONS: Record<string, string> = {
  INITIATION: "🚀",
  EXTRACTION: "📄",
  VALIDATION: "✅",
  CMS1500: "📑",
  EDI: "📨",
  CLEARINGHOUSE: "🏢",
  DENIAL_AI: "🧠",
  PAYMENT: "💰",
  LEARNING: "🎓",
  ANALYTICS: "📊",
};

const normalizeStage = (stage?: string) => {
  const s = (stage || "").toUpperCase().trim();
  if (["DONE", "COMPLETED", "FINISHED"].includes(s)) return "SUCCESS";
  return s;
};

const getStageIndex = (stage?: string) =>
  CLAIM_STAGES.indexOf(normalizeStage(stage));

const normalizePipelineStage = (stage?: string) => {
  const s = normalizeStage(stage).replace(/[\s-]+/g, "_");
  if (["INITIATE", "INITIATION", "START", "STARTED", "QUEUE", "QUEUED", "CASE", "CASE_ORCHESTRATED", "ORCHESTRATION"].includes(s)) return "INITIATION";
  if (["EXT", "EXTRACT", "EXTRACTION", "EXTRACTION_AGENT", "EXTRACTION_DONE", "OCR", "OCR_AGENT", "OCR_RUNNING", "INTAKE"].includes(s)) return "EXTRACTION";
  if (["VALIDATED", "VALIDATION", "VALIDATION_AGENT", "RULES", "RULES_VALIDATED", "ELIGIBILITY", "ELIGIBILITY_CHECKED"].includes(s)) return "VALIDATION";
  if (["PDF", "CMS1500", "CMS1500_PDF", "CMS1500_AGENT", "GENERATING_CMS1500"].includes(s)) return "CMS1500";
  if (["EDI", "EDI_GENERATION", "EDI_AGENT", "GENERATING_EDI", "GENERATING_837", "SUBMISSION", "SUBMISSION_AGENT", "SUBMITTED"].includes(s)) return "EDI";
  if (["CLEARINGHOUSE", "CLEARINGHOUSE_AGENT", "CLEARINGHOUSE_APPROVED", "CLEARINGHOUSE_PROCESSING", "CLEARINGHOUSE_QUEUED", "ACK", "ACKNOWLEDGED", "ACKNOWLEDGMENT", "WAITING_FOR_APPROVAL", "PENDING_CLEARINGHOUSE"].includes(s)) return "CLEARINGHOUSE";
  if (["DENIAL", "DENIAL_AI", "DENIAL_AI_AGENT", "DENIAL_CHECKED", "DENIAL_AI_ANALYZED"].includes(s)) return "DENIAL_AI";
  if (["PAYMENT", "PAYMENT_AGENT", "PAID", "ERA", "RECONCILIATION"].includes(s)) return "PAYMENT";
  if (["LEARNING", "LEARNING_AGENT", "FEEDBACK", "FEEDBACK_LOOP", "LEARNING_UPDATED"].includes(s)) return "LEARNING";
  if (["ANALYTICS", "ANALYTICS_AGENT", "ANALYTICS_DONE", "METRICS", "SUCCESS", "COMPLETED", "DONE", "FINISHED"].includes(s)) return "ANALYTICS";
  return s;
};

const getEventClaimId = (payload: any) =>
  payload?.claim_id ||
  payload?.claimId ||
  payload?.data?.claim_id ||
  payload?.data?.claimId ||
  payload?.metadata?.claim_id ||
  payload?.pipeline?.claim_id;

const getEventPatientId = (payload: any) =>
  payload?.patient_id ||
  payload?.patientId ||
  payload?.data?.patient_id ||
  payload?.data?.patientId ||
  payload?.metadata?.patient_id;

/* ================= API ================= */

const API_ROOT =
  import.meta.env.VITE_API_ROOT ||
  "https://zwht8u3a0e.execute-api.us-east-1.amazonaws.com/prod";

const CLAIM_API = `${API_ROOT}/bedrock`;
const POLL_API = `${API_ROOT}/generateClaim`;
const VIEW_FORM_API = `${API_ROOT}/viewForm`;
const WS_URL = API_URL.replace(/^https?:\/\//, (protocol) =>
  protocol === "https://" ? "wss://" : "ws://"
);

/* ================= SAMPLE DATA ================= */

const SAMPLE_PATIENTS: Patient[] = Array.from({ length: 20 }, (_, i) => {
  const id = `P${String(i + 1).padStart(3, "0")}`;
  return {
    patient_id: id,
    patient_name: id,
    age: Math.floor(Math.random() * 40) + 20,
    cpt_codes: i % 2 === 0 ? ["99213"] : [],
  };
});

/* ================= SAFE STAGE ADVANCE ================= */

const getSafeNextStage = (prev?: string, incoming?: string) => {
  const prevIdx = getStageIndex(prev);
  const nextIdx = getStageIndex(incoming);

  if (prevIdx === -1) return incoming;
  if (nextIdx === -1) return prev;

  if (nextIdx > prevIdx + 1) {
    return CLAIM_STAGES[prevIdx + 1];
  }
  return incoming;
};

const getStepperStageFromPipeline = (stage?: string, status?: string) => {
  const normalizedStatus = normalizeStage(status);
  if (["SUCCESS", "PAID"].includes(normalizedStatus)) return "SUCCESS";

  switch (normalizePipelineStage(stage)) {
    case "INITIATION":
      return "INITIATE";
    case "EXTRACTION":
      return "EXT";
    case "VALIDATION":
      return "VALIDATED";
    case "CMS1500":
      return "PDF";
    case "EDI":
    case "CLEARINGHOUSE":
    case "DENIAL_AI":
    case "PAYMENT":
    case "LEARNING":
      return "EDI";
    case "ANALYTICS":
      return "SUCCESS";
    default:
      return normalizeStage(stage);
  }
};

/* ================= STEPPER ================= */

const ClaimStepper: React.FC<{ stage?: string }> = ({ stage }) => {
  const idx = getStageIndex(stage);

  return (
    <div className="w-full">
      <div className="flex items-center justify-between">
        {CLAIM_STAGES.map((s, i) => (
          <div key={s} className="flex-1 flex items-center">
            <div
              className={`w-3 h-3 rounded-full ${
                i <= idx ? "bg-green-500" : "bg-gray-300"
              }`}
            />
            {i < CLAIM_STAGES.length - 1 && (
              <div
                className={`flex-1 h-[2px] mx-1 ${
                  i < idx ? "bg-green-500" : "bg-gray-300"
                }`}
              />
            )}
          </div>
        ))}
      </div>
      <div className="flex justify-between mt-1 text-[9px] text-gray-500">
        {CLAIM_STAGES.map((s) => (
          <div key={s} className="flex-1 text-center">
            {s}
          </div>
        ))}
      </div>
    </div>
  );
};

/* ================= COMPONENT ================= */

const Patients: React.FC<PatientsProps> = ({ ehrData }) => {
  const [data, setData] = useState<Patient[]>(ehrData ?? SAMPLE_PATIENTS);
  const [searchTerm, setSearchTerm] = useState("");
  const [page, setPage] = useState(1);

  const [processing, setProcessing] = useState<Record<string, boolean>>({});
  const [progressStage, setProgressStage] = useState<Record<string, string>>({});
  const [patientClaims, setPatientClaims] = useState<Record<string, string>>({});
  const [forms, setForms] = useState<
    Record<string, { pdfUrl?: string; ediUrl?: string }>
  >({});
  const [lastSynced, setLastSynced] = useState<Record<string, string>>({});
  const [expandedRows, setExpandedRows] = useState<Record<string, boolean>>({});
  const [agentPipeline, setAgentPipeline] = useState<
    Record<
      string,
      {
        currentAgent: string;
        currentStage: string;
        progress: number;
        status: string;
        history: any[];
      }
    >
  >({});

  const [toast, setToast] = useState<{ msg: string; type: "error" | "info" } | null>(null);
  const intervalRef = useRef<Record<string, number | null>>({});
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const shouldReconnectRef = useRef(true);
  const patientClaimsRef = useRef<Record<string, string>>({});

  useEffect(() => {
    setData(ehrData && ehrData.length ? ehrData : SAMPLE_PATIENTS);
  }, [ehrData]);

  useEffect(() => {
    patientClaimsRef.current = patientClaims;
  }, [patientClaims]);

  useEffect(() => {
    shouldReconnectRef.current = true;

    const clearReconnectTimer = () => {
      if (reconnectTimerRef.current) {
        window.clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
    };

    const scheduleReconnect = () => {
      if (!shouldReconnectRef.current || reconnectTimerRef.current) return;
      reconnectTimerRef.current = window.setTimeout(() => {
        reconnectTimerRef.current = null;
        connect();
      }, 3000);
    };

    const connect = () => {
      if (!shouldReconnectRef.current) return;

      if (
        socketRef.current &&
        [WebSocket.CONNECTING, WebSocket.OPEN].includes(socketRef.current.readyState)
      ) {
        return;
      }

      const socket = new WebSocket(`${WS_URL}/ws/analytics`);
      socketRef.current = socket;

      socket.onmessage = (event) => {
        let payload: any;
        try {
          payload = JSON.parse(event.data);
        } catch {
          return;
        }

        const rawClaimId = getEventClaimId(payload);
        if (!rawClaimId) return;

        const claimId = String(rawClaimId);
        const rawPatientId = getEventPatientId(payload);
        const patientIdForEvent = rawPatientId
          ? String(rawPatientId)
          : Object.entries(patientClaimsRef.current).find(([, mappedClaimId]) => mappedClaimId === claimId)?.[0];

        if (rawPatientId) {
          setPatientClaims((prev) =>
            prev[String(rawPatientId)] === claimId
              ? prev
              : {
                  ...prev,
                  [String(rawPatientId)]: claimId,
                }
          );
        }

        const eventStage =
          payload.data?.current_stage ||
          payload.current_stage ||
          payload.stage ||
          payload.step;
        const eventStatus = payload.status || payload.data?.status;

        if (patientIdForEvent && (eventStage || eventStatus)) {
          const nextStepperStage = getStepperStageFromPipeline(eventStage, eventStatus);
          setProgressStage((prev) => ({
            ...prev,
            [patientIdForEvent]:
              nextStepperStage === "SUCCESS"
                ? "SUCCESS"
                : getSafeNextStage(prev[patientIdForEvent], nextStepperStage),
          }));
        }

        setAgentPipeline((prev) => {
          const previous = prev[claimId];
          const currentStage =
            eventStage ||
            previous?.currentStage ||
            "INITIATION";
          const currentAgent =
            payload.data?.current_agent ||
            payload.current_agent ||
            payload.agent ||
            previous?.currentAgent ||
            "INITIATION";
          const progress = Number(
            payload.data?.progress ??
              payload.progress ??
              previous?.progress ??
              0
          );
          const status =
            payload.status ||
            payload.data?.status ||
            previous?.status ||
            "PROCESSING";
          const history = [
            ...(previous?.history || []),
            {
              timestamp: payload.timestamp || payload.data?.timestamp || new Date().toISOString(),
              agent: currentAgent,
              stage: currentStage,
              status,
            },
          ];

          return {
            ...prev,
            [claimId]: {
              currentAgent,
              currentStage,
              progress,
              status,
              history,
            },
          };
        });
      };

      socket.onclose = () => {
        if (socketRef.current === socket) {
          socketRef.current = null;
        }
        scheduleReconnect();
      };

      socket.onerror = () => {
        socket.close();
      };
    };

    connect();

    return () => {
      shouldReconnectRef.current = false;
      clearReconnectTimer();
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, []);

  const showToast = (msg: string, type: "error" | "info" = "info") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 2500);
  };

  const hasCptCodes = (p?: Patient) =>
    Array.isArray(p?.cpt_codes) && p.cpt_codes.length > 0;

  const toggleExpand = (id: string) => {
    setExpandedRows((prev) => ({
      ...prev,
      [id]: !prev[id],
    }));
  };

  /* ================= POLLING ================= */

  const pollProgress = async (id: string) => {
  try {
    const res = await axios.post(POLL_API, {
      path: "/generateClaim",
      patientId: id,
    });

    const { progress, status } = res.data || {};

    if (progress) {
      setProgressStage((p) => ({
        ...p,
        [id]: getSafeNextStage(p[id], normalizeStage(progress)),
      }));
    }

    /* ================= SUCCESS ================= */
    if (status === "SUCCESS") {
      if (intervalRef.current[id]) {
        clearInterval(intervalRef.current[id]!);
        intervalRef.current[id] = null;
      }

      setProcessing((p) => ({ ...p, [id]: false }));
      setProgressStage((p) => ({ ...p, [id]: "SUCCESS" }));

      showToast(`Claim completed for ${id}`);

      try {
        console.log("🚀 Fetching latest claim from S3...");

        const res2 = await axios.post(
          `${API_URL}/api/rcm/submit-from-s3`,
          {
            patient_id: id,
          }
        );

        console.log("✅ S3 Response:", res2.data);

        const submissionId =
          res2.data?.pipeline_result?.claim?.submission_id ||
          res2.data?.claim_id ||
          res2.data?.submission_id;

        if (!submissionId) {
          console.error("❌ No submissionId found");
          showToast("Pipeline started but ID missing", "error");
          return;
        }

        console.log("🎯 Submission ID:", submissionId);

        patientClaimsRef.current = {
          ...patientClaimsRef.current,
          [id]: submissionId,
        };

        setPatientClaims((prev) => ({
          ...prev,
          [id]: submissionId,
        }));

        setProgressStage((prev) => ({
          ...prev,
          [id]: "INITIATE",
        }));

        setAgentPipeline((prev) => ({
          ...prev,
          [submissionId]: prev[submissionId] || {
            currentAgent: "INITIATION",
            currentStage: "INITIATION",
            progress: 0,
            status: "PROCESSING",
            history: [],
          },
        }));

        localStorage.setItem(
          "agentPipeline",
          JSON.stringify({
            submission_id: submissionId,
            patient_id: id,
            data: res2.data,
          })
        );

        setExpandedRows((prev) => ({
          ...prev,
          [id]: true,
        }));
      } catch (err) {
        console.error("❌ S3 pipeline failed", err);
        showToast("Pipeline trigger failed", "error");
      }
    }

  } catch (e) {
    console.error(e);
  }
};



  const startPolling = (id: string) => {
    if (intervalRef.current[id]) {
      clearInterval(intervalRef.current[id]!);
    }

    pollProgress(id);
    intervalRef.current[id] = window.setInterval(() => pollProgress(id), 1000);
  };

  useEffect(() => {
    return () => {
      Object.values(intervalRef.current).forEach((timer) => {
        if (timer) clearInterval(timer);
      });
    };
  }, []);

  /* ================= ACTIONS ================= */

  const handleGenerateClaim = async (id: string) => {
    const patient = data.find((p) => p.patient_id === id);

    if (!hasCptCodes(patient)) {
      showToast("No CPT codes found. Cannot generate claim.", "error");
      return;
    }

    try {
      setProcessing((p) => ({ ...p, [id]: true }));
      setProgressStage((p) => ({ ...p, [id]: "INITIATE" }));
      await axios.post(CLAIM_API, { path: "/bedrock", patientId: id });
      startPolling(id);
    } catch {
      setProcessing((p) => ({ ...p, [id]: false }));
      showToast("Failed to start claim", "error");
    }
  };

  const handleLoadFiles = async (id: string) => {
    try {
      const res = await axios.post(VIEW_FORM_API, { path: "/viewForm", patientId: id });
      const { pdf, edi } = res.data || {};

      const hasPdf = !!pdf?.url;
      const hasEdi = !!edi?.url;

      if (!hasPdf && !hasEdi) {
        showToast("Files not ready yet", "error");
        return;
      }

      setForms((p) => ({
        ...p,
        [id]: { pdfUrl: pdf?.url, ediUrl: edi?.url },
      }));

      setLastSynced((p) => ({
        ...p,
        [id]: new Date().toLocaleString(),
      }));
    } catch {
      showToast("Failed to load files", "error");
    }
  };

  /* ================= FILTER + PAGINATION ================= */

  const filtered = data.filter((p) =>
    p.patient_id?.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const startIndex = (page - 1) * PAGE_SIZE;
  const paginated = filtered.slice(startIndex, startIndex + PAGE_SIZE);

  /* ================= UI ================= */

  return (
    <div className="p-6 space-y-4">
      {toast && (
        <div className={`px-4 py-2 rounded border text-sm ${
          toast.type === "error"
            ? "bg-red-50 text-red-700 border-red-300"
            : "bg-blue-50 text-blue-700 border-blue-300"
        }`}>
          {toast.msg}
        </div>
      )}

      <div className="flex justify-between">
        <h2 className="text-2xl font-bold flex gap-2"><UsersIcon /> Patients</h2>
        <div className="relative w-64">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-gray-400" />
          <input
            className="w-full pl-9 pr-3 py-2 border rounded"
            placeholder="Search patient..."
            value={searchTerm}
            onChange={(e) => { setSearchTerm(e.target.value); setPage(1); }}
          />
        </div>
      </div>

      <div className="bg-white rounded-xl shadow border overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-slate-500">
            <tr>
              <th className="px-5 py-3 text-left">Patient ID</th>
              <th className="px-5 py-3 text-left">Age</th>
              <th className="px-5 py-3 text-left">Claim Progress</th>
              <th className="px-5 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {paginated.map((p) => {
              const id = p.patient_id!;
              const success = progressStage[id] === "SUCCESS";
              const loaded = !!forms[id];
              const claimId = patientClaims[id] || id;
              const hasClaim = Boolean(patientClaims[id]);
              const livePipeline = agentPipeline[claimId];
              const effectiveStage = livePipeline?.currentStage || progressStage[id];
              const pipelineStatus = String(livePipeline?.status || "").toUpperCase();
              const pipelineProgress = Math.min(
                100,
                livePipeline?.progress ||
                  Math.round(((livePipeline?.history?.length || 0) / PIPELINE_AGENTS.length) * 100)
              );
              const pipelineComplete =
                ["COMPLETED", "SUCCESS", "PAID"].includes(pipelineStatus) ||
                (normalizePipelineStage(effectiveStage) === "ANALYTICS" && pipelineProgress >= 100);
              const lifecycleStatus = pipelineComplete
                ? "Completed"
                : processing[id] || livePipeline || success
                ? "In Progress"
                : "Waiting";
              const CurrentStatusIcon = lifecycleStatus === "Completed" ? ShieldCheck : AlertTriangle;

              return (
                <React.Fragment key={id}>
                  <tr className="border-b">
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => toggleExpand(id)}
                          className="p-1 rounded hover:bg-slate-100 text-slate-500"
                          aria-label={expandedRows[id] ? `Collapse ${id}` : `Expand ${id}`}
                        >
                          {expandedRows[id] ? (
                            <ChevronDown className="w-4 h-4" />
                          ) : (
                            <ChevronRight className="w-4 h-4" />
                          )}
                        </button>

                        {id}
                      </div>
                    </td>
                    <td className="px-5 py-3">{p.age}</td>
                    <td className="px-5 py-3 w-[320px]">
                      {progressStage[id] && <ClaimStepper stage={progressStage[id]} />}
                      {lastSynced[id] && (
                        <div className="text-[10px] text-emerald-600 mt-1">
                          Last Synced: {lastSynced[id]}
                        </div>
                      )}
                    </td>
                    <td className="px-5 py-3 flex justify-end gap-2 flex-wrap">
                      <button
                        onClick={() => handleGenerateClaim(id)}
                        disabled={processing[id] || success || hasClaim}
                        className={`px-4 py-1.5 rounded text-xs ${
                          processing[id] || success || hasClaim ? "bg-gray-300" : "bg-blue-600 text-white"
                        }`}
                      >
                        Generate Claim
                      </button>

                      <button
                        onClick={() => handleLoadFiles(id)}
                        disabled={!success || loaded}
                        className={`px-4 py-1.5 rounded text-xs ${
                          success && !loaded ? "bg-indigo-600 text-white" : "bg-gray-300"
                        }`}
                      >
                        Load Files
                      </button>

                      <button
                        disabled={!forms[id]?.pdfUrl}
                        onClick={() => window.open(forms[id]?.pdfUrl!, "_blank")}
                        className={`px-4 py-1.5 rounded text-xs ${
                          forms[id]?.pdfUrl ? "bg-emerald-600 text-white" : "bg-gray-300"
                        }`}
                      >
                        View PDF
                      </button>

                      <button
                        disabled={!forms[id]?.ediUrl}
                        onClick={() => window.open(forms[id]?.ediUrl!, "_blank")}
                        className={`px-4 py-1.5 rounded text-xs ${
                          forms[id]?.ediUrl ? "bg-orange-600 text-white" : "bg-gray-300"
                        }`}
                      >
                        Submit EDI
                      </button>
                    </td>
                  </tr>

                  {expandedRows[id] && (
                    <tr>
                      <td colSpan={4} className="bg-slate-50 px-6 py-6">
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                          <div className="bg-white rounded-xl border p-4">
                            <h3 className="font-semibold mb-3 flex items-center gap-2">
                              <FileCheck className="w-4 h-4 text-indigo-600" />
                              Patient Information
                            </h3>

                            <p>Patient: {p.patient_name || id}</p>
                            <p>Patient ID: {id}</p>
                            <p>Age: {p.age}</p>
                          </div>

                          <div className="bg-white rounded-xl border p-4">
                            <h3 className="font-semibold mb-3 flex items-center gap-2">
                              <Brain className="w-4 h-4 text-indigo-600" />
                              Current Agent
                            </h3>

                            <div className="text-indigo-600 font-bold text-lg">
                              {livePipeline?.currentAgent || "WAITING"}
                            </div>

                            <div className="text-sm text-gray-500">
                              Status: {livePipeline?.status || "WAITING"}
                            </div>

                            <div className="mt-2">
                              Progress: {pipelineProgress}%
                            </div>
                          </div>

                          <div className="bg-white rounded-xl border p-4">
                            <h3 className="font-semibold mb-3 flex items-center gap-2">
                              <Activity className="w-4 h-4 text-indigo-600" />
                              Files
                            </h3>

                            <p>PDF: {forms[id]?.pdfUrl ? "Ready" : "Pending"}</p>
                            <p>EDI: {forms[id]?.ediUrl ? "Ready" : "Pending"}</p>
                          </div>
                        </div>

                        <div className="mt-6 bg-white rounded-xl border p-6">
                          <h3 className="font-semibold mb-4 flex items-center gap-2">
                            <Activity className="w-4 h-4 text-indigo-600" />
                            Pipeline Tracker
                          </h3>

                          <div className="flex justify-between gap-2 overflow-x-auto pb-2">
                            {PIPELINE_AGENTS.map((stage, index) => {
                              const current = normalizePipelineStage(
                                livePipeline?.currentStage || progressStage[id]
                              );
                              const currentIndex = PIPELINE_AGENTS.findIndex((item) => item.id === current);
                              const completed = pipelineComplete || index < currentIndex;
                              const active = !pipelineComplete && index === currentIndex;

                              return (
                                <div key={stage.id} className="flex flex-col items-center relative min-w-[82px]">
                                  <div
                                    className={`w-12 h-12 rounded-full flex items-center justify-center transition-all ${
                                      active
                                        ? "bg-blue-600 animate-pulse text-white scale-110"
                                        : completed
                                        ? "bg-green-500 text-white"
                                        : "bg-gray-200 text-gray-500"
                                    }`}
                                  >
                                    {PIPELINE_AGENT_ICONS[stage.id] || stage.icon}
                                  </div>

                                  <div className="text-xs mt-2 text-center">
                                    {stage.label}
                                  </div>

                                  {active && (
                                    <div className="text-[10px] text-blue-500 font-medium mt-1">
                                      Processing...
                                    </div>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        </div>

                        <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-4">
                          <div className="bg-white rounded-xl border p-4">
                            <h3 className="font-semibold mb-2 flex items-center gap-2">
                              <ShieldCheck className="w-4 h-4 text-emerald-600" />
                              Claim Lifecycle
                            </h3>
                            <p className="text-sm text-slate-600">{lifecycleStatus}</p>
                          </div>

                          <div className="bg-white rounded-xl border p-4">
                            <h3 className="font-semibold mb-2 flex items-center gap-2">
                              <DollarSign className="w-4 h-4 text-emerald-600" />
                              Realtime Progress
                            </h3>
                            <p className="text-sm text-slate-600">{pipelineProgress}% complete</p>
                          </div>

                          <div className="bg-white rounded-xl border p-4">
                            <h3 className="font-semibold mb-2 flex items-center gap-2">
                              <CurrentStatusIcon className="w-4 h-4 text-amber-600" />
                              Current Agent Status
                            </h3>
                            <p className="text-sm text-slate-600">
                              {livePipeline?.status || (processing[id] ? "Processing" : success ? "Completed" : "Idle")}
                            </p>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="flex justify-between text-xs">
        <span>
          Showing {startIndex + 1}–{Math.min(startIndex + PAGE_SIZE, filtered.length)} of {filtered.length}
        </span>
        <div className="flex gap-2">
          <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1}>Prev</button>
          <span>Page {page} of {totalPages}</span>
          <button onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page === totalPages}>Next</button>
        </div>
      </div>
    </div>
  );
};

export default Patients;


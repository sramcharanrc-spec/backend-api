import React, { useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import "../../styles/main.css";

import { Users as UsersIcon, Search, FileText } from "lucide-react";

interface Patient {
  patient_name?: string;
  name?: string;
  patient_id?: string;
  age?: string | number;
  diagnosis?: string;
  visit_date?: string;
  date?: string;
  phone?: string;
  raw?: Record<string, any>;
  [k: string]: any;
}

interface PatientsProps {
  ehrData?: Patient[] | null;
}

interface ClaimJob {
  jobId: string;
  status?: string;
  message?: string;
  lastUpdated: number;
}

/** API root and endpoints */
const API_ROOT =
  import.meta.env.VITE_API_ROOT ||
  "https://zwht8u3a0e.execute-api.us-east-1.amazonaws.com/prod";
const CLAIM_API = import.meta.env.VITE_CLAIM_API || `${API_ROOT}/bedrock`;
const VIEW_FORM_API =
  import.meta.env.VITE_VIEW_FORM_API || `${API_ROOT}/viewForm`;
const POLL_API = `${API_ROOT}/generateClaim`;

/** Sample dataset (used when no ehrData is passed) */
const SAMPLE_PATIENTS: Patient[] = Array.from({ length: 70 }, (_, i) => {
  const id = `P${String(i + 1).padStart(3, "0")}`;
  return {
    patient_id: id,
    patient_name: id,
    age: Math.floor(Math.random() * 40) + 20,
    phone: `98765${Math.floor(10000 + Math.random() * 90000)}`,
  };
});

const PAGE_SIZE = 10;

const Patients: React.FC<PatientsProps> = ({ ehrData }) => {
  const [data, setData] = useState<Patient[]>(ehrData ?? SAMPLE_PATIENTS);

  // UI state
  const [searchTerm, setSearchTerm] = useState("");
  const [page, setPage] = useState(1);

  // Per-patient state maps (multi-job support)
  const [processingPatients, setProcessingPatients] = useState<Record<string, boolean>>({});
  const [progressStage, setProgressStage] = useState<Record<string, string>>({});
  const [jobStatus, setJobStatus] = useState<Record<string, string>>({});
  const [progressPercent, setProgressPercent] = useState<Record<string, number>>({});
  const [forms, setForms] = useState<Record<string, boolean>>({});

  // Jobs map (optional persistence)
  const [jobsByPatient, setJobsByPatient] = useState<Record<string, ClaimJob>>({});

  // message + modal state
  const [message, setMessage] = useState<{ type: "" | "success" | "warning" | "error"; text: string }>({ type: "", text: "" });
  const [formData, setFormData] = useState<{ url: string; patientId: string; formType?: string } | null>(null);

  // Toast
  const [toast, setToast] = useState({ show: false, type: "", text: "" });
  const showToast = (type: string, text: string) => {
    setToast({ show: true, type, text });
    setTimeout(() => setToast({ show: false, type: "", text: "" }), 2500);
  };

  // Store interval IDs outside React state to avoid rerenders & keep references per patient
  const intervalRef = useRef<Record<string, number | null>>({});

  useEffect(() => {
    if (ehrData && ehrData.length > 0) setData(ehrData);
    else setData(SAMPLE_PATIENTS);
  }, [ehrData]);

  // progress stage → percent mapping
  const getProgressPercent = (stage?: string) => {
    switch ((stage || "").toUpperCase()) {
      case "INITIATED":
      case "QUEUED":
        return 10;
      case "EXTRACTING":
        return 30;
      case "VALIDATED":
        return 60;
      case "PDF":
        return 75;
      case "EDI":
      case "EDI_GENERATING":
        return 85;
      case "SUCCESS":
        return 100;
      default:
        return 5;
    }
  };

  // Poll progress for a single patient
  const pollProgress = async (patientId: string) => {
    try {
      const res = await axios.post(POLL_API, {
        path: "/generateClaim",
        patientId,
      });

      const { progress, status, jobId, message: apiMessage } = res.data || {};

      // Debug
      // console.log(`Poll ${patientId}: progress=${progress} status=${status}`);

      if (progress) {
        setProgressStage((prev) => ({ ...prev, [patientId]: progress }));
      }
      if (status) {
        setJobStatus((prev) => ({ ...prev, [patientId]: status }));
      }
      setProgressPercent((prev) => ({ ...prev, [patientId]: getProgressPercent(progress) }));

      if (jobId) {
        setJobsByPatient((prev) => ({
          ...prev,
          [patientId]: {
            jobId,
            status: status,
            message: apiMessage,
            lastUpdated: Date.now(),
          },
        }));
      }

      // Stop on terminal statuses
      const s = (status || "").toUpperCase();
      if (s === "SUCCESS" || s === "STOPPED" || s === "FAILED" || s === "ERROR") {
        if (intervalRef.current[patientId]) {
          clearInterval(intervalRef.current[patientId]!);
          intervalRef.current[patientId] = null;
        }

        setProcessingPatients((prev) => ({ ...prev, [patientId]: false }));

        if (s === "SUCCESS") {
          setForms((prev) => ({ ...prev, [patientId]: true }));
          setMessage({ type: "success", text: `Claim completed for ${patientId}` });
          showToast("success", `Claim completed for ${patientId}!`);
        } else if (s === "STOPPED") {
          setMessage({ type: "warning", text: `Claim stopped for ${patientId}` });
          showToast("warning", `Claim stopped for ${patientId}!`);
        } else {
          setMessage({ type: "error", text: `Claim failed for ${patientId}` });
          showToast("error", `Claim failed for ${patientId}!`);
        }
      }
    } catch (err: any) {
      console.error("Polling error:", err);

      // Optionally: show toast on continuous errors (kept silent here)
      // Keep polling — or implement retry/backoff if desired
    }
  };

  const startPolling = (patientId: string) => {
    // clear existing
    if (intervalRef.current[patientId]) {
      clearInterval(intervalRef.current[patientId]!);
    }
    // immediate poll then interval
    pollProgress(patientId).catch(() => {});
    const id = window.setInterval(() => pollProgress(patientId), 1000);
    intervalRef.current[patientId] = id;
  };

  // Trigger claim start for patient
  const handleGenerateClaim = async (patientId: string) => {
    try {
      // set initial UI state for this patient
      setProcessingPatients((prev) => ({ ...prev, [patientId]: true }));
      setProgressStage((prev) => ({ ...prev, [patientId]: "INITIATED" }));
      setJobStatus((prev) => ({ ...prev, [patientId]: "RUNNING" }));
      setProgressPercent((prev) => ({ ...prev, [patientId]: getProgressPercent("INITIATED") }));

      showToast("info", `Starting claim for ${patientId}...`);
      setMessage({ type: "", text: "" });

      // call start endpoint (bedrock)
      const response = await axios.post(CLAIM_API, {
        path: "/bedrock",
        patientId,
      });

      const res = response.data || {};
      if (res.jobId) {
        setJobsByPatient((prev) => ({
          ...prev,
          [patientId]: {
            jobId: res.jobId,
            status: res.status,
            message: res.message,
            lastUpdated: Date.now(),
          },
        }));
      }

      // start polling for progress
      startPolling(patientId);
    } catch (err: any) {
      console.error("Claim start error:", err);
      setProcessingPatients((prev) => ({ ...prev, [patientId]: false }));
      showToast("error", "Failed to start claim");
      setMessage({ type: "error", text: `Failed to start claim for ${patientId}` });
    }
  };

  // View form
  const handleViewForm = async (patientId: string) => {
    try {
      setMessage({ type: "", text: "" });
      setFormData(null);

      const response = await axios.post(VIEW_FORM_API, {
        path: "/viewForm",
        patientId,
      });

      const d = response.data || {};
      // older code used pdfUrl; some APIs use url or data.url
      const pdfUrl = d.pdfUrl || d.url || d.data?.url;
      if (pdfUrl) {
        setFormData({ url: pdfUrl, patientId, formType: d.form_type || "Form" });
        setMessage({ type: "success", text: `Form found for ${patientId}` });
      } else {
        setMessage({ type: "warning", text: `Form not ready for ${patientId}` });
        showToast("warning", "Form not ready yet!");
      }
    } catch (err) {
      console.error("View form error:", err);
      setMessage({ type: "error", text: `Failed to load form for ${patientId}` });
      showToast("error", "Failed to open form");
    }
  };

  // filtered + pagination
  const filtered = data.filter((p) => {
    const s = searchTerm.trim().toLowerCase();
    if (!s) return true;
    return (
      (p.patient_id?.toString().toLowerCase() || "").includes(s) ||
      (p.patient_name?.toString().toLowerCase() || "").includes(s) ||
      (p.age?.toString().toLowerCase() || "").includes(s) ||
      (p.phone?.toString().toLowerCase() || "").includes(s)
    );
  });

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const startIndex = (currentPage - 1) * PAGE_SIZE;
  const endIndex = Math.min(startIndex + PAGE_SIZE, filtered.length);
  const paginated = filtered.slice(startIndex, endIndex);

  // stats
  const stats = useMemo(() => {
    const total = data.length;
    const withPhone = data.filter((p) => p.phone).length;
    const withDiagnosis = data.filter((p) => p.diagnosis).length;
    const ages = data.map((p) => Number(p.age)).filter((n) => !Number.isNaN(n));
    const avgAge = ages.length > 0 ? Math.round(ages.reduce((s, a) => s + a, 0) / ages.length) : 0;
    return { total, withPhone, withDiagnosis, avgAge };
  }, [data]);

  // message color classes
  const alertClasses =
    message.type === "success"
      ? "bg-emerald-50 text-emerald-800 border-emerald-200"
      : message.type === "error"
      ? "bg-rose-50 text-rose-800 border-rose-200"
      : message.type === "warning"
      ? "bg-amber-50 text-amber-800 border-amber-200"
      : "bg-slate-50 text-slate-700 border-slate-200";

  // cleanup on unmount
  useEffect(() => {
    return () => {
      Object.values(intervalRef.current).forEach((id) => {
        if (id) clearInterval(id);
      });
      intervalRef.current = {};
    };
  }, []);

  return (
    <div className="p-6 space-y-6">
      {/* Toast */}
      {toast.show && (
        <div
          className={`fixed top-5 right-5 px-4 py-2 rounded text-white shadow-lg ${
            toast.type === "success" ? "bg-green-600" : toast.type === "error" ? "bg-red-600" : "bg-blue-600"
          }`}
        >
          {toast.text}
        </div>
      )}

      {/* Header + stats */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="page-title text-2xl font-bold text-blue-900 flex items-center gap-2">
            <UsersIcon size={22} />
            Patients
          </h2>
          <p className="text-sm text-gray-500">View encounters, generate claims, and open AI-created forms for each patient.</p>
        </div>

        <div className="flex flex-wrap gap-3 text-xs">
          <div className="bg-white rounded-2xl shadow-sm border border-gray-100 px-3 py-2 min-w-[120px]">
            <div className="text-gray-400 uppercase tracking-wide">Total patients</div>
            <div className="text-lg font-semibold text-gray-900">{stats.total}</div>
          </div>
          <div className="bg-blue-50 rounded-2xl border border-blue-100 px-3 py-2 min-w-[120px]">
            <div className="text-[11px] text-blue-700 uppercase tracking-wide">With phone</div>
            <div className="text-lg font-semibold text-blue-700">{stats.withPhone}</div>
          </div>
          <div className="bg-emerald-50 rounded-2xl border border-emerald-100 px-3 py-2 min-w-[120px]">
            <div className="text-[11px] text-emerald-700 uppercase tracking-wide">With diagnosis</div>
            <div className="text-lg font-semibold text-emerald-700">{stats.withDiagnosis}</div>
          </div>
          <div className="bg-gray-50 rounded-2xl border border-gray-200 px-3 py-2 min-w-[120px]">
            <div className="text-[11px] text-gray-600 uppercase tracking-wide">Avg. age</div>
            <div className="text-lg font-semibold text-gray-800">{stats.avgAge || "-"}</div>
          </div>
        </div>
      </div>

      {/* Search bar */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4 flex flex-wrap items-center gap-4">
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center">
            <FileText size={18} />
          </div>
          <div className="space-y-1">
            <div className="text-xs font-semibold uppercase tracking-wide text-gray-500">Patient search</div>
            <p className="text-xs text-gray-400">Using sample patients + cloud claim APIs (no local backend).</p>
          </div>
        </div>

        <div className="ml-auto flex-1 min-w-[220px] max-w-xs">
          <div className="relative">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-gray-400" />
            <input
              type="text"
              placeholder="Search id, name, age, phone..."
              value={searchTerm}
              onChange={(e) => { setSearchTerm(e.target.value); setPage(1); }}
              className="w-full rounded-lg border border-gray-300 pl-9 pr-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>
        </div>
      </div>

      {/* Messages */}
      {message.text && (
        <div className={`border text-sm rounded-xl px-4 py-2 flex items-center gap-2 ${alertClasses}`}>
          <span className="h-2 w-2 rounded-full bg-current" />
          <span>{message.text}</span>
        </div>
      )}

      {/* Patients table */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-2">
              <FileText size={16} /> Patient encounters
            </h3>
            <p className="text-xs text-gray-500">Use AI agents to generate claims and view structured forms.</p>
          </div>
          <div className="text-xs text-gray-500">
            Showing <span className="font-semibold text-gray-800">{paginated.length}</span> of <span className="font-semibold text-gray-800">{filtered.length}</span> matching patients
          </div>
        </div>

        <div className="overflow-x-auto rounded-xl border border-gray-100">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-50 text-xs text-gray-500">
                <th className="px-4 py-2 text-left">Patient</th>
                <th className="px-4 py-2 text-left">Age</th>
                <th className="px-4 py-2 text-left">Diagnosis</th>
                <th className="px-4 py-2 text-left">Visit</th>
                <th className="px-4 py-2 text-left">Claim job</th>
                <th className="px-4 py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {paginated.length === 0 && (
                <tr>
                  <td colSpan={6} className="text-center py-6 text-gray-500 text-sm">No patient data loaded.</td>
                </tr>
              )}

              {paginated.map((p, i) => {
                const patientId = (p.patient_id || p.patient_name || p.name || `PAT-${startIndex + i + 1}`).toString();
                const busy = processingPatients[patientId] === true;
                const job = jobsByPatient[patientId];

                return (
                  <tr key={startIndex + i} className="hover:bg-slate-50/70 transition">
                    <td className="px-4 py-3">{p.patient_name || p.name || p.patient_id || "-"}</td>
                    <td className="px-4 py-3">{p.age ?? "-"}</td>
                    <td className="px-4 py-3">
                      {p.diagnosis ?? <span className="text-xs text-gray-400 italic">Not captured</span>}
                    </td>
                    <td className="px-4 py-3">{p.visit_date ?? p.date ?? "-"}</td>
                    <td className="px-4 py-3">
                      {progressStage[patientId] ? (
                        <div className="flex flex-col gap-0.5">
                          <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium bg-slate-100 text-slate-700">
                            <span className={`h-1.5 w-1.5 rounded-full ${jobStatus[patientId] ? "bg-sky-500" : "bg-slate-400"}`} />
                            {jobStatus[patientId] || progressStage[patientId]}
                          </span>
                          <div className="w-full bg-gray-200 rounded-full h-2 mt-1">
                            <div
                              className="bg-purple-600 h-2 rounded-full transition-all"
                              style={{ width: `${progressPercent[patientId] ?? 0}%` }}
                            />
                          </div>
                        </div>
                      ) : job ? (
                        <div className="text-[11px] text-gray-500">Job: {job.jobId}</div>
                      ) : (
                        <span className="text-xs text-gray-400">No job started</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex justify-end gap-2">
                        <button
                          onClick={() => handleGenerateClaim(patientId)}
                          disabled={busy}
                          className={`px-3 py-1.5 rounded-full text-xs font-medium text-white shadow-sm ${
                            busy ? "bg-gray-400 cursor-not-allowed" : "bg-blue-600 hover:bg-blue-700"
                          }`}
                        >
                          {busy ? "Processing…" : "Generate Claim"}
                        </button>
                        <button
                          onClick={() => handleViewForm(patientId)}
                          disabled={!forms[patientId]}
                          className={`px-3 py-1.5 rounded-full text-xs font-medium text-white shadow-sm ${
                            forms[patientId] ? "bg-emerald-600 hover:bg-emerald-700" : "bg-gray-500 cursor-not-allowed"
                          }`}
                        >
                          View Form
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        <div className="flex items-center justify-between mt-3 text-xs text-gray-500">
          <span>
            Showing <span className="font-semibold text-gray-800">{filtered.length === 0 ? 0 : startIndex + 1}-{endIndex}</span> of <span className="font-semibold text-gray-800">{filtered.length}</span> patients
          </span>
          <div className="flex items-center gap-2">
            <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={currentPage === 1} className="px-2.5 py-1 rounded-full border border-gray-300 bg-white hover:bg-gray-50 disabled:bg-gray-100 disabled:text-gray-400">Prev</button>
            <span>Page <span className="font-semibold text-gray-800">{currentPage}</span> of <span className="font-semibold text-gray-800">{totalPages}</span></span>
            <button onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={currentPage === totalPages} className="px-2.5 py-1 rounded-full border border-gray-300 bg-white hover:bg-gray-50 disabled:bg-gray-100 disabled:text-gray-400">Next</button>
          </div>
        </div>
      </div>

      {/* Modal for viewing form */}
      {formData && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-4xl h-[85vh] overflow-hidden relative flex flex-col">
            <div className="flex items-center justify-between px-4 py-3 border-b bg-gray-50">
              <div>
                <h3 className="font-semibold text-gray-900 text-sm">
                  Viewing {formData.formType || "Form"} — <span className="font-mono text-xs">{formData.patientId}</span>
                </h3>
                <p className="text-xs text-gray-500">Rendered directly from your claim generation pipeline.</p>
              </div>
              <div className="flex items-center gap-2">
                <a href={formData.url} target="_blank" rel="noreferrer" className="px-3 py-1.5 bg-blue-600 text-white rounded-full text-xs font-medium hover:bg-blue-700">Open in new tab</a>
                <button onClick={() => setFormData(null)} className="text-sm font-bold text-gray-500 hover:text-red-600">✕</button>
              </div>
            </div>
            <iframe title="Claim Form" src={formData.url} width="100%" height="100%" className="border-0 flex-1" />
          </div>
        </div>
      )}
    </div>
  );
};

export default Patients;

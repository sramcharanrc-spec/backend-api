// import React, { useEffect, useState } from "react";

// type SubmitResponse = {
//   claim_id: string;
//   status: string;
//   submission_id: string;
// };

// type SubmissionStatus = {
//   id: string;
//   claim_id: string;
//   status: string;
//   created_at: string;
//   raw_edi: string;
//   rejection_reason?: string | null;
// };

// const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

// const RcmDevPanel: React.FC = () => {
//   // existing states
//   const [loadingSubmit, setLoadingSubmit] = useState(false);
//   const [loadingStatus, setLoadingStatus] = useState(false);
//   const [loadingCustom, setLoadingCustom] = useState(false);
//   const [loadingFull, setLoadingFull] = useState(false);
//   const [fullResult, setFullResult] = useState<any | null>(null);

//   const [lastSubmission, setLastSubmission] = useState<SubmitResponse | null>(null);
//   const [statusResult, setStatusResult] = useState<SubmissionStatus | null>(null);
//   const [submissionIdInput, setSubmissionIdInput] = useState("");

//   const [error, setError] = useState<string | null>(null);
//   const [showEdi, setShowEdi] = useState(false);

//   // S3 integration states
//   const [s3Keys, setS3Keys] = useState<string[]>([]);
//   const [s3Prefix, setS3Prefix] = useState<string>("");
//   const [selectedS3Key, setSelectedS3Key] = useState<string>("");
//   const [s3Preview, setS3Preview] = useState<string | null>(null);
//   const [loadingS3List, setLoadingS3List] = useState(false);
//   const [loadingS3Submit, setLoadingS3Submit] = useState(false);

//   // Custom EDA as before
//   const [customEda, setCustomEda] = useState<string>(
//     JSON.stringify(
//       {
//         claim_id: "CLM-123",
//         patient: {
//           id: "PT-999",
//           name: "Test Patient",
//           dob: "1985-05-05",
//           member_id: "M999999",
//         },
//         provider: {
//           npi: "9999999999",
//           name: "Dr. Test",
//         },
//         payer: {
//           id: "TEST-PAYER-2",
//           name: "Demo Health Plan",
//         },
//         diagnosis_codes: ["R51"],
//         service_date: "2025-02-01",
//         place_of_service: "11",
//         procedure_lines: [{ cpt: "99214", modifier: "25", charge_amount: 200.0 }],
//       },
//       null,
//       2
//     )
//   );

//   // ----------------- S3: list on mount / when prefix changes -----------------
//   useEffect(() => {
//     const fetchKeys = async () => {
//       setLoadingS3List(true);
//       try {
//         const res = await fetch(`${API_BASE}/api/rcm/s3/list?prefix=${encodeURIComponent(s3Prefix)}`);
//         if (!res.ok) {
//           const txt = await res.text();
//           throw new Error(txt || `HTTP ${res.status}`);
//         }
//         const keys: string[] = await res.json();
//         setS3Keys(keys);
//         if (keys.length && !selectedS3Key) {
//           setSelectedS3Key(keys[0]);
//         }
//       } catch (err: any) {
//         console.error("S3 list error", err);
//         setError("Failed to list S3 EDA files: " + (err.message || err));
//       } finally {
//         setLoadingS3List(false);
//       }
//     };

//     // fetch only when prefix changes OR on mount (prefix initialized "")
//     fetchKeys();
//     // eslint-disable-next-line react-hooks/exhaustive-deps
//   }, [s3Prefix]);

//   // ----------------- core handlers (unchanged) -----------------
//   const handleRunFullSample = async () => {
//     setError(null);
//     setLoadingFull(true);
//     setFullResult(null);
//     try {
//       const res = await fetch(`${API_BASE}/api/rcm/run-full-sample`, {
//         method: "POST",
//       });
//       if (!res.ok) {
//         const text = await res.text();
//         throw new Error(text || `HTTP ${res.status}`);
//       }
//       const data = await res.json();
//       setFullResult(data);
//       if (data.submit_result?.submission_id) {
//         setSubmissionIdInput(data.submit_result.submission_id);
//       }
//     } catch (err: any) {
//       setError(err.message || "Failed to run full RCM test");
//     } finally {
//       setLoadingFull(false);
//     }
//   };

//   const handleSubmitSample = async () => {
//     setError(null);
//     setStatusResult(null);
//     setLoadingSubmit(true);
//     try {
//       const res = await fetch(`${API_BASE}/api/rcm/submit-sample`, {
//         method: "POST",
//       });
//       if (!res.ok) {
//         const text = await res.text();
//         throw new Error(text || `HTTP ${res.status}`);
//       }
//       const data: SubmitResponse = await res.json();
//       setLastSubmission(data);
//       setSubmissionIdInput(data.submission_id);
//     } catch (err: any) {
//       setError(err.message || "Failed to submit sample claim");
//     } finally {
//       setLoadingSubmit(false);
//     }
//   };

//   const handleSubmitCustomEda = async () => {
//     setError(null);
//     setStatusResult(null);
//     setLoadingCustom(true);
//     try {
//       let parsed;
//       try {
//         parsed = JSON.parse(customEda);
//       } catch (e) {
//         throw new Error("Custom EDA JSON is invalid. Please fix and try again.");
//       }

//       const res = await fetch(`${API_BASE}/api/rcm/submit-from-eda`, {
//         method: "POST",
//         headers: {
//           "Content-Type": "application/json",
//         },
//         body: JSON.stringify(parsed),
//       });

//       if (!res.ok) {
//         const text = await res.text();
//         throw new Error(text || `HTTP ${res.status}`);
//       }

//       const data: SubmitResponse = await res.json();
//       setLastSubmission(data);
//       setSubmissionIdInput(data.submission_id);
//     } catch (err: any) {
//       setError(err.message || "Failed to submit custom EDA claim");
//     } finally {
//       setLoadingCustom(false);
//     }
//   };

//   const handleCheckStatus = async () => {
//     if (!submissionIdInput.trim()) {
//       setError("Enter a submission ID first");
//       return;
//     }
//     setError(null);
//     setLoadingStatus(true);
//     setStatusResult(null);
//     try {
//       const res = await fetch(`${API_BASE}/api/rcm/submission/${submissionIdInput.trim()}`);
//       if (!res.ok) {
//         const text = await res.text();
//         throw new Error(text || `HTTP ${res.status}`);
//       }
//       const data: SubmissionStatus = await res.json();
//       setStatusResult(data);
//     } catch (err: any) {
//       setError(err.message || "Failed to fetch submission status");
//     } finally {
//       setLoadingStatus(false);
//     }
//   };

//   // ----------------- S3: preview and submit handlers -----------------
//   const handlePreviewS3 = async (key: string) => {
//     setS3Preview(null);
//     setError(null);
//     if (!key) {
//       setError("No S3 key selected");
//       return;
//     }
//     try {
//       const res = await fetch(`${API_BASE}/api/rcm/s3/get?key=${encodeURIComponent(key)}`);
//       if (!res.ok) {
//         const txt = await res.text();
//         throw new Error(txt || `HTTP ${res.status}`);
//       }
//       const data = await res.json();
//       // If content is JSON string, pretty-print
//       let content = data.content;
//       try {
//         const parsed = JSON.parse(content);
//         content = JSON.stringify(parsed, null, 2);
//       } catch {
//         // leave as-is
//       }
//       setS3Preview(content);
//     } catch (err: any) {
//       setError(err.message || "Failed to preview S3 file");
//     }
//   };

//   const handleSubmitFromS3 = async (key: string) => {
//     setError(null);
//     if (!key) {
//       setError("No S3 key selected");
//       return;
//     }
//     setLoadingS3Submit(true);
//     try {
//       const res = await fetch(`${API_BASE}/api/rcm/submit-from-s3?key=${encodeURIComponent(key)}`, {
//         method: "POST",
//       });
//       if (!res.ok) {
//         const text = await res.text();
//         throw new Error(text || `HTTP ${res.status}`);
//       }
//       const data: SubmitResponse = await res.json();
//       setLastSubmission(data);
//       setSubmissionIdInput(data.submission_id);
//     } catch (err: any) {
//       setError(err.message || "Failed to submit EDA from S3");
//     } finally {
//       setLoadingS3Submit(false);
//     }
//   };

//   // UI
//   return (
//     <div className="max-w-5xl mx-auto mt-4 p-4 rounded-xl border border-gray-200 shadow-sm bg-white">
//       <h2 className="text-lg font-semibold mb-2">RCM Dev Panel (EDA → Claim → 837 → Mock Clearinghouse)</h2>
//       <p className="text-sm text-gray-600 mb-4">Test the /api/rcm backend with sample data, S3 EDA files, or your own EDA JSON.</p>

//       {/* TOP: Sample submit + status */}
//       <div className="mb-6 border-b border-gray-200 pb-4">
//         <div className="mb-3 flex flex-wrap items-center gap-3">
//           <button
//             onClick={handleSubmitSample}
//             disabled={loadingSubmit}
//             className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium disabled:opacity-60"
//           >
//             {loadingSubmit ? "Submitting sample claim..." : "Submit Sample Claim"}
//           </button>

//           <button
//             onClick={handleRunFullSample}
//             disabled={loadingFull}
//             className="px-4 py-2 rounded-lg bg-orange-600 text-white text-sm font-medium disabled:opacity-60"
//           >
//             {loadingFull ? "Running full sample..." : "Run Full RCM Test (Sample)"}
//           </button>

//           {lastSubmission && (
//             <div className="text-xs text-gray-700 space-y-0.5">
//               <div>
//                 Last claim: <span className="font-mono">{lastSubmission.claim_id}</span>
//               </div>
//               <div>
//                 Last status: <span className="font-mono">{lastSubmission.status}</span>
//               </div>
//               <div>
//                 Last submission_id: <span className="font-mono">{lastSubmission.submission_id}</span>
//               </div>
//             </div>
//           )}
//         </div>

//         {/* Submission ID + Status */}
//         <div className="mb-3">
//           <label className="block text-sm font-medium mb-1">Submission ID</label>
//           <input
//             type="text"
//             value={submissionIdInput}
//             onChange={(e) => setSubmissionIdInput(e.target.value)}
//             placeholder="Auto-filled from last submit, or paste manually"
//             className="w-full max-w-xl px-3 py-2 border rounded-lg text-sm"
//           />
//         </div>

//         <button
//           onClick={handleCheckStatus}
//           disabled={loadingStatus}
//           className="px-4 py-2 rounded-lg bg-green-600 text-white text-sm font-medium disabled:opacity-60"
//         >
//           {loadingStatus ? "Checking status..." : "Check Submission Status"}
//         </button>
//       </div>

//       {/* S3 EDA picker */}
//       <div className="mb-6">
//         <h3 className="text-md font-semibold mb-2">Use EDA from S3</h3>

//         <div className="mb-2 flex items-center gap-2">
//           <input
//             value={s3Prefix}
//             onChange={(e) => setS3Prefix(e.target.value)}
//             placeholder="Optional prefix/folder (e.g. cms1500/2025-11-)"
//             className="px-2 py-1 border rounded text-sm"
//           />
//           <button
//             onClick={async () => {
//               setLoadingS3List(true);
//               setError(null);
//               try {
//                 const res = await fetch(`${API_BASE}/api/rcm/s3/list?prefix=${encodeURIComponent(s3Prefix)}`);
//                 if (!res.ok) {
//                   const txt = await res.text();
//                   throw new Error(txt || `HTTP ${res.status}`);
//                 }
//                 const keys = await res.json();
//                 setS3Keys(keys);
//                 if (keys.length) setSelectedS3Key(keys[0]);
//               } catch (err: any) {
//                 setError(err.message || "Failed to list S3 files");
//               } finally {
//                 setLoadingS3List(false);
//               }
//             }}
//             className="px-3 py-1 bg-gray-200 rounded text-sm"
//           >
//             Refresh
//           </button>
//         </div>

//         <div className="mb-2 flex items-center gap-2">
//           <select
//             value={selectedS3Key}
//             onChange={(e) => setSelectedS3Key(e.target.value)}
//             className="w-full max-w-2xl px-2 py-1 border rounded text-sm"
//           >
//             <option value="">-- select S3 file --</option>
//             {s3Keys.map((k) => (
//               <option key={k} value={k}>
//                 {k}
//               </option>
//             ))}
//           </select>

//           <button
//             onClick={() => selectedS3Key && handlePreviewS3(selectedS3Key)}
//             disabled={!selectedS3Key}
//             className="px-3 py-1 rounded bg-indigo-600 text-white text-sm disabled:opacity-60"
//           >
//             Preview
//           </button>

//           <button
//             onClick={() => selectedS3Key && handleSubmitFromS3(selectedS3Key)}
//             disabled={!selectedS3Key || loadingS3Submit}
//             className="px-3 py-1 rounded bg-rose-600 text-white text-sm disabled:opacity-60"
//           >
//             {loadingS3Submit ? "Submitting..." : "Submit From S3"}
//           </button>
//         </div>

//         {loadingS3List && <div className="text-sm text-gray-500">Loading S3 files…</div>}

//         {s3Preview && (
//           <pre className="mt-2 p-3 bg-gray-50 text-xs font-mono rounded max-h-72 overflow-auto">
//             {s3Preview}
//           </pre>
//         )}
//       </div>

//       {/* Custom EDA submit */}
//       <div className="mb-6">
//         <h3 className="text-md font-semibold mb-2">Custom EDA JSON</h3>
//         <p className="text-xs text-gray-500 mb-2">
//           Paste EDA-style JSON here (must match backend expectations: patient, provider, payer, diagnosis_codes,
//           service_date, procedure_lines...).
//         </p>
//         <textarea
//           value={customEda}
//           onChange={(e) => setCustomEda(e.target.value)}
//           rows={12}
//           className="w-full font-mono text-xs px-3 py-2 border rounded-lg bg-gray-50"
//         />

//         <div className="mt-3">
//           <button
//             onClick={handleSubmitCustomEda}
//             disabled={loadingCustom}
//             className="px-4 py-2 rounded-lg bg-purple-600 text-white text-sm font-medium disabled:opacity-60"
//           >
//             {loadingCustom ? "Submitting custom EDA..." : "Submit Custom EDA"}
//           </button>
//         </div>
//       </div>

//       {/* Error */}
//       {error && <div className="mb-4 text-sm text-red-600">{error}</div>}

//       {/* Show fullResult if present */}
//       {fullResult && (
//         <div className="mb-4 p-3 rounded-lg bg-gray-50 border">
//           <h4 className="font-medium mb-2">Full Run Result</h4>
//           <pre className="text-xs font-mono max-h-60 overflow-auto">{JSON.stringify(fullResult, null, 2)}</pre>
//         </div>
//       )}

//       {/* Status result */}
//       {statusResult && (
//         <div className="mt-4 space-y-2 text-sm border-t border-gray-200 pt-4">
//           <div>
//             <span className="font-medium">Submission ID:</span> <span className="font-mono">{statusResult.id}</span>
//           </div>
//           <div>
//             <span className="font-medium">Claim ID:</span> <span className="font-mono">{statusResult.claim_id}</span>
//           </div>
//           <div>
//             <span className="font-medium">Status:</span>{" "}
//             <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-700">
//               {statusResult.status}
//             </span>
//           </div>
//           <div>
//             <span className="font-medium">Created at:</span> {new Date(statusResult.created_at).toLocaleString()}
//           </div>

//           <div className="mt-3">
//             <button onClick={() => setShowEdi((v) => !v)} className="text-xs text-blue-600 hover:underline">
//               {showEdi ? "Hide raw EDI 837" : "Show raw EDI 837"}
//             </button>
//             {showEdi && (
//               <pre className="mt-2 p-3 bg-gray-900 text-green-100 text-xs rounded-lg overflow-x-auto whitespace-pre">
//                 {statusResult.raw_edi}
//               </pre>
//             )}
//           </div>
//         </div>
//       )}
//     </div>
//   );
// };

// export default RcmDevPanel;


// import React, { useState } from "react";

// type SubmitResponse = {
//   claim_id: string;
//   status: string;
//   submission_id: string;
// };

// type SubmissionStatus = {
//   id: string;
//   claim_id: string;
//   status: string;
//   created_at: string;
//   raw_edi: string;
//   rejection_reason?: string | null;
// };

// const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

// const RcmDevPanel: React.FC = () => {
//   const [loadingSubmit, setLoadingSubmit] = useState(false);
//   const [loadingStatus, setLoadingStatus] = useState(false);
//   const [loadingCustom, setLoadingCustom] = useState(false);
//   const [loadingFull, setLoadingFull] = useState(false);
//   const [fullResult, setFullResult] = useState<any | null>(null);

//   const [lastSubmission, setLastSubmission] = useState<SubmitResponse | null>(null);
//   const [statusResult, setStatusResult] = useState<SubmissionStatus | null>(null);
//   const [submissionIdInput, setSubmissionIdInput] = useState("");

//   const [error, setError] = useState<string | null>(null);
//   const [showEdi, setShowEdi] = useState(false);

//   // ---------- Handler moved above JSX / return ----------
//   const handleRunFullSample = async () => {
//     setError(null);
//     setLoadingFull(true);
//     setFullResult(null);
//     try {
//       const res = await fetch(`${API_BASE}/api/rcm/run-full-sample`, {
//         method: "POST",
//       });
//       if (!res.ok) {
//         const text = await res.text();
//         throw new Error(text || `HTTP ${res.status}`);
//       }
//       const data = await res.json();
//       setFullResult(data);
//       if (data.submit_result?.submission_id) {
//         setSubmissionIdInput(data.submit_result.submission_id);
//       }
//     } catch (err: any) {
//       setError(err.message || "Failed to run full RCM test");
//     } finally {
//       setLoadingFull(false);
//     }
//   };

//   const [customEda, setCustomEda] = useState<string>(
//     JSON.stringify(
//       {
//         claim_id: "CLM-123",
//         patient: {
//           id: "PT-999",
//           name: "Test Patient",
//           dob: "1985-05-05",
//           member_id: "M999999",
//         },
//         provider: {
//           npi: "9999999999",
//           name: "Dr. Test",
//         },
//         payer: {
//           id: "TEST-PAYER-2",
//           name: "Demo Health Plan",
//         },
//         diagnosis_codes: ["R51"],
//         service_date: "2025-02-01",
//         place_of_service: "11",
//         procedure_lines: [{ cpt: "99214", modifier: "25", charge_amount: 200.0 }],
//       },
//       null,
//       2
//     )
//   );

//   const handleSubmitSample = async () => {
//     setError(null);
//     setStatusResult(null);
//     setLoadingSubmit(true);
//     try {
//       const res = await fetch(`${API_BASE}/api/rcm/submit-sample`, {
//         method: "POST",
//       });
//       if (!res.ok) {
//         const text = await res.text();
//         throw new Error(text || `HTTP ${res.status}`);
//       }
//       const data: SubmitResponse = await res.json();
//       setLastSubmission(data);
//       setSubmissionIdInput(data.submission_id);
//     } catch (err: any) {
//       setError(err.message || "Failed to submit sample claim");
//     } finally {
//       setLoadingSubmit(false);
//     }
//   };

//   const handleSubmitCustomEda = async () => {
//     setError(null);
//     setStatusResult(null);
//     setLoadingCustom(true);
//     try {
//       let parsed;
//       try {
//         parsed = JSON.parse(customEda);
//       } catch (e) {
//         throw new Error("Custom EDA JSON is invalid. Please fix and try again.");
//       }

//       const res = await fetch(`${API_BASE}/api/rcm/submit-from-eda`, {
//         method: "POST",
//         headers: {
//           "Content-Type": "application/json",
//         },
//         body: JSON.stringify(parsed),
//       });

//       if (!res.ok) {
//         const text = await res.text();
//         throw new Error(text || `HTTP ${res.status}`);
//       }

//       const data: SubmitResponse = await res.json();
//       setLastSubmission(data);
//       setSubmissionIdInput(data.submission_id);
//     } catch (err: any) {
//       setError(err.message || "Failed to submit custom EDA claim");
//     } finally {
//       setLoadingCustom(false);
//     }
//   };

//   const handleCheckStatus = async () => {
//     if (!submissionIdInput.trim()) {
//       setError("Enter a submission ID first");
//       return;
//     }
//     setError(null);
//     setLoadingStatus(true);
//     setStatusResult(null);
//     try {
//       const res = await fetch(`${API_BASE}/api/rcm/submission/${submissionIdInput.trim()}`);
//       if (!res.ok) {
//         const text = await res.text();
//         throw new Error(text || `HTTP ${res.status}`);
//       }
//       const data: SubmissionStatus = await res.json();
//       setStatusResult(data);
//     } catch (err: any) {
//       setError(err.message || "Failed to fetch submission status");
//     } finally {
//       setLoadingStatus(false);
//     }
//   };

//   return (
//     <div className="max-w-5xl mx-auto mt-4 p-4 rounded-xl border border-gray-200 shadow-sm bg-white">
//       <h2 className="text-lg font-semibold mb-2">RCM Dev Panel (EDA → Claim → 837 → Mock Clearinghouse)</h2>
//       <p className="text-sm text-gray-600 mb-4">Test the /api/rcm backend with sample data or your own EDA JSON.</p>

//       {/* TOP: Sample submit + status */}
//       <div className="mb-6 border-b border-gray-200 pb-4">
//         <div className="mb-3 flex flex-wrap items-center gap-3">
//           <button
//             onClick={handleSubmitSample}
//             disabled={loadingSubmit}
//             className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium disabled:opacity-60"
//           >
//             {loadingSubmit ? "Submitting sample claim..." : "Submit Sample Claim"}
//           </button>

//           {/* Run full sample button (moved into JSX) */}
//           <button
//             onClick={handleRunFullSample}
//             disabled={loadingFull}
//             className="px-4 py-2 rounded-lg bg-orange-600 text-white text-sm font-medium disabled:opacity-60"
//           >
//             {loadingFull ? "Running full sample..." : "Run Full RCM Test (Sample)"}
//           </button>

//           {lastSubmission && (
//             <div className="text-xs text-gray-700 space-y-0.5">
//               <div>
//                 Last claim: <span className="font-mono">{lastSubmission.claim_id}</span>
//               </div>
//               <div>
//                 Last status: <span className="font-mono">{lastSubmission.status}</span>
//               </div>
//               <div>
//                 Last submission_id: <span className="font-mono">{lastSubmission.submission_id}</span>
//               </div>
//             </div>
//           )}
//         </div>

//         {/* Submission ID + Status */}
//         <div className="mb-3">
//           <label className="block text-sm font-medium mb-1">Submission ID</label>
//           <input
//             type="text"
//             value={submissionIdInput}
//             onChange={(e) => setSubmissionIdInput(e.target.value)}
//             placeholder="Auto-filled from last submit, or paste manually"
//             className="w-full max-w-xl px-3 py-2 border rounded-lg text-sm"
//           />
//         </div>

//         <button
//           onClick={handleCheckStatus}
//           disabled={loadingStatus}
//           className="px-4 py-2 rounded-lg bg-green-600 text-white text-sm font-medium disabled:opacity-60"
//         >
//           {loadingStatus ? "Checking status..." : "Check Submission Status"}
//         </button>
//       </div>

//       {/* Show fullResult if present */}
//       {fullResult && (
//         <div className="mb-4 p-3 rounded-lg bg-gray-50 border">
//           <h4 className="font-medium mb-2">Full Run Result</h4>
//           <pre className="text-xs font-mono max-h-60 overflow-auto">{JSON.stringify(fullResult, null, 2)}</pre>
//         </div>
//       )}

//       {/* Custom EDA submit */}
//       <div className="mb-6">
//         <h3 className="text-md font-semibold mb-2">Custom EDA JSON</h3>
//         <p className="text-xs text-gray-500 mb-2">
//           Paste EDA-style JSON here (must match backend expectations: patient, provider, payer, diagnosis_codes, service_date,
//           procedure_lines...).
//         </p>
//         <textarea
//           value={customEda}
//           onChange={(e) => setCustomEda(e.target.value)}
//           rows={12}
//           className="w-full font-mono text-xs px-3 py-2 border rounded-lg bg-gray-50"
//         />

//         <div className="mt-3">
//           <button
//             onClick={handleSubmitCustomEda}
//             disabled={loadingCustom}
//             className="px-4 py-2 rounded-lg bg-purple-600 text-white text-sm font-medium disabled:opacity-60"
//           >
//             {loadingCustom ? "Submitting custom EDA..." : "Submit Custom EDA"}
//           </button>
//         </div>
//       </div>

//       {/* Error */}
//       {error && <div className="mb-4 text-sm text-red-600">{error}</div>}

//       {/* Status result */}
//       {statusResult && (
//         <div className="mt-4 space-y-2 text-sm border-t border-gray-200 pt-4">
//           <div>
//             <span className="font-medium">Submission ID:</span> <span className="font-mono">{statusResult.id}</span>
//           </div>
//           <div>
//             <span className="font-medium">Claim ID:</span> <span className="font-mono">{statusResult.claim_id}</span>
//           </div>
//           <div>
//             <span className="font-medium">Status:</span>{" "}
//             <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-700">
//               {statusResult.status}
//             </span>
//           </div>
//           <div>
//             <span className="font-medium">Created at:</span> {new Date(statusResult.created_at).toLocaleString()}
//           </div>

//           <div className="mt-3">
//             <button onClick={() => setShowEdi((v) => !v)} className="text-xs text-blue-600 hover:underline">
//               {showEdi ? "Hide raw EDI 837" : "Show raw EDI 837"}
//             </button>
//             {showEdi && (
//               <pre className="mt-2 p-3 bg-gray-900 text-green-100 text-xs rounded-lg overflow-x-auto whitespace-pre">
//                 {statusResult.raw_edi}
//               </pre>
//             )}
//           </div>
//         </div>
//       )}
//     </div>
//   );
// };

// export default RcmDevPanel;



import React, { useState } from "react";

type SubmitResponse = {
  claim_id: string;
  status: string;
  submission_id: string;
};

type SubmissionStatus = {
  id: string;
  claim_id: string;
  status: string;
  created_at?: string;
  raw_edi?: string;
  // backend uses 'denial_reason' (some old code used 'rejection_reason')
  denial_reason?: string | null;
  rejection_reason?: string | null;
};

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const RcmDevPanel: React.FC = () => {
  const [loadingSubmit, setLoadingSubmit] = useState(false);
  const [loadingStatus, setLoadingStatus] = useState(false);
  const [loadingCustom, setLoadingCustom] = useState(false);
  const [loadingFull, setLoadingFull] = useState(false);
  const [fullResult, setFullResult] = useState<any | null>(null);

  const [lastSubmission, setLastSubmission] = useState<SubmitResponse | null>(null);
  const [statusResult, setStatusResult] = useState<SubmissionStatus | null>(null);
  const [submissionIdInput, setSubmissionIdInput] = useState("");

  const [error, setError] = useState<string | null>(null);
  const [showEdi, setShowEdi] = useState(false);

  // ---------- Handlers ----------
  const handleRunFullSample = async () => {
    setError(null);
    setLoadingFull(true);
    setFullResult(null);
    try {
      const res = await fetch(`${API_BASE}/api/rcm/run-full-sample`, {
        method: "POST",
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `HTTP ${res.status}`);
      }
      const data = await res.json();
      setFullResult(data);
      if (data.submit_result?.submission_id) {
        setSubmissionIdInput(data.submit_result.submission_id);
      }
    } catch (err: any) {
      setError(err.message || "Failed to run full RCM test");
    } finally {
      setLoadingFull(false);
    }
  };

  const [customEda, setCustomEda] = useState<string>(
    JSON.stringify(
      {
        claim_id: "CLM-123",
        patient: {
          id: "PT-999",
          name: "Test Patient",
          dob: "1985-05-05",
          member_id: "M999999",
        },
        provider: {
          npi: "9999999999",
          name: "Dr. Test",
        },
        payer: {
          id: "TEST-PAYER-2",
          name: "Demo Health Plan",
        },
        diagnosis_codes: ["R51"],
        service_date: "2025-02-01",
        place_of_service: "11",
        procedure_lines: [{ cpt: "99214", modifier: "25", charge_amount: 200.0 }],
      },
      null,
      2
    )
  );

  const handleSubmitSample = async () => {
    setError(null);
    setStatusResult(null);
    setLoadingSubmit(true);
    try {
      const res = await fetch(`${API_BASE}/api/rcm/submit-sample`, {
        method: "POST",
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `HTTP ${res.status}`);
      }
      const data: SubmitResponse = await res.json();
      setLastSubmission(data);
      setSubmissionIdInput(data.submission_id);
    } catch (err: any) {
      setError(err.message || "Failed to submit sample claim");
    } finally {
      setLoadingSubmit(false);
    }
  };

  const handleSubmitCustomEda = async () => {
    setError(null);
    setStatusResult(null);
    setLoadingCustom(true);
    try {
      let parsed;
      try {
        parsed = JSON.parse(customEda);
      } catch (e) {
        throw new Error("Custom EDA JSON is invalid. Please fix and try again.");
      }

      const res = await fetch(`${API_BASE}/api/rcm/submit-from-eda`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(parsed),
      });

      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `HTTP ${res.status}`);
      }

      const data: SubmitResponse = await res.json();
      setLastSubmission(data);
      setSubmissionIdInput(data.submission_id);
    } catch (err: any) {
      setError(err.message || "Failed to submit custom EDA claim");
    } finally {
      setLoadingCustom(false);
    }
  };

  const handleCheckStatus = async () => {
    if (!submissionIdInput.trim()) {
      setError("Enter a submission ID first");
      return;
    }
    setError(null);
    setLoadingStatus(true);
    setStatusResult(null);
    try {
      const res = await fetch(`${API_BASE}/api/rcm/submission/${submissionIdInput.trim()}`);
      if (!res.ok) {
        // try to show helpful server message
        const text = await res.text();
        throw new Error(text || `HTTP ${res.status}`);
      }
      const data: SubmissionStatus = await res.json();
      // normalize older field name if backend uses 'rejection_reason'
      if ((data as any).rejection_reason && !(data as any).denial_reason) {
        (data as any).denial_reason = (data as any).rejection_reason;
      }
      setStatusResult(data);
    } catch (err: any) {
      setError(err.message || "Failed to fetch submission status");
    } finally {
      setLoadingStatus(false);
    }
  };

  // ---------- JSX ----------
  return (
    <div className="max-w-5xl mx-auto mt-4 p-4 rounded-xl border border-gray-200 shadow-sm bg-white">
      <h2 className="text-lg font-semibold mb-2">RCM Dev Panel (EDA → Claim → 837 → Mock Clearinghouse)</h2>
      <p className="text-sm text-gray-600 mb-4">Test the /api/rcm backend with sample data or your own EDA JSON.</p>

      {/* TOP: Sample submit + status */}
      <div className="mb-6 border-b border-gray-200 pb-4">
        <div className="mb-3 flex flex-wrap items-center gap-3">
          <button
            onClick={handleSubmitSample}
            disabled={loadingSubmit}
            className="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium disabled:opacity-60"
          >
            {loadingSubmit ? "Submitting sample claim..." : "Submit Sample Claim"}
          </button>

          <button
            onClick={handleRunFullSample}
            disabled={loadingFull}
            className="px-4 py-2 rounded-lg bg-orange-600 text-white text-sm font-medium disabled:opacity-60"
          >
            {loadingFull ? "Running full sample..." : "Run Full RCM Test (Sample)"}
          </button>

          {lastSubmission && (
            <div className="text-xs text-gray-700 space-y-0.5">
              <div>
                Last claim: <span className="font-mono">{lastSubmission.claim_id}</span>
              </div>
              <div>
                Last status: <span className="font-mono">{lastSubmission.status}</span>
              </div>
              <div>
                Last submission_id: <span className="font-mono">{lastSubmission.submission_id}</span>
              </div>
            </div>
          )}
        </div>

        {/* Submission ID + Status */}
        <div className="mb-3">
          <label className="block text-sm font-medium mb-1">Submission ID</label>
          <input
            type="text"
            value={submissionIdInput}
            onChange={(e) => setSubmissionIdInput(e.target.value)}
            placeholder="Auto-filled from last submit, or paste manually"
            className="w-full max-w-xl px-3 py-2 border rounded-lg text-sm"
          />
        </div>

        <button
          onClick={handleCheckStatus}
          disabled={loadingStatus}
          className="px-4 py-2 rounded-lg bg-green-600 text-white text-sm font-medium disabled:opacity-60"
        >
          {loadingStatus ? "Checking status..." : "Check Submission Status"}
        </button>
      </div>

      {/* Show fullResult if present */}
      {fullResult && (
        <div className="mb-4 p-3 rounded-lg bg-gray-50 border">
          <h4 className="font-medium mb-2">Full Run Result</h4>
          <pre className="text-xs font-mono max-h-60 overflow-auto">{JSON.stringify(fullResult, null, 2)}</pre>
        </div>
      )}

      {/* Custom EDA submit */}
      <div className="mb-6">
        <h3 className="text-md font-semibold mb-2">Custom EDA JSON</h3>
        <p className="text-xs text-gray-500 mb-2">
          Paste EDA-style JSON here (must match backend expectations: patient, provider, payer, diagnosis_codes, service_date,
          procedure_lines...).
        </p>
        <textarea
          value={customEda}
          onChange={(e) => setCustomEda(e.target.value)}
          rows={12}
          className="w-full font-mono text-xs px-3 py-2 border rounded-lg bg-gray-50"
        />

        <div className="mt-3">
          <button
            onClick={handleSubmitCustomEda}
            disabled={loadingCustom}
            className="px-4 py-2 rounded-lg bg-purple-600 text-white text-sm font-medium disabled:opacity-60"
          >
            {loadingCustom ? "Submitting custom EDA..." : "Submit Custom EDA"}
          </button>
        </div>
      </div>

      {/* Error */}
      {error && <div className="mb-4 text-sm text-red-600">{error}</div>}

      {/* Status result */}
      {statusResult && (
        <div className="mt-4 space-y-2 text-sm border-t border-gray-200 pt-4">
          <div>
            <span className="font-medium">Submission ID:</span> <span className="font-mono">{statusResult.id}</span>
          </div>
          <div>
            <span className="font-medium">Claim ID:</span> <span className="font-mono">{statusResult.claim_id}</span>
          </div>
          <div>
            <span className="font-medium">Status:</span>{" "}
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-700">
              {statusResult.status}
            </span>
          </div>
          <div>
            <span className="font-medium">Created at:</span>{" "}
            {statusResult.created_at ? new Date(statusResult.created_at).toLocaleString() : "—"}
          </div>

          {/** show denial_reason if present */}
          {(statusResult.denial_reason || statusResult.rejection_reason) && (
            <div>
              <span className="font-medium text-red-600">Denial reason:</span>{" "}
              <span className="font-mono text-xs text-red-700">
                {statusResult.denial_reason ?? statusResult.rejection_reason}
              </span>
            </div>
          )}

          <div className="mt-3">
            <button onClick={() => setShowEdi((v) => !v)} className="text-xs text-blue-600 hover:underline">
              {showEdi ? "Hide raw EDI 837" : "Show raw EDI 837"}
            </button>
            {showEdi && (
              <pre className="mt-2 p-3 bg-gray-900 text-green-100 text-xs rounded-lg overflow-x-auto whitespace-pre">
                {statusResult.raw_edi ?? "No raw EDI available"}
              </pre>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default RcmDevPanel;

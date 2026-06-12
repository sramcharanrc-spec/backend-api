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

// import React, { useCallback, useEffect, useState } from "react";

// const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";



// type Status = {
//   id: string;
//   claim_id?: string;
//   status: string;
//   denial_reason?: string | null;
//   raw_edi?: string | null;
//   created_at?: string;
// };

// const Spinner = () => (
//   <div className="flex items-center gap-2 text-sm text-gray-600 mt-2">
//     <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
//     Waiting for clearinghouse ACK (277CA)...
//   </div>
// );


// const progressSteps = ["SUBMITTED", "ACCEPTED", "PAID"];

// const progressIndex = (status?: string) => {
//   if (!status) return 0;
//   if (status === "DENIED") return 2;
//   return progressSteps.indexOf(status);
// };

// {status?.status === "SUBMITTED" && <Spinner />}

// const Timeline = ({ status }: { status?: string }) => {
//   const steps = [
//     { label: "Claim Submitted (837)", key: "SUBMITTED" },
//     { label: "Clearinghouse ACK (277CA)", key: "ACCEPTED" },
//     { label: "AI Decision", key: "AI" },
//     { label: "Payment Posted (835)", key: "PAID" },
//   ];

//   const activeIndex =
//     status === "DENIED" ? 2 : steps.findIndex(s => s.key === status);

//   return (
//     <div className="mt-4 space-y-2">
//       {steps.map((s, i) => (
//         <div key={i} className="flex items-center gap-2 text-sm">
//           <div
//             className={`w-3 h-3 rounded-full ${
//               i <= activeIndex ? "bg-green-500" : "bg-gray-300"
//             }`}
//           />
//           <span className={i <= activeIndex ? "font-medium" : "text-gray-500"}>
//             {s.label}
//           </span>
//         </div>
//       ))}
//     </div>
//   );
// };


// const ProgressBar = ({ status }: { status?: string }) => {
//   const step = progressIndex(status);

//   return (
//     <div className="mt-4">
//       <div className="flex items-center justify-between text-xs mb-1">
//         <span>Submitted</span>
//         <span>Accepted</span>
//         <span>{status === "DENIED" ? "Denied" : "Paid"}</span>
//       </div>

//       <div className="relative h-2 bg-gray-200 rounded-full overflow-hidden">
//         <div
//           className={`absolute h-full transition-all duration-700 ${
//             status === "DENIED" ? "bg-red-500" : "bg-green-500"
//           }`}
//           style={{ width: `${(step + 1) * 33.33}%` }}
//         />
//       </div>
//     </div>
//   );
// };


// const statusColor = (status: string) => {
//   switch (status) {
//     case "SUBMITTED":
//       return "bg-blue-100 text-blue-700";
//     case "ACCEPTED":
//       return "bg-green-100 text-green-700";
//     case "DENIED":
//       return "bg-red-100 text-red-700";
//     case "PAID":
//       return "bg-emerald-100 text-emerald-700";
//     default:
//       return "bg-gray-100 text-gray-700";
//   }
// };

// const RcmDevPanel: React.FC = () => {
//   const [bucket, setBucket] = useState("healthcare-edi-output");

//   // ✅ MUST be a FILE, not folder
//   const [key, setKey] = useState(
//     "claims/P001/02a57ff6-89cb-4fae-bfd7-e29fdf45fcea.json"
//   );

//   const [directJson, setDirectJson] = useState("{}");
//   const [submissionId, setSubmissionId] = useState("");
//   const [status, setStatus] = useState<Status | null>(null);
//   const [analytics, setAnalytics] = useState<any>(null);

//   const [loading, setLoading] = useState(false);
//   const [error, setError] = useState<string | null>(null);
//   const [showEdi, setShowEdi] = useState(false);

//   // -------------------------------
//   // FETCH STATUS (memoized)
//   // -------------------------------
//   const fetchStatus = useCallback(async () => {
//     if (!submissionId) return;
//     try {
//       const res = await fetch(`${API_BASE}/api/rcm/status/${submissionId}`);
//       if (res.ok) setStatus(await res.json());
//     } catch {
//       /* silent refresh */
//     }
//   }, [submissionId]);

// useEffect(() => {
//   const saved = localStorage.getItem("last_submission_id");
//   if (saved) {
//     setSubmissionId(saved);
//   }
// }, []);
         
//   // -------------------------------
//   // AUTO REFRESH STATUS
//   // -------------------------------
//   useEffect(() => {
//     if (!submissionId) return;
//     fetchStatus();
//     const interval = setInterval(fetchStatus, 5000);
//     return () => clearInterval(interval);
//   }, [submissionId, fetchStatus]);

//   // -------------------------------
//   // SUBMIT FROM S3
//   // -------------------------------
//   const submitFromS3 = async () => {
//   setLoading(true);
//   setError(null);

//   try {
//     const res = await fetch(`${API_BASE}/api/rcm/submit-from-s3`, {
//       method: "POST",
//       headers: { "Content-Type": "application/json" },
//       body: JSON.stringify({ bucket, key }),
//     });

//     const data = await res.json();
//     if (!res.ok) throw new Error(data.error || "Submit failed");

//     setSubmissionId(data.submission_id);
//     localStorage.setItem("last_submission_id", data.submission_id); // ✅ ADD
//   } catch (e: any) {
//     setError(e.message);
//   } finally {
//     setLoading(false);
//   }
// };


//   // -------------------------------
//   // DIRECT JSON SUBMIT
//   // -------------------------------
//   const submitDirect = async () => {
//     setError(null);
//     setLoading(true);

//     try {
//       const parsed = JSON.parse(directJson);
//       const res = await fetch(`${API_BASE}/api/rcm/submit`, {
//         method: "POST",
//         headers: { "Content-Type": "application/json" },
//         body: JSON.stringify(parsed),
//       });

//       const data = await res.json();
//       if (!res.ok) throw new Error("Direct submit failed");

//       setSubmissionId(data.submission_id);
//       localStorage.setItem("last_submission_id", data.submission_id);

//       setStatus(null);
//     } catch {
//       setError("Invalid JSON or submit error");
//     } finally {
//       setLoading(false);
//     }
//   };

//   // -------------------------------
//   // SIMULATORS
//   // -------------------------------
//   const sendAck = async () => {
//     await fetch(`${API_BASE}/api/rcm/ack`, {
//       method: "POST",
//       headers: { "Content-Type": "application/json" },
//       body: JSON.stringify({
//         submission_id: submissionId,
//         status: "ACCEPTED",
//       }),
//     });
//     fetchStatus();
//   };

//   const sendDenial = async () => {
//     await fetch(`${API_BASE}/api/rcm/denial`, {
//       method: "POST",
//       headers: { "Content-Type": "application/json" },
//       body: JSON.stringify({
//         submission_id: submissionId,
//         denial_code: "CO-50",
//         message: "Non-covered service",
//       }),
//     });
//     fetchStatus();
//   };

//   const sendPayment = async () => {
//     await fetch(`${API_BASE}/api/rcm/payment`, {
//       method: "POST",
//       headers: { "Content-Type": "application/json" },
//       body: JSON.stringify({
//         submission_id: submissionId,
//         expected_amount: 948.28,
//         paid_amount: 948.28,
//       }),
//     });
//     fetchStatus();
//   };

//   // -------------------------------
//   // ANALYTICS
//   // -------------------------------
//   const loadAnalytics = async () => {
//     try {
//       const res = await fetch(`${API_BASE}/api/rcm/analytics/dashboard`);
//       if (res.ok) setAnalytics(await res.json());
//     } catch {
//       setError("Failed to load analytics");
//     }
//   };

//   // -------------------------------
//   // UI
//   // -------------------------------
//   return (
//     <div className="max-w-6xl mx-auto p-6 bg-white rounded-xl shadow border space-y-6">
//       <h2 className="text-xl font-semibold">RCM Unified Dev Panel</h2>

//       {/* SUBMIT */}
//       <div className="grid grid-cols-2 gap-4">
//         <div>
//           <h3 className="font-medium mb-2">Submit From S3</h3>
//           <input
//             className="w-full border p-2 mb-2"
//             value={bucket}
//             onChange={(e) => setBucket(e.target.value)}
//           />
//           <input
//             className="w-full border p-2 mb-2 font-mono text-xs"
//             value={key}
//             onChange={(e) => setKey(e.target.value)}
//           />
//           <button
//             disabled={loading}
//             className="bg-blue-600 text-white px-4 py-2 rounded disabled:opacity-60"
//             onClick={submitFromS3}
//           >
//             Submit S3
//           </button>
//         </div>

//         <div>
//           <h3 className="font-medium mb-2">Direct JSON Submit</h3>
//           <textarea
//             rows={6}
//             className="w-full border font-mono text-xs p-2"
//             value={directJson}
//             onChange={(e) => setDirectJson(e.target.value)}
//           />
//           <button
//             disabled={loading}
//             className="bg-purple-600 text-white px-4 py-2 mt-2 rounded disabled:opacity-60"
//             onClick={submitDirect}
//           >
//             Submit JSON
//           </button>
//         </div>
//       </div>

//       {/* STATUS */}
//       {submissionId && (
//         <div className="border-t pt-4">
//           <ProgressBar status={status?.status} />

//           <h3 className="font-medium">Submission Status</h3>
//           <div className="flex items-center gap-3 mt-2">
//             <span className="font-mono text-sm">{submissionId}</span>
//             {status && (
//               <span
//                 className={`px-2 py-1 rounded text-xs font-semibold ${statusColor(
//                   status.status
//                 )}`}
//               >
//                 {status.status}
//               </span>
//             )}
//           </div>

//           {status?.denial_reason && (
//             <div className="text-red-600 text-sm mt-2">
//               {status.denial_reason}
//             </div>
//           )}

//           {status?.raw_edi && (
//             <>
//               <button
//                 className="text-blue-600 text-sm mt-2"
//                 onClick={() => setShowEdi(!showEdi)}
//               >
//                 {showEdi ? "Hide EDI" : "Show EDI"}
//               </button>
//               {showEdi && (
//                 <pre className="bg-black text-green-200 p-3 mt-2 text-xs rounded">
//                   {status.raw_edi}
//                 </pre>
//               )}
//             </>
//           )}
//         </div>
//       )}

//       {/* SIMULATORS */}
//       {submissionId && (
//         <div className="flex gap-3 border-t pt-4">
//           <button onClick={sendAck} className="bg-green-600 text-white px-3 py-2 rounded">
//             Send ACK
//           </button>
//           <button onClick={sendDenial} className="bg-red-600 text-white px-3 py-2 rounded">
//             Send Denial
//           </button>
//           <button onClick={sendPayment} className="bg-emerald-600 text-white px-3 py-2 rounded">
//             Send Payment
//           </button>
//         </div>
//       )}

//       {/* ANALYTICS */}
//       <div className="border-t pt-4">
//         <button
//           onClick={loadAnalytics}
//           className="bg-gray-800 text-white px-4 py-2 rounded"
//         >
//           Load Analytics Dashboard
//         </button>

//         {analytics && (
//           <pre className="mt-3 bg-gray-100 p-3 text-xs rounded">
//             {JSON.stringify(analytics, null, 2)}
//           </pre>
//         )}
//       </div>

//       {error && <div className="text-red-600 text-sm">{error}</div>}
//     </div>
//   );
// };

// export default RcmDevPanel;


import React, { useCallback, useEffect, useState } from "react";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

/* =======================
   TYPES
======================= */
type Status = {
  id: string;
  claim_id?: string;
  status: string;
  denial_reason?: string | null;
  denial_risk?: number;
  raw_edi?: string | null;
  created_at?: string;
};

/* =======================
   UI HELPERS
======================= */
const statusColor = (status: string) => {
  switch (status) {
    case "SUBMITTED":
      return "bg-blue-100 text-blue-700";
    case "ACCEPTED":
      return "bg-green-100 text-green-700";
    case "DENIED":
      return "bg-red-100 text-red-700";
    case "PAID":
      return "bg-emerald-100 text-emerald-700";
    default:
      return "bg-gray-100 text-gray-700";
  }
};

const Spinner = () => (
  <div className="flex items-center gap-2 text-sm text-gray-600 mt-2">
    <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
    Waiting for clearinghouse ACK (277CA)...
  </div>
);

/* =======================
   TIMELINE
======================= */
const Timeline = ({ status }: { status?: string }) => {
  const steps = [
    { label: "Claim Submitted (837)", key: "SUBMITTED" },
    { label: "Clearinghouse ACK (277CA)", key: "ACCEPTED" },
    { label: "AI Decision", key: "AI" },
    { label: "Payment Posted (835)", key: "PAID" },
  ];

  const activeIndex =
    status === "DENIED" ? 2 : steps.findIndex(s => s.key === status);

  return (
    <div className="mt-4 space-y-2">
      {steps.map((s, i) => (
        <div key={i} className="flex items-center gap-2 text-sm">
         <div
               className={`w-3 h-3 rounded-full ${
                  i <= activeIndex && activeIndex >= 0
                    ? "bg-green-500"
                      : "bg-gray-300"
                     }`}
                        />

          <span className={i <= activeIndex ? "font-medium" : "text-gray-500"}>
            {s.label}
          </span>
        </div>
      ))}
    </div>
  );
};

/* =======================
   AI RISK METER
======================= */
const AiRiskMeter = ({ risk }: { risk: number }) => {
  const pct = Math.round(risk * 100);
  return (
    <div className="mt-3">
      <div className="text-sm mb-1">AI Denial Risk</div>
      <div className="h-2 bg-gray-200 rounded-full">
        <div
          className={`h-2 rounded-full ${
            pct > 70 ? "bg-red-500" : pct > 40 ? "bg-yellow-400" : "bg-green-500"
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="text-xs mt-1">{pct}%</div>
    </div>
  );
};

/* =======================
   KPI ANIMATION
======================= */
const AnimatedNumber = ({ value }: { value: number }) => {
  const [display, setDisplay] = useState(0);

  useEffect(() => {
    let current = 0;
    const step = value / 30;
    const interval = setInterval(() => {
      current += step;
      if (current >= value) {
        setDisplay(value);
        clearInterval(interval);
      } else {
        setDisplay(Math.floor(current));
      }
    }, 30);
    return () => clearInterval(interval);
  }, [value]);

  return <span className="text-xl font-semibold">{display}</span>;
};

/* =======================
   MAIN COMPONENT
======================= */
const RcmDevPanel: React.FC = () => {
  const [bucket, setBucket] = useState("healthcare-edi-output");
  const [key, setKey] = useState(
    "claims/P001/02a57ff6-89cb-4fae-bfd7-e29fdf45fcea.json"
  );

  const [submissionId, setSubmissionId] = useState("");
  const [status, setStatus] = useState<Status | null>(null);
  const [analytics, setAnalytics] = useState<any>(null);

  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showEdi, setShowEdi] = useState(false);

  /* =======================
     RESTORE SUBMISSION
  ======================= */
  useEffect(() => {
    const saved = localStorage.getItem("last_submission_id");
    if (saved) setSubmissionId(saved);
  }, []);

  /* =======================
     FETCH STATUS
  ======================= */
  const fetchStatus = useCallback(async () => {
    if (!submissionId) return;
    const res = await fetch(`${API_URL}/api/rcm/status/${submissionId}`);
    if (res.ok) {
      const data = await res.json();
      setStatus(data);
    }
  }, [submissionId]);

  /* =======================
     AUTO REFRESH + TOAST
  ======================= */
  useEffect(() => {
    if (!submissionId) return;
    fetchStatus();
    const interval = setInterval(fetchStatus, 5000);
    return () => clearInterval(interval);
  }, [submissionId, fetchStatus]);

  useEffect(() => {
    if (!status?.status) return;
    setToast(`Status updated → ${status.status}`);
    const t = setTimeout(() => setToast(null), 3000);
    return () => clearTimeout(t);
  }, [status?.status]);

  /* =======================
     SUBMIT FROM S3
  ======================= */
  const submitFromS3 = async () => {
  setLoading(true);
  setError(null);

  try {
    const res = await fetch(`${API_URL}/api/rcm/submit-from-s3`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ bucket, key }),
    });

    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Submit failed");

    // ✅ STORE ID
    setSubmissionId(data.submission_id);
    localStorage.setItem("last_submission_id", data.submission_id);

    // ✅ IMMEDIATELY FETCH STATUS
    setTimeout(fetchStatus, 300);   // <-- THIS FIXES NULL
  } catch (e: any) {
    setError(e.message);
  } finally {
    setLoading(false);
  }
};


  /* =======================
     ANALYTICS
  ======================= */
  const loadAnalytics = async () => {
    const res = await fetch(`${API_URL}/api/rcm/analytics/dashboard`);
    if (res.ok) setAnalytics(await res.json());
  };

  /* =======================
     UI
  ======================= */
  return (
    <div className="max-w-6xl mx-auto p-6 bg-white rounded-xl shadow border space-y-6">
      <h2 className="text-xl font-semibold">RCM Unified Dev Panel</h2>

      {/* SUBMIT */}
      <div>
        <h3 className="font-medium mb-2">Submit From S3</h3>
        <input className="w-full border p-2 mb-2" value={bucket} onChange={e => setBucket(e.target.value)} />
        <input className="w-full border p-2 mb-2 font-mono text-xs" value={key} onChange={e => setKey(e.target.value)} />
        <button onClick={submitFromS3} disabled={loading} className="bg-blue-600 text-white px-4 py-2 rounded">
          Generate Claim
        </button>
      </div>

      {/* STATUS */}
      {submissionId && (
        <div className="border-t pt-4">
          <div className="flex items-center gap-3">
            <span className="font-mono text-sm">{submissionId}</span>
            {status && (
              <span className={`px-2 py-1 rounded text-xs font-semibold ${statusColor(status.status)}`}>
                {status.status}
              </span>
            )}
          </div>

          {status?.status === "SUBMITTED" && <Spinner />}
          <Timeline status={status?.status} />

          {status?.denial_risk !== undefined && <AiRiskMeter risk={status.denial_risk} />}

          {status?.raw_edi && (
            <>
              <button className="text-blue-600 text-sm mt-2" onClick={() => setShowEdi(!showEdi)}>
                {showEdi ? "Hide EDI" : "Show EDI"}
              </button>
              {showEdi && <pre className="bg-black text-green-200 p-3 mt-2 text-xs rounded">{status.raw_edi}</pre>}
            </>
          )}
        </div>
      )}

      {/* ANALYTICS */}
      <div className="border-t pt-4">
        <button onClick={loadAnalytics} className="bg-gray-800 text-white px-4 py-2 rounded">
          Load Analytics
        </button>

        {analytics && (
          <div className="grid grid-cols-3 gap-4 mt-4">
            <div className="p-4 bg-gray-100 rounded">
              Total Claims <AnimatedNumber value={analytics.total_claims} />
            </div>
            <div className="p-4 bg-green-100 rounded">
              Paid Claims <AnimatedNumber value={analytics.paid_claims} />
            </div>
            <div className="p-4 bg-red-100 rounded">
              Denied Claims <AnimatedNumber value={analytics.denied_claims} />
            </div>
          </div>
        )}
      </div>

      {toast && <div className="fixed bottom-5 right-5 bg-black text-white px-4 py-2 rounded">{toast}</div>}
      {error && <div className="text-red-600 text-sm">{error}</div>}
    </div>
  );
};

export default RcmDevPanel;

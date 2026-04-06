import React, { useState } from "react";
import { CloudUpload, FileText, AlertCircle } from "lucide-react";

type UploadItem = {
  name: string;
  patient: string;
  date: string;
  pages: number;
  status: "Parsed" | "Processing" | "Failed";
};

// initial demo data
const initialItems: UploadItem[] = [
  { name: "visit_2391.pdf", patient: "John D", date: "10 Feb 2025", pages: 12, status: "Parsed" },
  { name: "consult_1982.pdf", patient: "Mary S", date: "09 Feb 2025", pages: 8, status: "Processing" },
  { name: "admission_0467.pdf", patient: "—", date: "06 Feb 2025", pages: 5, status: "Failed" },
  { name: "discharge_0077.pdf", patient: "Alex P", date: "05 Feb 2025", pages: 10, status: "Parsed" },
];

// TODO: change this to your real API (Lambda / FastAPI / etc.)
const UPLOAD_EHR_API = "/api/ehr/upload";

const UploadEHR: React.FC = () => {
  const [items, setItems] = useState<UploadItem[]>(initialItems);
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string>("");

  const parsedCount = items.filter((i) => i.status === "Parsed").length;
  const processingCount = items.filter((i) => i.status === "Processing").length;
  const failedCount = items.filter((i) => i.status === "Failed").length;

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    setMessage("");

    if (!file) {
      setMessage("Please choose a file (.pdf/.txt/.docx).");
      return;
    }

    try {
      setLoading(true);

      const form = new FormData();
      form.append("file", file);

      // hit backend – backend should upload to S3 / process EHR
      const res = await fetch(UPLOAD_EHR_API, {
        method: "POST",
        body: form,
      });

      // you can adjust this shape to match your API
      const data = await res.json();

      if (!res.ok || data.ok === false) {
        throw new Error(data.message || "Upload failed");
      }

      // add a new row into the table (use backend values if available)
      const today = new Date().toLocaleDateString("en-GB", {
        day: "2-digit",
        month: "short",
        year: "numeric",
      });

      const newItem: UploadItem = {
        name: file.name,
        patient: data.patient || "Unknown",
        date: today,
        pages: data.pages || 1,
        status: "Processing",
      };

      setItems((prev) => [newItem, ...prev]);
      setMessage("✅ File uploaded successfully.");
      setFile(null);
    } catch (err: any) {
      console.error(err);
      setMessage(`❌ ${err?.message || "Upload failed"}`);
    } finally {
      setLoading(false);
    }
  };

  const statusPill = (status: UploadItem["status"]) => {
    if (status === "Parsed") {
      return "bg-emerald-50 text-emerald-700 border border-emerald-100";
    }
    if (status === "Processing") {
      return "bg-amber-50 text-amber-700 border border-amber-100";
    }
    return "bg-rose-50 text-rose-700 border border-rose-100";
  };

  return (
    <div className="space-y-6">
      {/* Header + quick stats */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-blue-900 flex items-center gap-2">
            <FileText size={20} />
            EHR Uploads
          </h2>
          <p className="text-sm text-gray-500">
            Send encounter files to AgenticAI for parsing, coding, and claim generation.
          </p>
        </div>

        <div className="flex flex-wrap gap-3 text-xs">
          <div className="rounded-xl bg-white shadow-sm border border-gray-100 px-3 py-2">
            <div className="text-gray-400 uppercase tracking-wide">Total Files</div>
            <div className="text-lg font-semibold text-gray-900">{items.length}</div>
          </div>
          <div className="rounded-xl bg-emerald-50 border border-emerald-100 px-3 py-2">
            <div className="text-[11px] text-emerald-700 uppercase tracking-wide">
              Parsed
            </div>
            <div className="text-lg font-semibold text-emerald-700">{parsedCount}</div>
          </div>
          <div className="rounded-xl bg-amber-50 border border-amber-100 px-3 py-2">
            <div className="text-[11px] text-amber-700 uppercase tracking-wide">
              Processing
            </div>
            <div className="text-lg font-semibold text-amber-700">
              {processingCount}
            </div>
          </div>
          <div className="rounded-xl bg-rose-50 border border-rose-100 px-3 py-2">
            <div className="text-[11px] text-rose-700 uppercase tracking-wide">
              Failed
            </div>
            <div className="text-lg font-semibold text-rose-700">{failedCount}</div>
          </div>
        </div>
      </div>

      {/* Upload card */}
      <form
        onSubmit={handleUpload}
        className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 flex flex-col md:flex-row md:items-center md:justify-between gap-4"
      >
        <div className="flex items-start gap-3">
          <div className="mt-1 flex h-10 w-10 items-center justify-center rounded-xl bg-blue-50 text-blue-600">
            <CloudUpload size={20} />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-gray-900">Upload EHR file </h3>
            <p className="text-xs text-gray-500">
              Supported: PDF, DOCX, TXT, CSV. Files are securely stored and processed in your cloud.
            </p>
          </div>
        </div>

        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
          <input
            type="file"
            accept=".pdf,.txt,.doc,.docx,.csv"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
            className="text-xs file:mr-3 file:rounded-lg file:border-0 file:bg-blue-50 file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-blue-700 hover:file:bg-blue-100"
          />
          <button
            type="submit"
            disabled={loading}
            className={`inline-flex items-center justify-center rounded-lg px-4 py-2 text-sm font-medium text-white shadow-sm transition ${
              loading
                ? "bg-gray-400 cursor-not-allowed"
                : "bg-blue-600 hover:bg-blue-700"
            }`}
          >
            {loading ? "Uploading..." : "Upload & Process"}
          </button>
        </div>
      </form>

      {/* Status message */}
      {message && (
        <div className="flex items-center gap-2 text-sm px-4 py-2 rounded-xl border bg-gray-50 text-gray-700 shadow-sm">
          <AlertCircle size={16} className="text-gray-400" />
          <span>{message}</span>
        </div>
      )}

      {/* Table card */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold text-gray-900">Upload history</h3>
            <p className="text-xs text-gray-500">
              Latest EHR files processed by the pipeline.
            </p>
          </div>
          <div className="text-xs text-gray-400">
            Showing <span className="font-semibold text-gray-700">{items.length}</span>{" "}
            files
          </div>
        </div>

        <div className="overflow-hidden rounded-xl border border-gray-100">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-left text-xs text-gray-500">
              <tr>
                <th className="px-3 py-2.5">File Name</th>
                <th className="px-3 py-2.5">Patient</th>
                <th className="px-3 py-2.5">Upload Date</th>
                <th className="px-3 py-2.5 text-center">Pages</th>
                <th className="px-3 py-2.5 text-center">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {items.map((f, i) => (
                <tr key={i} className="hover:bg-gray-50/70 transition">
                  <td className="px-3 py-2.5">
                    <div className="flex items-center gap-2">
                      <FileText size={14} className="text-gray-400" />
                      <span className="truncate">{f.name}</span>
                    </div>
                  </td>
                  <td className="px-3 py-2.5">{f.patient}</td>
                  <td className="px-3 py-2.5">{f.date}</td>
                  <td className="px-3 py-2.5 text-center">{f.pages}</td>
                  <td className="px-3 py-2.5 text-center">
                    <span
                      className={`inline-flex items-center justify-center rounded-full px-2.5 py-1 text-[11px] font-medium ${statusPill(
                        f.status
                      )}`}
                    >
                      {f.status}
                    </span>
                  </td>
                </tr>
              ))}
              {items.length === 0 && (
                <tr>
                  <td
                    colSpan={5}
                    className="px-3 py-6 text-center text-sm text-gray-500"
                  >
                    No files uploaded yet. Use the uploader above to add your first EHR file.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default UploadEHR;

import axios from "axios";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000",
});

export async function uploadEHR(file: File) {
  const form = new FormData();
  form.append("file", file);

  const res = await api.post("/api/ehr/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });

  console.log("raw upload res:", res.data);   // 👈 console
  const raw = res.data || {};
  const dataField = raw.data ?? raw;

  const batchId =
    raw.batchId ??
    dataField?.batchId ??
    raw.meta?.batchId ??
    raw?.job_id ??               // extra common keys
    raw?.taskId ??
    null;

  const payload =
    Array.isArray(raw.rows) ? raw.rows :
    Array.isArray(dataField) ? dataField :
    Array.isArray(dataField?.records) ? dataField.records :
    Array.isArray(raw.items) ? raw.items :
    dataField?.data ?? [];

  return { batchId, payload, __raw: raw };    // 👈 return raw for on-screen debug
}

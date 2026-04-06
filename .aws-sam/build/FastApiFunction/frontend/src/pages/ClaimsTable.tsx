import React, { useState } from "react";

type Row = {
  patient_id: string;
  icd_code: string;
  icd_desc: string;
  cpt_code: string;
  cpt_desc: string;
  e_claim: string; // "CMS-1500" | "UB-04"
};

export default function ClaimsTable() {
  const [file, setFile] = useState<File | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [count, setCount] = useState(0);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setRows([]);
    setCount(0);
    if (!file) { setError("Choose a CSV/XLSX file."); return; }

    const form = new FormData();
    form.append("file", file);

    const qs = new URLSearchParams({ note_fields: "assessment,notes,chief_complaint" });
    const res = await fetch(`/api/claims/table?${qs.toString()}`, { method: "POST", body: form });
    const text = await res.text();
    if (!res.ok) { setError(`HTTP ${res.status}: ${text}`); return; }
    const data = JSON.parse(text);
    setRows(Array.isArray(data.rows) ? data.rows : []);
    setCount(data.count || 0);
  };

  return (
    <div style={{ padding: 16 }}>
      <h2>Claims (ICD/CPT & E-Claim)</h2>
      <form onSubmit={handleSubmit} style={{ display: "flex", gap: 8 }}>
        <input type="file" accept=".csv,.xlsx,.xls" onChange={e => setFile(e.target.files?.[0] || null)} />
        <button type="submit">Upload</button>
      </form>
      {error && <div style={{ color: "red", marginTop: 8 }}>{error}</div>}
      <div style={{ marginTop: 12 }}>Rows: {count}</div>

      <div style={{ overflowX: "auto", marginTop: 12 }}>
        <table style={{ borderCollapse: "collapse", width: "100%" }}>
          <thead>
            <tr>
              <Th>Patient ID</Th><Th>ICD Code</Th><Th>ICD Description</Th>
              <Th>CPT Code</Th><Th>CPT Description</Th><Th>E-Claim</Th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr><Td colSpan={6}>No data. Upload a file.</Td></tr>
            ) : rows.map((r, i) => (
              <tr key={i}>
                <Td>{r.patient_id}</Td>
                <Td>{r.icd_code}</Td>
                <Td>{r.icd_desc}</Td>
                <Td>{r.cpt_code}</Td>
                <Td>{r.cpt_desc}</Td>
                <Td>{r.e_claim}</Td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const Th: React.FC<React.PropsWithChildren> = ({ children }) => (
  <th style={{ border: "1px solid #ddd", padding: 8, background: "#fafafa", textAlign: "left" }}>{children}</th>
);
const Td: React.FC<React.TdHTMLAttributes<HTMLTableCellElement>> = ({ children, ...rest }) => (
  <td {...rest} style={{ border: "1px solid #eee", padding: 8 }}>{children}</td>
);

import React, { useMemo, useState } from "react";

// -------------------------
// Types
// -------------------------
type Metric = { label: string; value: number };
type Activity = { date: string; activity: string; status: string };
type TrendPoint = { label: string; value: number };

type Row = {
  patient_id: string;
  icd_code: string;
  icd_desc: string;
  cpt_code: string;
  cpt_desc: string;
  e_claim: string;
  baseline_total?: number;
  coded_total?: number;
  amount_delta?: number;
};

// -------------------------
// Static sample dashboard data
// -------------------------
const metrics: Metric[] = [
  { label: "Total Patients", value: 1248 },
  { label: "Claims Generated", value: 862 },
  { label: "Claims Approved", value: 743 },
  { label: "EHR Files Processed", value: 1932 },
];

const recentActivity: Activity[] = [
  { date: "2025-02-10", activity: "EHR File Uploaded", status: "Processed" },
  { date: "2025-02-10", activity: "Claim Generated", status: "Pending" },
  { date: "2025-02-09", activity: "Agent Triggered (CoderBot)", status: "Completed" },
  { date: "2025-02-08", activity: "Patient Added", status: "Success" },
];

const trend: TrendPoint[] = [
  { label: "Jan", value: 350 },
  { label: "Feb", value: 280 },
  { label: "Mar", value: 410 },
  { label: "Apr", value: 390 },
  { label: "May", value: 430 },
  { label: "Jun", value: 455 },
];

// -------------------------
// Tailwind metric cards + graph
// -------------------------
const MetricCard: React.FC<Metric> = ({ label, value }) => (
  <div className="bg-white shadow-sm rounded-2xl p-4 min-w-[10rem]">
    <div className="text-xs text-gray-500 uppercase tracking-wide">
      {label}
    </div>
    <div className="text-2xl font-semibold mt-2 text-gray-900">{value}</div>
  </div>
);

const DashboardGraph: React.FC<{ trend: TrendPoint[] }> = ({ trend }) => {
  const max = Math.max(...trend.map((t) => t.value));
  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-4">
      <div className="flex items-center justify-between mb-2">
        <h3 className="font-semibold text-gray-900">Claims Trend</h3>
        <span className="text-xs text-gray-500">Last 6 months</span>
      </div>
      <div className="mt-4 flex items-end gap-3 h-40">
        {trend.map((t) => {
          const height = Math.round((t.value / max) * 100);
          return (
            <div
              key={t.label}
              className="flex-1 flex flex-col items-center text-xs text-gray-600"
            >
              <div
                className="w-full rounded-t-md shadow-inner flex items-end justify-center bg-blue-50"
                style={{ height: `${height}%` }}
              >
                <span className="pb-1 text-[10px]">{t.value}</span>
              </div>
              <span className="mt-2 font-medium">{t.label}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

// -------------------------
// Inline style helpers (for summary + mini charts)
// -------------------------
const cardWrap: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
  gap: 12,
  marginTop: 16,
};
const card: React.CSSProperties = {
  border: "1px solid #e5e7eb",
  borderRadius: 12,
  padding: 16,
  background: "#fff",
  boxShadow: "0 1px 2px rgba(0,0,0,0.05)",
};
const label: React.CSSProperties = { fontSize: 12, color: "#6b7280" };
const valueStyle: React.CSSProperties = {
  fontSize: 24,
  fontWeight: 700,
  color: "#111827",
};

// -------------------------
// MAIN Dashboard component
// -------------------------
const Dashboard: React.FC = () => {
  // rows would typically be fetched from your backend
  const [rows] = useState<Row[]>([]);

  const totals = useMemo(() => {
    const patients = new Set(rows.map((r) => r.patient_id)).size;
    const withICD = rows.filter((r) => r.icd_code && r.icd_code.trim() !== "").length;
    const withCPT = rows.filter((r) => r.cpt_code && r.cpt_code.trim() !== "").length;
    const codedTotal = rows.reduce((s, r) => s + (Number(r.coded_total) || 0), 0);
    const baselineTotal = rows.reduce((s, r) => s + (Number(r.baseline_total) || 0), 0);
    const delta = codedTotal - baselineTotal;
    return { patients, withICD, withCPT, codedTotal, baselineTotal, delta };
  }, [rows]);

  const topICD = useMemo(() => {
    const map = new Map<string, number>();
    rows.forEach((r) => {
      if (!r.icd_code) return;
      map.set(r.icd_code, (map.get(r.icd_code) || 0) + 1);
    });
    return [...map.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5);
  }, [rows]);

  const topCPT = useMemo(() => {
    const map = new Map<string, number>();
    rows.forEach((r) => {
      if (!r.cpt_code) return;
      map.set(r.cpt_code, (map.get(r.cpt_code) || 0) + 1);
    });
    return [...map.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5);
  }, [rows]);

  const fileCount = rows.length;

  return (
    <div className="max-w-6xl mx-auto p-4 space-y-6">
      {/* Header / Hero summary card */}
      <div className="rounded-2xl bg-gradient-to-r from-blue-700 via-indigo-600 to-sky-500 p-5 text-white shadow-md">
        <div className="flex flex-wrap items-center justify-between gap-6">
          <div>
            <p className="text-xs uppercase tracking-wide text-blue-100">
              Claims overview
            </p>
            <p className="text-2xl font-semibold">Claims Dashboard</p>
            <p className="mt-1 text-xs text-blue-100 max-w-md">
              Monitor volume, coding performance, and revenue lift generated by
              AgenticAI from your EHR data.
            </p>
          </div>

          <div className="flex flex-wrap gap-4 text-sm">
            <div className="bg-white/10 rounded-xl px-4 py-2 min-w-[140px]">
              <p className="text-[11px] uppercase tracking-wide text-blue-100">
                Baseline Total
              </p>
              <p className="text-lg font-semibold">
                ₹{fmtMoney(totals.baselineTotal)}
              </p>
            </div>
            <div className="bg-white/10 rounded-xl px-4 py-2 min-w-[140px]">
              <p className="text-[11px] uppercase tracking-wide text-blue-100">
                Coded Total
              </p>
              <p className="text-lg font-semibold">
                ₹{fmtMoney(totals.codedTotal)}
              </p>
            </div>
            <div className="bg-white/10 rounded-xl px-4 py-2 min-w-[140px]">
              <p className="text-[11px] uppercase tracking-wide text-blue-100">
                Revenue Lift Δ
              </p>
              <p
                className={`text-lg font-semibold ${
                  totals.delta >= 0 ? "text-emerald-100" : "text-rose-100"
                }`}
              >
                ₹{fmtMoney(totals.delta)}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Top metrics + activity + graph */}
      <section className="space-y-6">
        {/* top metrics row */}
        <div className="flex flex-wrap gap-4">
          {metrics.map((m) => (
            <MetricCard key={m.label} {...m} />
          ))}
        </div>

        {/* recent activity + graph */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-2 bg-white rounded-2xl shadow-sm border border-gray-100 p-4">
            <h3 className="font-semibold mb-3 text-gray-900">Recent Activity</h3>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-gray-500">
                  <th className="pb-2">Date</th>
                  <th className="pb-2">Activity</th>
                  <th className="pb-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {recentActivity.map((r, i) => (
                  <tr key={i} className="border-t">
                    <td className="py-2">{r.date}</td>
                    <td className="py-2">{r.activity}</td>
                    <td className="py-2">{r.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <DashboardGraph trend={trend} />
        </div>
      </section>

      {/* Existing summary cards + mini charts */}
      <SummaryCards
        patients={totals.patients}
        withICD={totals.withICD}
        withCPT={totals.withCPT}
        baselineTotal={totals.baselineTotal}
        codedTotal={totals.codedTotal}
        delta={totals.delta}
        fileCount={fileCount}
      />

      <MiniCharts topICD={topICD} topCPT={topCPT} />

      {/* Table section */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5 mt-4">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className="text-sm font-semibold text-gray-900">
              Claims detail
            </h3>
            <p className="text-xs text-gray-500">
              Flattened ICD × CPT combinations returned from the pipeline.
            </p>
          </div>
          <div className="text-xs text-gray-500">
            Rows: <span className="font-semibold text-gray-800">{fileCount}</span>
          </div>
        </div>

        <div className="overflow-x-auto rounded-xl border border-gray-100">
          <table className="w-full border-collapse text-sm">
            <thead className="bg-gray-50 text-xs text-gray-500">
              <tr>
                <th className="px-3 py-2.5 text-left">Patient ID</th>
                <th className="px-3 py-2.5 text-left">ICD Code</th>
                <th className="px-3 py-2.5 text-left">ICD Description</th>
                <th className="px-3 py-2.5 text-left">CPT Code</th>
                <th className="px-3 py-2.5 text-left">CPT Description</th>
                <th className="px-3 py-2.5 text-left">E-Claim</th>
                <th className="px-3 py-2.5 text-right">Baseline ₹</th>
                <th className="px-3 py-2.5 text-right">Coded ₹</th>
                <th className="px-3 py-2.5 text-right">Δ ₹</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {rows.length === 0 ? (
                <tr>
                  <td
                    colSpan={9}
                    className="px-3 py-6 text-center text-sm text-gray-500"
                  >
                    No data yet. Claims will appear here once your EHR files are
                    processed in the pipeline.
                  </td>
                </tr>
              ) : (
                rows.map((r, i) => (
                  <tr key={i} className="hover:bg-gray-50/70 transition">
                    <td className="px-3 py-2.5">{r.patient_id}</td>
                    <td className="px-3 py-2.5">{r.icd_code}</td>
                    <td className="px-3 py-2.5">{r.icd_desc}</td>
                    <td className="px-3 py-2.5">{r.cpt_code}</td>
                    <td className="px-3 py-2.5">{r.cpt_desc}</td>
                    <td className="px-3 py-2.5">{r.e_claim}</td>
                    <td className="px-3 py-2.5 text-right">
                      {fmtMoney(r.baseline_total)}
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      {fmtMoney(r.coded_total)}
                    </td>
                    <td className="px-3 py-2.5 text-right font-semibold">
                      {fmtMoney(r.amount_delta)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

// -------------------------
// Helpers + subcomponents
// -------------------------
function fmtMoney(n?: number) {
  const v = Number(n || 0);
  return v.toLocaleString("en-IN", { maximumFractionDigits: 2 });
}

function SummaryCards(props: {
  patients: number;
  withICD: number;
  withCPT: number;
  baselineTotal: number;
  codedTotal: number;
  delta: number;
  fileCount: number;
}) {
  const {
    patients,
    withICD,
    withCPT,
    baselineTotal,
    codedTotal,
    delta,
    fileCount,
  } = props;

  return (
    <div style={cardWrap}>
      <div style={card}>
        <div style={label}>Patients</div>
        <div style={valueStyle}>{patients}</div>
        <div style={{ fontSize: 12, color: "#6b7280" }}>
          Unique patient_id in result rows
        </div>
      </div>
      <div style={card}>
        <div style={label}>Rows Returned</div>
        <div style={valueStyle}>{fileCount}</div>
        <div style={{ fontSize: 12, color: "#6b7280" }}>
          Flattened rows (ICD×CPT combos)
        </div>
      </div>
      <div style={card}>
        <div style={label}>Records with ICD</div>
        <div style={valueStyle}>{withICD}</div>
      </div>
      <div style={card}>
        <div style={label}>Records with CPT</div>
        <div style={valueStyle}>{withCPT}</div>
      </div>
      <div style={card}>
        <div style={label}>Baseline Total (₹)</div>
        <div style={valueStyle}>{fmtMoney(baselineTotal)}</div>
      </div>
      <div style={card}>
        <div style={label}>Coded Total (₹)</div>
        <div style={valueStyle}>{fmtMoney(codedTotal)}</div>
      </div>
      <div style={card}>
        <div style={label}>Lift Δ (₹)</div>
        <div
          style={{
            ...valueStyle,
            color: delta >= 0 ? "#065f46" : "#991b1b",
          }}
        >
          {fmtMoney(delta)}
        </div>
      </div>
    </div>
  );
}

function MiniCharts(props: {
  topICD: [string, number][];
  topCPT: [string, number][];
}) {
  const { topICD, topCPT } = props;

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "1fr 1fr",
        gap: 12,
        marginTop: 16,
      }}
    >
      <BarList title="Top ICD" items={topICD} />
      <BarList title="Top CPT" items={topCPT} />
    </div>
  );
}

function BarList({
  title,
  items,
}: {
  title: string;
  items: [string, number][];
}) {
  const max = Math.max(1, ...items.map((i) => i[1]));
  return (
    <div style={card}>
      <div style={{ ...label, marginBottom: 8 }}>{title}</div>
      {items.length === 0 ? (
        <div style={{ color: "#6b7280", fontSize: 12 }}>No data</div>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {items.map(([code, count]) => (
            <li
              key={code}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                marginBottom: 8,
              }}
            >
              <div style={{ width: 60, fontSize: 12, color: "#374151" }}>
                {code}
              </div>
              <div
                style={{
                  flex: 1,
                  height: 8,
                  background: "#e5e7eb",
                  borderRadius: 9999,
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    width: `${(count / max) * 100}%`,
                    height: "100%",
                    background: "#111827",
                  }}
                />
              </div>
              <div
                style={{
                  width: 28,
                  textAlign: "right",
                  fontSize: 12,
                  color: "#374151",
                }}
              >
                {count}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default Dashboard;

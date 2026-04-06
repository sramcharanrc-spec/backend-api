import React from "react";
import EHRChartsPanel from "../../widgets/EHRChartsPanel";

// Optional: if later your ehrData has real metrics, you can
// compute these from props instead of hard-coding.
type MonthlyClaim = {
  month: string;
  created: number;
  approved: number;
  rejected: number;
};
type CPTUsage = { code: string; desc: string; count: number };

const monthlyClaims: MonthlyClaim[] = [
  { month: "Jan 2025", created: 350, approved: 310, rejected: 40 },
  { month: "Feb 2025", created: 280, approved: 243, rejected: 37 },
  { month: "Mar 2025", created: 410, approved: 365, rejected: 45 },
];

const cptUsage: CPTUsage[] = [
  { code: "99213", desc: "Office Visit", count: 423 },
  { code: "99214", desc: "Complex Visit", count: 289 },
  { code: "93000", desc: "ECG", count: 146 },
];

interface AnalyticsProps {
  ehrData?: any[];
}

const Analytics: React.FC<AnalyticsProps> = ({ ehrData }) => {
  const data = ehrData || [];

  const maxMonthly = Math.max(...monthlyClaims.map((x) => x.created));
  const totalCreated = monthlyClaims.reduce((s, m) => s + m.created, 0);
  const totalApproved = monthlyClaims.reduce((s, m) => s + m.approved, 0);
  const totalRejected = monthlyClaims.reduce((s, m) => s + m.rejected, 0);
  const approvalRate = totalCreated ? Math.round((totalApproved / totalCreated) * 100) : 0;
  const rejectionRate = totalCreated ? Math.round((totalRejected / totalCreated) * 100) : 0;
  const avgMonthly = Math.round(totalCreated / monthlyClaims.length);

  return (
    <div className="space-y-6">
      {/* Page title + pill */}
      <div className="flex items-center justify-between gap-4">
        <div>
          <h2 className="page-title">Analytics</h2>
          <p className="text-sm text-gray-500">
            Claims performance overview for the last 3 months.
          </p>
        </div>
        <span className="inline-flex items-center rounded-full border border-blue-100 bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700">
          Live · Demo Mode
        </span>
      </div>

      {/* Gradient banner with key KPIs */}
      <div className="rounded-2xl bg-gradient-to-r from-blue-600 via-indigo-600 to-sky-500 p-5 text-white shadow-md">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-wide text-blue-100">
              Claims summary
            </p>
            <p className="text-2xl font-semibold">
              {totalCreated.toLocaleString("en-IN")} total claims
            </p>
          </div>
          <div className="flex flex-wrap gap-4 text-sm">
            <div className="bg-white/10 rounded-xl px-4 py-2 min-w-[120px]">
              <p className="text-[11px] uppercase tracking-wide text-blue-100">
                Approval rate
              </p>
              <p className="text-lg font-semibold">{approvalRate}%</p>
            </div>
            <div className="bg-white/10 rounded-xl px-4 py-2 min-w-[120px]">
              <p className="text-[11px] uppercase tracking-wide text-blue-100">
                Rejection rate
              </p>
              <p className="text-lg font-semibold">{rejectionRate}%</p>
            </div>
            <div className="bg-white/10 rounded-xl px-4 py-2 min-w-[140px]">
              <p className="text-[11px] uppercase tracking-wide text-blue-100">
                Avg monthly volume
              </p>
              <p className="text-lg font-semibold">
                {avgMonthly.toLocaleString("en-IN")}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Mini charts section */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {/* Monthly claims chart */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
          <div className="flex items-center justify-between mb-3">
            <div>
              <div className="text-xs font-semibold uppercase tracking-wide text-gray-400">
                Volume
              </div>
              <div className="font-medium text-gray-800">Monthly Claims</div>
            </div>
            <span className="text-xs rounded-full bg-blue-50 px-2 py-1 text-blue-700">
              Last 3 months
            </span>
          </div>

          <div className="flex items-end gap-3 h-40">
            {monthlyClaims.map((m) => {
              const height = Math.round((m.created / maxMonthly) * 100);
              return (
                <div key={m.month} className="flex-1 flex flex-col items-center">
                  <div className="flex-1 flex flex-col justify-end w-full">
                    <div
                      className="relative mx-auto w-7 rounded-t-xl bg-gradient-to-t from-blue-500 to-sky-400 shadow-sm"
                      style={{ height: `${height}%` }}
                    >
                      <div className="absolute -top-5 left-1/2 -translate-x-1/2 text-[10px] bg-white text-gray-800 rounded px-1 py-[1px] shadow-sm">
                        {m.created}
                      </div>
                    </div>
                  </div>
                  <div className="mt-2 text-[11px] text-gray-500">{m.month}</div>
                  <div className="mt-1 text-[10px] text-emerald-600">
                    {Math.round((m.approved / m.created) * 100)}% approved
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Top CPT codes list */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
          <div className="flex items-center justify-between mb-3">
            <div>
              <div className="text-xs font-semibold uppercase tracking-wide text-gray-400">
                Mix
              </div>
              <div className="font-medium text-gray-800">Top CPT Codes</div>
            </div>
            <span className="text-xs rounded-full bg-emerald-50 px-2 py-1 text-emerald-700">
              High frequency
            </span>
          </div>

          <ul className="mt-1 space-y-2 text-sm">
            {cptUsage.map((c, idx) => {
              const maxCount = Math.max(...cptUsage.map((x) => x.count));
              const pct = (c.count / maxCount) * 100;
              return (
                <li
                  key={c.code}
                  className="flex items-center justify-between gap-3 rounded-lg px-2 py-2 hover:bg-gray-50 transition"
                >
                  <div className="flex items-center gap-3">
                    <div className="flex h-7 w-7 items-center justify-center rounded-full bg-blue-50 text-[11px] font-semibold text-blue-700">
                      {idx + 1}
                    </div>
                    <div>
                      <div className="font-medium text-gray-800">
                        {c.code}{" "}
                        <span className="ml-1 text-xs text-gray-500">
                          {c.desc}
                        </span>
                      </div>
                      <div className="mt-1 h-1.5 w-28 rounded-full bg-gray-100 overflow-hidden">
                        <div
                          className="h-full rounded-full bg-gradient-to-r from-blue-500 to-sky-400"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  </div>
                  <div className="text-xs text-gray-500 text-right">
                    <div className="font-semibold text-gray-800">
                      {c.count.toLocaleString("en-IN")}
                    </div>
                    <div>claims</div>
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      </div>

      {/* Existing EHRChartsPanel in a nicer card */}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
        <div className="flex items-center justify-between mb-4">
          <div>
            <div className="text-xs font-semibold uppercase tracking-wide text-gray-400">
              Deep dive
            </div>
            <div className="font-medium text-gray-800">
              EHR-driven Claim Insights
            </div>
          </div>
          <span className="text-xs text-gray-400">
            Source: Uploaded EHR data
          </span>
        </div>

        <EHRChartsPanel data={data} />
      </div>
    </div>
  );
};

export default Analytics;

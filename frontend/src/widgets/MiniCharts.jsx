import React from "react";
// if you use Recharts:
// import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";

export default function MiniCharts({ data }) {
  const list = Array.isArray(data) ? data : [];

  // example transforms — adjust to your schema
  const byAge = list.map((p, i) => ({
    idx: i + 1,
    age: Number.parseInt?.(p?.age, 10) || 0,
  }));

  const byDiagCounts = Object.entries(
    list.reduce((acc, item) => {
      const d = (item?.diagnosis ?? "").toString().trim();
      if (!d) return acc;
      acc[d] = (acc[d] || 0) + 1;
      return acc;
    }, {})
  ).map(([name, value]) => ({ name, value }));

  return (
    <div className="grid md:grid-cols-2 gap-4 mt-6">
      {/* If using Recharts, uncomment the imports above and these blocks */}

      {/* Ages mini line */}
      {/* <div className="p-4 rounded-xl border bg-white">
        <div className="text-sm font-semibold mb-2">Ages Trend</div>
        <ResponsiveContainer width="100%" height={180}>
          <LineChart data={byAge}>
            <XAxis dataKey="idx" hide />
            <YAxis hide />
            <Tooltip />
            <Line type="monotone" dataKey="age" dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div> */}

      {/* Diagnoses mini bar (simple fallback without a lib) */}
      <div className="p-4 rounded-xl border bg-white">
        <div className="text-sm font-semibold mb-2">Top Diagnoses</div>
        {byDiagCounts.length === 0 ? (
          <div className="text-gray-500 text-sm">No data</div>
        ) : (
          <ul className="space-y-1">
            {byDiagCounts
              .sort((a, b) => b.value - a.value)
              .slice(0, 5)
              .map((row) => (
                <li key={row.name} className="flex items-center gap-2">
                  <span className="w-32 truncate">{row.name}</span>
                  <div className="flex-1 h-2 bg-gray-200 rounded">
                    <div
                      className="h-2 bg-blue-500 rounded"
                      style={{
                        width: `${(row.value / byDiagCounts[0].value) * 100}%`,
                      }}
                    />
                  </div>
                  <span className="w-8 text-right tabular-nums">{row.value}</span>
                </li>
              ))}
          </ul>
        )}
      </div>
    </div>
  );
}

import React from "react";

export default function DenialDashboard() {

  const data = [
    { reason: "Invalid CPT", count: 12 },
    { reason: "Eligibility", count: 8 },
    { reason: "Authorization", count: 5 },
  ];

  return (
    <div className="space-y-3">

      {data.map((d) => (
        <div key={d.reason}>

          <div className="flex justify-between text-sm">
            <span>{d.reason}</span>
            <span>{d.count}</span>
          </div>

          <div className="h-2 bg-gray-200 rounded">
            <div
              className="h-2 bg-red-500 rounded"
              style={{ width: `${d.count * 8}%` }}
            />
          </div>

        </div>
      ))}

    </div>
  );
}
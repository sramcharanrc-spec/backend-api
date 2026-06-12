import React from "react";

type Props = {
  status?: string;
};

const tone: Record<string, string> = {
  COMPLETED: "bg-emerald-500/15 text-emerald-200 border-emerald-400/40 shadow-[0_0_18px_rgba(16,185,129,0.18)]",
  COMPLETE: "bg-emerald-500/15 text-emerald-200 border-emerald-400/40 shadow-[0_0_18px_rgba(16,185,129,0.18)]",
  SUCCESS: "bg-emerald-500/15 text-emerald-200 border-emerald-400/40 shadow-[0_0_18px_rgba(16,185,129,0.18)]",
  PAID: "bg-emerald-500/15 text-emerald-200 border-emerald-400/40 shadow-[0_0_18px_rgba(16,185,129,0.18)]",
  ACKNOWLEDGED: "bg-emerald-500/15 text-emerald-200 border-emerald-400/40 shadow-[0_0_18px_rgba(16,185,129,0.18)]",
  RUNNING: "bg-blue-500/15 text-blue-200 border-blue-400/40 shadow-[0_0_18px_rgba(79,140,255,0.2)]",
  PROCESSING: "bg-blue-500/15 text-blue-200 border-blue-400/40 shadow-[0_0_18px_rgba(79,140,255,0.2)]",
  PENDING: "bg-orange-500/15 text-orange-200 border-orange-400/40",
  QUEUED: "bg-yellow-500/15 text-yellow-200 border-yellow-400/40",
  FAILED: "bg-rose-500/15 text-rose-200 border-rose-400/40 shadow-[0_0_18px_rgba(239,68,68,0.16)]",
  DENIED: "bg-rose-500/15 text-rose-200 border-rose-400/40 shadow-[0_0_18px_rgba(239,68,68,0.16)]",
  HITL: "bg-purple-500/15 text-purple-200 border-purple-400/40 shadow-[0_0_18px_rgba(139,92,246,0.18)]",
  HITL_REQUIRED: "bg-purple-500/15 text-purple-200 border-purple-400/40 shadow-[0_0_18px_rgba(139,92,246,0.18)]",
};

const ClaimStatusBadge: React.FC<Props> = ({ status = "PENDING" }) => {
  const normalized = String(status || "PENDING").toUpperCase();
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold ${tone[normalized] || tone.PENDING}`}>
      {normalized.replace(/_/g, " ")}
    </span>
  );
};

export default ClaimStatusBadge;

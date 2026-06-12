import React, { useMemo } from "react";
import { Activity, BarChart3, CheckCircle2, Clock, ShieldCheck, UploadCloud } from "lucide-react";
import PipelineTimeline from "../../components/PipelineTimeline";
import RealtimeAgentFeed from "../../components/RealtimeAgentFeed";
import ClaimStatusBadge from "../../components/ClaimStatusBadge";
import { usePipeline } from "../../hooks/usePipeline";

const stageNames = ["Upload", "Eligibility", "Validation", "Compliance", "Submission", "Payment", "Learning", "Analytics"];

const EndToEndRCM: React.FC = () => {
  const { claims, events, bulkProgress } = usePipeline();
  const liveClaims = Object.values(claims);
  const activeClaim = liveClaims[0];

  const stats = useMemo(() => {
    const total = liveClaims.length;
    const failed = liveClaims.filter((claim) => ["FAILED", "DENIED", "HITL_REQUIRED"].includes(String(claim.status))).length;
    const paid = liveClaims.filter((claim) => ["PAID", "COMPLETED"].includes(String(claim.paymentStatus || claim.status))).length;
    return {
      total,
      failed,
      paid,
      cleanRate: total ? Math.round(((total - failed) / total) * 100) : 0,
    };
  }, [liveClaims]);

  return (
    <div className="p-6 space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="page-title text-2xl font-bold text-slate-900">End-to-End RCM Pipeline</h2>
          <p className="text-sm text-slate-500 max-w-xl">
            Live claim movement from intake through reimbursement, driven by websocket agent events.
          </p>
        </div>
        <div className="inline-flex items-center gap-2 rounded-full bg-emerald-50 px-4 py-1.5 text-xs font-semibold text-emerald-700 border border-emerald-100">
          <Activity size={16} />
          Live websocket connected
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-white border border-slate-200 rounded-lg p-4">
          <UploadCloud className="text-blue-600" size={18} />
          <p className="text-xs text-slate-500 mt-2">Live Claims</p>
          <h3 className="text-2xl font-bold">{stats.total}</h3>
        </div>
        <div className="bg-white border border-slate-200 rounded-lg p-4">
          <CheckCircle2 className="text-emerald-600" size={18} />
          <p className="text-xs text-slate-500 mt-2">Clean Claim Rate</p>
          <h3 className="text-2xl font-bold">{stats.cleanRate}%</h3>
        </div>
        <div className="bg-white border border-slate-200 rounded-lg p-4">
          <ShieldCheck className="text-amber-600" size={18} />
          <p className="text-xs text-slate-500 mt-2">Needs Review</p>
          <h3 className="text-2xl font-bold">{stats.failed}</h3>
        </div>
        <div className="bg-white border border-slate-200 rounded-lg p-4">
          <BarChart3 className="text-indigo-600" size={18} />
          <p className="text-xs text-slate-500 mt-2">Paid or Complete</p>
          <h3 className="text-2xl font-bold">{stats.paid}</h3>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <section className="xl:col-span-2 bg-white rounded-lg border border-slate-200 p-5">
          <div className="flex items-center justify-between gap-3 mb-5">
            <div>
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">Enterprise Pipeline</div>
              <div className="font-semibold text-slate-900">Realtime stage visualization</div>
            </div>
            <ClaimStatusBadge status={activeClaim?.status || "PENDING"} />
          </div>

          <PipelineTimeline liveState={activeClaim} />

          <div className="mt-6 grid grid-cols-1 md:grid-cols-8 gap-2">
            {stageNames.map((stage, index) => (
              <div key={stage} className="rounded-md border border-slate-200 bg-slate-50 p-3 text-center">
                <div className="mx-auto mb-2 flex h-8 w-8 items-center justify-center rounded-full bg-white border border-slate-200 text-xs font-bold">
                  {index + 1}
                </div>
                <div className="text-xs font-semibold text-slate-700">{stage}</div>
                <div className="mt-2 h-1 rounded-full bg-blue-100 overflow-hidden">
                  <div className="h-full bg-blue-600 transition-all" style={{ width: activeClaim ? "100%" : "20%" }} />
                </div>
              </div>
            ))}
          </div>

          <div className="mt-6 flex flex-wrap gap-4 text-sm text-slate-600">
            <span>Queued: {bulkProgress.queued}</span>
            <span>Processing: {bulkProgress.processing}</span>
            <span>Completed: {bulkProgress.completed}</span>
            <span>Failed: {bulkProgress.failed}</span>
          </div>
        </section>

        <RealtimeAgentFeed events={events} />
      </div>

      <section className="bg-white rounded-lg border border-slate-200 p-5">
        <div className="flex items-center gap-2 mb-3">
          <Clock size={16} className="text-slate-500" />
          <h3 className="font-semibold text-slate-900">Recent Claim Status</h3>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {liveClaims.slice(0, 6).map((claim) => (
            <div key={claim.claimId} className="rounded-md border border-slate-200 bg-slate-50 p-3">
              <div className="flex items-center justify-between gap-3">
                <span className="font-mono text-xs text-slate-600">{claim.claimId}</span>
                <ClaimStatusBadge status={claim.status} />
              </div>
              <p className="mt-2 text-sm text-slate-700">{claim.currentAgent || "Queued"} - {claim.currentStep || "Awaiting next agent"}</p>
            </div>
          ))}
          {liveClaims.length === 0 && <p className="text-sm text-slate-500">Waiting for live claim pipeline events.</p>}
        </div>
      </section>
    </div>
  );
};

export default EndToEndRCM;

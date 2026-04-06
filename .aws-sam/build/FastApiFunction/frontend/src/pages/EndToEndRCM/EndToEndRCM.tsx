import React from "react";
import {
  Workflow,
  ArrowRight,
  CheckCircle2,
  AlertTriangle,
  Clock,
} from "lucide-react";

type StageStatus = "healthy" | "warning" | "issue";

interface Stage {
  name: string;
  description: string;
  count: number;
  avgTime: string;
  status: StageStatus;
}

interface Claim {
  id: string;
  patient: string;
  payer: string;
  stage: string;
  status: "Clean Claim" | "Pending" | "Denied";
  submittedOn: string;
  amount: number;
}

const stages: Stage[] = [
  {
    name: "EHR Parsing",
    description: "Extract clinical entities and structure charts from raw notes.",
    count: 1932,
    avgTime: "16 sec",
    status: "healthy",
  },
  {
    name: "Medical Coding",
    description: "Assign ICD / CPT codes using AI-assisted coding agents.",
    count: 862,
    avgTime: "31 sec",
    status: "healthy",
  },
  {
    name: "Audit & Compliance",
    description: "Run coverage, LCD/NCD & documentation checks.",
    count: 805,
    avgTime: "12 sec",
    status: "healthy",
  },
  {
    name: "Claim Submission",
    description: "Package and route clean claims to payer clearing houses.",
    count: 743,
    avgTime: "8 sec",
    status: "warning",
  },
  {
    name: "Denials & Appeals",
    description: "Triage denials and generate appeal-ready packets.",
    count: 119,
    avgTime: "—",
    status: "issue",
  },
];

const claims: Claim[] = [
  {
    id: "C-89213",
    patient: "John Daniels",
    payer: "BlueCross",
    stage: "Claim Submission",
    status: "Clean Claim",
    submittedOn: "09 Feb 2025",
    amount: 12850,
  },
  {
    id: "C-88341",
    patient: "Sarah Miller",
    payer: "UnitedHealth",
    stage: "Audit & Compliance",
    status: "Pending",
    submittedOn: "10 Feb 2025",
    amount: 7600,
  },
  {
    id: "C-87122",
    patient: "Alex Paul",
    payer: "Aetna",
    stage: "Denials & Appeals",
    status: "Denied",
    submittedOn: "08 Feb 2025",
    amount: 5400,
  },
];

const totalClaims = stages[stages.length - 2].count + stages[stages.length - 1].count;
const cleanClaims = stages[stages.length - 2].count;
const deniedClaims = stages[stages.length - 1].count;
const cleanRate = totalClaims ? Math.round((cleanClaims / totalClaims) * 100) : 0;
const denialRate = totalClaims ? Math.round((deniedClaims / totalClaims) * 100) : 0;
const avgCycleDays = 19; // demo value

const statusColor = (status: StageStatus) => {
  switch (status) {
    case "healthy":
      return "text-emerald-600 bg-emerald-50 border-emerald-100";
    case "warning":
      return "text-amber-600 bg-amber-50 border-amber-100";
    case "issue":
      return "text-rose-600 bg-rose-50 border-rose-100";
  }
};

const statusDot = (status: StageStatus) => {
  switch (status) {
    case "healthy":
      return "bg-emerald-500";
    case "warning":
      return "bg-amber-500";
    case "issue":
      return "bg-rose-500";
  }
};

const claimStatusPill = (status: Claim["status"]) => {
  if (status === "Clean Claim") {
    return "bg-emerald-50 text-emerald-700 border border-emerald-100";
  }
  if (status === "Pending") {
    return "bg-amber-50 text-amber-700 border border-amber-100";
  }
  return "bg-rose-50 text-rose-700 border border-rose-100";
};

const EndToEndRCM: React.FC = () => {
  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="page-title text-2xl font-bold text-blue-900">
            End-to-End RCM Pipeline
          </h2>
          <p className="text-sm text-gray-500 max-w-xl">
            Visualise how your EHR data flows from clinical documentation to
            clean claims, payments, and denial management — all driven by Agentic AI.
          </p>
        </div>
        <div className="flex items-center gap-2 rounded-full bg-blue-50 px-4 py-1.5 text-xs font-medium text-blue-700 border border-blue-100">
          <Workflow size={16} />
          Auto-orchestrated pipeline
        </div>
      </div>

      {/* Gradient KPIs */}
      <div className="rounded-2xl bg-gradient-to-r from-blue-700 via-indigo-600 to-sky-500 p-5 text-white shadow-md">
        <div className="flex flex-wrap items-center justify-between gap-6">
          <div>
            <p className="text-xs uppercase tracking-wide text-blue-100">
              RCM health snapshot
            </p>
            <p className="text-2xl font-semibold">
              {totalClaims.toLocaleString("en-IN")} claims this cycle
            </p>
            <p className="mt-1 text-xs text-blue-100">
              From EHR parsing all the way to payments & appeals.
            </p>
          </div>

          <div className="flex flex-wrap gap-4 text-sm">
            <div className="bg-white/10 rounded-xl px-4 py-2 min-w-[140px]">
              <p className="text-[11px] uppercase tracking-wide text-blue-100">
                Clean claim rate
              </p>
              <p className="text-lg font-semibold">{cleanRate}%</p>
              <p className="text-[11px] text-blue-100 mt-1">
                {cleanClaims.toLocaleString("en-IN")} clean claims
              </p>
            </div>

            <div className="bg-white/10 rounded-xl px-4 py-2 min-w-[140px]">
              <p className="text-[11px] uppercase tracking-wide text-blue-100">
                Denial rate
              </p>
              <p className="text-lg font-semibold">{denialRate}%</p>
              <p className="text-[11px] text-blue-100 mt-1">
                {deniedClaims.toLocaleString("en-IN")} denied / appealed
              </p>
            </div>

            <div className="bg-white/10 rounded-xl px-4 py-2 min-w-[140px]">
              <p className="text-[11px] uppercase tracking-wide text-blue-100">
                Avg. cycle time
              </p>
              <p className="text-lg font-semibold">{avgCycleDays} days</p>
              <p className="text-[11px] text-blue-100 mt-1">
                From encounter to payment posting
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Pipeline + recent claims */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Pipeline timeline */}
        <div className="lg:col-span-2 bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
          <div className="flex items-center justify-between mb-4">
            <div>
              <div className="text-xs font-semibold uppercase tracking-wide text-gray-400">
                Pipeline
              </div>
              <div className="font-medium text-gray-900">
                RCM stages from EHR to cash
              </div>
            </div>
            <div className="flex items-center gap-2 text-[11px] text-gray-500">
              <span className="inline-flex items-center gap-1">
                <span className="h-2 w-2 rounded-full bg-emerald-500" /> Healthy
              </span>
              <span className="inline-flex items-center gap-1">
                <span className="h-2 w-2 rounded-full bg-amber-500" /> Watch
              </span>
              <span className="inline-flex items-center gap-1">
                <span className="h-2 w-2 rounded-full bg-rose-500" /> Issue
              </span>
            </div>
          </div>

          <div className="relative pt-4">
            {/* Vertical line */}
            <div className="absolute left-4 top-0 bottom-0 w-px bg-gradient-to-b from-blue-200 via-gray-200 to-blue-200" />

            <div className="space-y-5">
              {stages.map((stage, idx) => (
                <div key={stage.name} className="flex items-start gap-4">
                  {/* Step icon */}
                  <div className="relative z-10 mt-1">
                    <div className="h-7 w-7 rounded-full bg-white shadow flex items-center justify-center border border-gray-200">
                      {idx === stages.length - 1 ? (
                        <AlertTriangle className="w-4 h-4 text-rose-500" />
                      ) : idx === stages.length - 2 ? (
                        <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                      ) : (
                        <ArrowRight className="w-4 h-4 text-blue-500" />
                      )}
                    </div>
                  </div>

                  {/* Card */}
                  <div className="flex-1 rounded-xl border border-gray-100 bg-gray-50/60 px-4 py-3 hover:bg-white hover:shadow-sm transition">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-semibold uppercase tracking-wide text-gray-400">
                          Step {idx + 1}
                        </span>
                        <span className="text-sm font-semibold text-gray-900">
                          {stage.name}
                        </span>
                      </div>
                      <div
                        className={`inline-flex items-center gap-2 rounded-full px-2.5 py-1 text-[11px] border ${statusColor(
                          stage.status
                        )}`}
                      >
                        <span
                          className={`h-1.5 w-1.5 rounded-full ${statusDot(
                            stage.status
                          )}`}
                        />
                        {stage.status === "healthy"
                          ? "Healthy throughput"
                          : stage.status === "warning"
                          ? "Monitor volume"
                          : "Needs attention"}
                      </div>
                    </div>

                    <p className="mt-1 text-xs text-gray-600">
                      {stage.description}
                    </p>

                    <div className="mt-3 flex flex-wrap items-center gap-4 text-xs text-gray-500">
                      <div className="flex items-center gap-1.5">
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                        <span>
                          {stage.count.toLocaleString("en-IN")}{" "}
                          <span className="text-gray-400">records</span>
                        </span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <Clock className="w-3.5 h-3.5 text-blue-500" />
                        <span>
                          Avg time:{" "}
                          <span className="font-medium text-gray-700">
                            {stage.avgTime}
                          </span>
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {/* Overall flow bar */}
            <div className="mt-6">
              <div className="flex items-center justify-between text-xs text-gray-500 mb-1">
                <span>Encounter → Coding → Audit → Submission → Payment</span>
                <span className="font-medium text-emerald-600">
                  {cleanRate}% clean claims
                </span>
              </div>
              <div className="h-1.5 rounded-full bg-gray-100 overflow-hidden">
                <div className="h-full w-full bg-gradient-to-r from-blue-500 via-emerald-500 to-sky-400" />
              </div>
            </div>
          </div>
        </div>

        {/* Recent claims */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 p-5">
          <div className="flex items-center justify-between mb-3">
            <div>
              <div className="text-xs font-semibold uppercase tracking-wide text-gray-400">
                Live stream
              </div>
              <div className="font-medium text-gray-900">Recent claims</div>
            </div>
            <span className="text-[11px] text-gray-400">
              {claims.length} records
            </span>
          </div>

          <div className="space-y-2 text-sm">
            {claims.map((claim) => (
              <div
                key={claim.id}
                className="rounded-xl border border-gray-100 bg-gray-50/70 px-3 py-2.5 hover:bg-white hover:shadow-sm transition"
              >
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-mono text-gray-500">
                        {claim.id}
                      </span>
                      <span
                        className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] ${claimStatusPill(
                          claim.status
                        )}`}
                      >
                        {claim.status === "Clean Claim" ? "Clean" : claim.status}
                      </span>
                    </div>
                    <div className="mt-1 text-xs text-gray-600">
                      {claim.patient} · {claim.payer}
                    </div>
                  </div>
                  <div className="text-right text-xs text-gray-500">
                    <div className="font-medium text-gray-800">
                      ₹{claim.amount.toLocaleString("en-IN")}
                    </div>
                    <div>{claim.submittedOn}</div>
                    <div className="mt-0.5 text-[11px] text-blue-600">
                      {claim.stage}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>

          <button className="mt-4 w-full rounded-full border border-gray-200 bg-gray-50 py-2 text-xs font-medium text-gray-700 hover:bg-gray-100 transition">
            View full RCM queue
          </button>
        </div>
      </div>
    </div>
  );
};

export default EndToEndRCM;

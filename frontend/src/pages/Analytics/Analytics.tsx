import React, { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  AlertTriangle,
  BadgeCheck,
  Bot,
  Clock3,
  FileSearch,
  HeartPulse,
  Layers3,
  ShieldCheck,
  Timer,
  TrendingUp,
} from "lucide-react";

import RealtimeAgentFeed from "../../components/RealtimeAgentFeed";
import EHRChartsPanel from "../../widgets/EHRChartsPanel";
import { usePipeline } from "../../hooks/usePipeline";
import { connectAnalyticsWS } from "../../services/analyticsWS";
import { fetchEnterpriseAnalytics } from "../../services/rcmApi";
import type { EnterpriseAnalytics } from "../../types/enterprise";
import "./Analytics.css";

interface Props {
  ehrData?: any[];
}

const colors = ["#2563eb", "#14b8a6", "#f97316", "#8b5cf6", "#ef4444", "#22c55e", "#06b6d4"];
const money = (value: number) => Number(value || 0).toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
const pct = (value?: number | null) => (value === undefined || value === null ? "" : `${Math.round(Number(value))}%`);

const formatMs = (value?: number | null) => {
  const ms = Number(value || 0);
  if (!ms) return "";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)}s`;
  const minutes = seconds / 60;
  if (minutes < 60) return `${minutes.toFixed(minutes < 10 ? 1 : 0)}m`;
  const hours = minutes / 60;
  return `${hours.toFixed(hours < 10 ? 1 : 0)}h`;
};

const EmptyChart = ({ label }: { label: string }) => (
  <div className="ec-empty-chart">
    <span>{label}</span>
  </div>
);

const Analytics: React.FC<Props> = ({ ehrData = [] }) => {
  const [enterprise, setEnterprise] = useState<EnterpriseAnalytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const { events } = usePipeline();

  useEffect(() => {
    const socket = connectAnalyticsWS((data) => {
      if (data.enterprise_analytics) setEnterprise(data.enterprise_analytics);
    });

    return () => {
      socket.onmessage = null;
      socket.onerror = null;
      if (socket.readyState === WebSocket.CONNECTING) socket.onopen = () => socket.close();
      if (socket.readyState === WebSocket.OPEN) socket.close();
    };
  }, []);

  useEffect(() => {
    const load = async () => {
      try {
        setLoading(true);
        setEnterprise(await fetchEnterpriseAnalytics());
      } catch (err) {
        console.error(err);
        setError("Failed to load enterprise analytics data");
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const summary = enterprise?.summary || {};
  const trendData = enterprise?.claim_trends || [];
  const payerRanking = enterprise?.payer_ranking || [];
  const denialReasons = enterprise?.denial_reasons || [];
  const agentPerformance = enterprise?.agent_performance || [];

  const analyticsCards = useMemo(
    () => [
      ["Average Cycle Time", formatMs(summary.average_processing_time_ms), Clock3],
      ["Average Payment Time", formatMs(summary.average_payment_time_ms), Timer],
      ["Top Denial Reason", summary.top_denial_reason || "", AlertTriangle],
      ["Best Payer", summary.best_payer || "", HeartPulse],
      ["Worst Payer", summary.worst_payer || "", ShieldCheck],
      ["SLA Compliance", pct(summary.sla_compliance), BadgeCheck],
      ["Claim Success Rate", pct(summary.claim_success_ratio), TrendingUp],
      ["Total Claims", String(summary.total_claims ?? ""), Bot],
    ],
    [summary]
  );

  if (loading) return <div className="ec-page">Loading enterprise analytics...</div>;
  if (error) return <div className="ec-page">{error}</div>;

  return (
    <div className="ec-page">
      <section className="ec-hero analytics-hero">
        <div>
          <p className="ec-eyebrow">Enterprise Analytics Intelligence</p>
          <h1>AI Revenue Analytics Command Center</h1>
          <p>Cycle time, payer performance, SLA outcomes, denial reasons, claim success, and agent performance from persisted workflow data.</p>
        </div>
        <div className="ec-live-card">
          <span className="ec-live-dot" />
          <div>
            <strong>Streaming analytics active</strong>
            <small>{events.length} websocket events reconciled</small>
          </div>
        </div>
      </section>

      <section className="ec-kpi-grid analytics-modules">
        {analyticsCards.map(([label, value, Icon]: any, index) => (
          <article className="ec-kpi-card analytics-module" key={label} style={{ ["--accent" as string]: colors[index % colors.length] }}>
            <div className="ec-kpi-head">
              <span><Icon size={17} /> {label}</span>
            </div>
            <strong>{value}</strong>
          </article>
        ))}
      </section>

      <section className="ec-command-grid">
        <article className="ec-panel ec-wide">
          <div className="ec-panel-title">
            <div>
              <h2>Claim Trends</h2>
              <p>Claim volume, successful claims, denials, and revenue by period.</p>
            </div>
            <TrendingUp size={20} />
          </div>
          {trendData.length ? (
            <ResponsiveContainer width="100%" height={330}>
              <LineChart data={trendData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#dbeafe" />
                <XAxis dataKey="period" />
                <YAxis />
                <Tooltip formatter={(value: any, name: string) => name === "revenue" ? money(Number(value)) : value} />
                <Line type="monotone" dataKey="claims" stroke="#2563eb" strokeWidth={3} name="Claims" />
                <Line type="monotone" dataKey="success" stroke="#14b8a6" strokeWidth={3} name="Success" />
                <Line type="monotone" dataKey="denials" stroke="#ef4444" strokeWidth={3} name="Denials" />
                <Line type="monotone" dataKey="revenue" stroke="#8b5cf6" strokeWidth={2} name="Revenue" />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <EmptyChart label="No claim trend records available" />
          )}
        </article>

        <article className="ec-panel">
          <div className="ec-panel-title">
            <div>
              <h2>Payer Ranking</h2>
              <p>Success and denial rate by payer.</p>
            </div>
          </div>
          {payerRanking.length ? (
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={payerRanking}>
                <CartesianGrid strokeDasharray="3 3" stroke="#dbeafe" />
                <XAxis dataKey="payer" />
                <YAxis />
                <Tooltip />
                <Bar dataKey="success_rate" fill="#14b8a6" radius={[6, 6, 0, 0]} name="Success %" />
                <Bar dataKey="denial_rate" fill="#ef4444" radius={[6, 6, 0, 0]} name="Denial %" />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <EmptyChart label="No payer ranking records available" />
          )}
        </article>

        <article className="ec-panel">
          <div className="ec-panel-title">
            <div>
              <h2>Denial Reasons</h2>
              <p>Root cause distribution from claim outcomes.</p>
            </div>
          </div>
          {denialReasons.length ? (
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie data={denialReasons} dataKey="count" nameKey="reason" innerRadius={58} outerRadius={96} paddingAngle={4}>
                  {denialReasons.map((_: any, index: number) => <Cell key={index} fill={colors[index % colors.length]} />)}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <EmptyChart label="No denial reason records available" />
          )}
        </article>

        <article className="ec-panel ec-wide">
          <div className="ec-panel-title">
            <div>
              <h2>Agent Performance Heatmap</h2>
              <p>Event volume, duration, and failure pressure by agent.</p>
            </div>
            <Layers3 size={20} />
          </div>
          {agentPerformance.length ? (
            <div className="agent-performance-heatmap">
              {agentPerformance.map((agent: any) => {
                const failure = Number(agent.failure_rate || 0);
                const level = Math.max(0.12, Math.min(1, (failure + Number(agent.avg_duration_ms || 0) / 1000) / 100));
                return (
                  <div key={agent.agent} style={{ ["--level" as string]: String(level) }}>
                    <b>{agent.agent}</b>
                    <span>{agent.events} events</span>
                    <small>{formatMs(agent.avg_duration_ms)} avg, {pct(agent.failure_rate)} fail</small>
                  </div>
                );
              })}
            </div>
          ) : (
            <EmptyChart label="No agent performance records available" />
          )}
        </article>

        <article className="ec-panel ec-wide">
          <RealtimeAgentFeed events={events.slice(0, 14)} title="Realtime Analytics Activity Stream" />
        </article>

        <article className="ec-panel">
          <div className="ec-panel-title">
            <div>
              <h2>EHR And OCR Insights</h2>
              <p>Embedded source-document analytics.</p>
            </div>
            <FileSearch size={20} />
          </div>
          <EHRChartsPanel data={ehrData} />
        </article>
      </section>
    </div>
  );
};

export default Analytics;

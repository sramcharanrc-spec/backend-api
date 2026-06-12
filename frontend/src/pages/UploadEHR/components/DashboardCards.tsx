import type { LucideIcon } from "lucide-react";

type Metric = {
  label: string;
  value: string | number;
  trend?: any;
  icon: LucideIcon;
  tone?: string;
};

type DashboardCardsProps = {
  metrics: Metric[];
};

const DashboardCards = ({ metrics }: DashboardCardsProps) => {
  return (
    <div className="cw-dashboard-cards">
      {metrics.map((metric) => {
        const Icon = metric.icon;

        return (
          <div className={`cw-dashboard-card ${metric.tone || ""}`} key={metric.label}>
            <div className="cw-dashboard-icon">
              <Icon size={20} />
            </div>

            <div className="cw-dashboard-content">
              <span>{metric.label}</span>
              <strong>{metric.value}</strong>
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default DashboardCards;
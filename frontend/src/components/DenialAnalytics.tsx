export default function DenialAnalytics({ data }: any) {

  const highRisk = data.filter((d: any) =>
    (d.risk_score || d.claim?.denial_risk?.risk_score || 0) > 0.7
  ).length;

  return (
    <div className="analytics-card">
      <h4>Denial Risk</h4>
      <p>High Risk Claims: {highRisk}</p>
    </div>
  );
}
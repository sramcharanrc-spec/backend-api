
export default function KPICards({ data }: any) {
  const safeData = Array.isArray(data)
    ? data
    : [];

  console.log("KPICards data:", safeData);
  console.log(
    "Statuses:",
    safeData.map((d: any) => ({
      claim_id: d.claim_id,
      status: d.status,
      total_charge: d.total_charge,
      claim_charge: d.claim?.total_charge
    }))
  );

  const normalized = safeData.map((d: any) => ({
    ...d,
    status: String(
      d.status ||
      d.claim?.status ||
      ""
    ).toUpperCase()
  }));

  const total = normalized.length;

  const completed = normalized.filter(
    (d: any) =>
      [
        "COMPLETED",
        "PAID",
        "COMMAND_CENTER"
      ].includes(d.status)
  ).length;

  const hitl = normalized.filter(
    (d: any) =>
      [
        "HITL_REQUIRED",
        "MANUAL_REVIEW_REQUIRED",
        "WAITING_FOR_REVIEW"
      ].includes(d.status)
  ).length;

  const revenue = normalized.reduce(
    (sum: number, d: any) =>
      sum + Number(
        d.total_charge ||
        d.claim?.total_charge ||
        d.payment_amount ||
        0
      ),
    0
  );

  return (
    <div className="kpi-grid">

      <div className="kpi-card">
        <h4>Total Claims</h4>
        <p>{total}</p>
      </div>

      <div className="kpi-card success">
        <h4>Completed</h4>
        <p>{completed}</p>
      </div>

      <div className="kpi-card warning">
        <h4>HITL Required</h4>
        <p>{hitl}</p>
      </div>

      <div className="kpi-card revenue">
        <h4>Total Revenue</h4>
        <p>₹ {revenue.toLocaleString()}</p>
      </div>

    </div>
  );
}

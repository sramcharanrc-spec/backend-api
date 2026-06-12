export default function ClaimFunnel({ data }: any) {

  const stages = {
    Intake: data.length,
    Validated: data.filter((d: any) => d.status === "VALIDATED").length,
    Approved: data.filter((d: any) => d.status === "APPROVED").length,
    Paid: data.filter((d: any) => d.status === "COMPLETED").length,
  };

  return (
    <div className="funnel">

      {Object.entries(stages).map(([key, value]) => (
        <div key={key} className="funnel-step">
          <span>{key}</span>
          <strong>{value}</strong>
        </div>
      ))}

    </div>
  );
}
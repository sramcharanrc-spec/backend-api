import React from "react";

const SummaryCards = ({ data }) => {
  const total = data.length;
  const avgAge = total ? Math.round(data.reduce((s,p)=>s+(parseInt(p.age)||0),0)/total) : "-";
  const diagnoses = [...new Set(data.map(d=>d.diagnosis))].slice(0,3);

  return (
    <div className="cards">
      <div className="card small">
        <div className="card-title">Total Patients</div>
        <div className="card-value">{total}</div>
      </div>
      <div className="card small">
        <div className="card-title">Avg Age</div>
        <div className="card-value">{avgAge}</div>
      </div>
      <div className="card small">
        <div className="card-title">Top Diagnoses</div>
        <div className="card-value">{diagnoses.join(", ") || "-"}</div>
      </div>
    </div>
  );
};

export default SummaryCards;

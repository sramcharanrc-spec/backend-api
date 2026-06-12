import React from "react";

interface PatientData {
  age: string | number;
  diagnosis: string;
}

interface DashboardCardsProps {
  data: PatientData[];
}

const DashboardCards: React.FC<DashboardCardsProps> = ({ data }) => {
  const totalPatients = data.length;

  const avgAge =
    totalPatients > 0
      ? Math.round(
          data.reduce((sum, p) => sum + (parseInt(p.age as string) || 0), 0) /
            totalPatients
        )
      : 0;

  const topDiagnosis = [...new Set(data.map((p) => p.diagnosis))].slice(0, 3);

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-6">
      <div className="bg-blue-50 border-l-4 border-blue-500 p-4 rounded shadow">
        <h3 className="text-sm text-gray-600">Total Patients</h3>
        <p className="text-2xl font-bold text-blue-600">{totalPatients}</p>
      </div>

      <div className="bg-green-50 border-l-4 border-green-500 p-4 rounded shadow">
        <h3 className="text-sm text-gray-600">Average Age</h3>
        <p className="text-2xl font-bold text-green-600">{avgAge}</p>
      </div>

      <div className="bg-purple-50 border-l-4 border-purple-500 p-4 rounded shadow">
        <h3 className="text-sm text-gray-600">Top Diagnoses</h3>
        <ul className="text-sm font-medium text-purple-700 mt-1">
          {topDiagnosis.map((d, i) => (
            <li key={i}>• {d}</li>
          ))}
        </ul>
      </div>
    </div>
  );
};

export default DashboardCards;

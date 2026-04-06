import React from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  PieChart,
  Pie,
  Cell,
  Legend,
  ResponsiveContainer,
} from "recharts";

const COLORS = ["#4F46E5", "#10B981", "#F59E0B", "#EF4444", "#6366F1"];

interface PatientData {
  patient_name: string;
  age: string | number;
  diagnosis: string;
}

interface EHRChartsProps {
  data: PatientData[];
}

const EHRCharts: React.FC<EHRChartsProps> = ({ data }) => {
  const ageData = data.map((p) => ({
    name: p.patient_name,
    age: parseInt(p.age as string) || 0,
  }));

  const diagnosisCount = data.reduce<Record<string, number>>((acc, p) => {
    acc[p.diagnosis] = (acc[p.diagnosis] || 0) + 1;
    return acc;
  }, {});

  const diagnosisData = Object.entries(diagnosisCount).map(([key, val]) => ({
    name: key,
    value: val,
  }));

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mt-6">
      {/* Age Distribution */}
      <div className="bg-white rounded-lg shadow p-4">
        <h3 className="text-lg font-semibold mb-4 text-blue-600">
          Age Distribution
        </h3>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={ageData}>
            <XAxis dataKey="name" />
            <YAxis />
            <Tooltip />
            <Bar dataKey="age" fill="#3B82F6" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Diagnosis Breakdown */}
      <div className="bg-white rounded-lg shadow p-4">
        <h3 className="text-lg font-semibold mb-4 text-green-600">
          Diagnosis Breakdown
        </h3>
        <ResponsiveContainer width="100%" height={300}>
          <PieChart>
            <Pie
              data={diagnosisData}
              cx="50%"
              cy="50%"
              labelLine={false}
              outerRadius={100}
              fill="#8884d8"
              dataKey="value"
              label={({ name, percent }) =>
                `${name} ${(percent * 100).toFixed(0)}%`
              }
            >
              {diagnosisData.map((_, index) => (
                <Cell key={index} fill={COLORS[index % COLORS.length]} />
              ))}
            </Pie>
            <Tooltip />
            <Legend />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default EHRCharts;

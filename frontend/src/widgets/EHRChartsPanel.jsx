import React from "react";


import { BarChart, Bar, XAxis, YAxis, Tooltip, PieChart, Pie, Cell, Legend, ResponsiveContainer } from "recharts";

const COLORS = ["#4F46E5", "#10B981", "#F59E0B", "#EF4444", "#6366F1"];

const EHRChartsPanel = ({ data }) => {
  const ageData = (data || []).map(d => ({ name: d.patient_name || d.name || d.patient_id, age: parseInt(d.age) || 0 }));
  const diagnosisCount = Object.entries((data||[]).reduce((m,p)=>{ m[p.diagnosis]=(m[p.diagnosis]||0)+1; return m; }, {})).map(([k,v])=>({name:k,value:v}));

  return (
    <div className="grid grid-2">
      <div className="chart-card">
        <h4>Age Distribution</h4>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={ageData}>
            <XAxis dataKey="name" hide />
            <YAxis />
            <Tooltip />
            <Bar dataKey="age" fill="#3B82F6" />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="chart-card">
        <h4>Diagnosis Breakdown</h4>
        <ResponsiveContainer width="100%" height={300}>
          <PieChart>
            <Pie data={diagnosisCount} dataKey="value" nameKey="name" outerRadius={100} label>
              {diagnosisCount.map((_,i)=><Cell key={i} fill={COLORS[i%COLORS.length]} />)}
            </Pie>
            <Tooltip />
            <Legend />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default EHRChartsPanel;

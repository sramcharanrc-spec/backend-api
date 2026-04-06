import React, { useState } from "react";
import { Routes, Route, Navigate } from "react-router-dom";

// Layout + shared components
import Layout from "./components/Layout";

// Pages
import Login from "./pages/Loginpage/Login";
import Dashboard from "./pages/Dashboard/Dashboard";
import UploadEHR from "./pages/UploadEHR/UploadEHR";
import Patients from "./pages/Patients/Patients";
import Analytics from "./pages/Analytics/Analytics";
import Agents from "./pages/Agents/Agents";
import Settings from "./pages/Settings/Settings";
import EndToEndRCM from "./pages/EndToEndRCM/EndToEndRCM";
import Payments from "./pages/Payments/Payments";
import ClaimsTable from "./pages/ClaimsTable";
import RcmDevPanelPage from "./pages/RcmPanel/RcmDevPanel";

// 🔐 Protected route wrapper
const Protected: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const isLoggedIn = localStorage.getItem("isLoggedIn") === "true";
  return isLoggedIn ? <>{children}</> : <Navigate to="/login" replace />;
};

const App: React.FC = () => {
  const [ehrData, setEhrData] = useState<any>(null);

  const onEhrUpload = (data: any) => {
    setEhrData(data);
  };

  return (
    <Routes>
      {/* Public route: Login */}
      <Route path="/" element={<Navigate to="/login" replace />} />
      <Route path="/login" element={<Login />} />

      {/* Protected routes with Layout */}
      <Route
        path="/"
        element={
          <Protected>
            <Layout />
          </Protected>
        }
      >
        <Route path="dashboard" element={<Dashboard ehrData={ehrData} />} />
        <Route path="upload" element={<UploadEHR onUpload={onEhrUpload} />} />
        <Route path="patients" element={<Patients ehrData={ehrData} />} />
        <Route path="analytics" element={<Analytics ehrData={ehrData} />} />
        <Route path="agents" element={<Agents ehrData={ehrData} />} />
        <Route path="settings" element={<Settings />} />
        <Route path="end-to-end-rcm" element={<EndToEndRCM ehrData={ehrData} />} />
        <Route path="payments" element={<Payments />} />
        <Route path="claims" element={<ClaimsTable />} />
        <Route path="/rcm-dev" element={<RcmDevPanelPage />} />

      </Route>

      {/* Fallback */}
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
};

export default App;

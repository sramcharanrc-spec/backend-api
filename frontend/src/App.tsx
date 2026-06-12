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
// import ClaimsTable from "./pages/UploadEHR/ClaimsTable";
import RcmDevPanelPage from "./pages/RcmPanel/RcmDevPanel";
import ClaimSubmit from "./components/ClaimSubmit";
import Payments from "./pages/Payments/Payments";
import ClearingHouse from "./pages/ClearingHouse/ClearingHouse";
import CaseOrchestration from "./pages/CaseOrchestration/CaseOrchestration";
import ClaimProfile from "./pages/ClaimProfile/ClaimProfile";

//  Protected route wrapper
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
        <Route path="claim-workspace" element={<UploadEHR onUpload={onEhrUpload} />} />
        <Route path="patients" element={<Patients ehrData={ehrData} />} />
        <Route path="analytics" element={<Analytics ehrData={ehrData} />} />
        <Route path="/agents" element={<Agents />} />
        <Route path="settings" element={<Settings />} />
        <Route path="end-to-end-rcm" element={<EndToEndRCM ehrData={ehrData} />} />
        <Route path="payments" element={<Payments />} />
        <Route path="/case" element={<CaseOrchestration />} />
        <Route path="/case/:claimId" element={<CaseOrchestration />} />
        <Route path="/claim/:id" element={<ClaimProfile />} />
        <Route path="/submit-claim" element={<ClaimSubmit />} />
        <Route path="/submit-payment" element={<Payments />} />
        <Route path="/clearinghouse" element={<ClearingHouse />} />
      </Route>

      {/* Fallback */}
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
};

export default App;

import axios from "axios";

const API = "http://127.0.0.1:8000/run-rcm";

export const fetchClaims = async () => {
  const res = await axios.get(`${API}/list`);
  return res.data.submissions;
};

export const fetchReconciliation = async () => {
  const res = await axios.get(`${API}/reconciliation`);
  return res.data;
};

export const fetchAnalytics = async () => {
  const res = await axios.get(`${API}/analytics/dashboard`);
  return res.data;
};

export const fetchAgentStatus = async () => {
  const res = await axios.get(`${API}/agents/status`);
  return res.data;
};
import axios from "axios";

export const fetchReconciliation = async () => {
  const response = await axios.get("/api/reconciliation");
  return response.data;
};
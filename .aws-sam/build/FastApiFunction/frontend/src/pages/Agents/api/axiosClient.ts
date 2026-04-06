// src/pages/Agents/api/axiosClient.ts
import axios from "axios";

const API_BASE = import.meta.env.VITE_API_BASE || "";

const axiosClient = axios.create({
  baseURL: API_BASE,
  headers: {
    "Content-Type": "application/json",
  },
});

axiosClient.interceptors.request.use((config) => {
  const token = localStorage.getItem("idToken");
  if (token && config.headers) {
    (config.headers as Record<string, string>).Authorization = `Bearer ${token}`;
  }
  return config;
});

export default axiosClient;

import axios from "axios";

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE, // e.g. http://127.0.0.1:8000
  withCredentials: false,
  headers: { "Content-Type": "application/json" },
});

// Optional: response error logging
api.interceptors.response.use(
  (r) => r,
  (err) => {
    // surface backend error messages consistently
    const msg =
      err?.response?.data?.detail ||
      err?.response?.data?.message ||
      err.message;
    console.error("[API ERROR]", msg, err?.response);
    return Promise.reject(err);
  }
);

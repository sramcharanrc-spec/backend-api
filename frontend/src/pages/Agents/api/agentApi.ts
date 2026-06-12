


import axiosClient from "./axiosClient";

export const getAgents = async () => {

  const res = await axiosClient.get("/api/rcm/agents/status");

  return res.data;

};
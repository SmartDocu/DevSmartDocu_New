// src/lib/api.js
import axios from "axios";
import { supabase } from "./supabase";

const api = axios.create({
  baseURL: process.env.REACT_APP_API_URL,
});

// 🔥 요청마다 자동으로 토큰 붙이기
api.interceptors.request.use(async (config) => {
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (session?.access_token) {
    config.headers.Authorization = `Bearer ${session.access_token}`;
  }

  return config;
});

export default api;
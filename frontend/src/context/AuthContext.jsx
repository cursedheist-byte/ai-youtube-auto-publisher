import { createContext, useContext, useEffect, useState } from "react";
import apiClient from "../api/client";
import { getCredentialSettings, getAccessHomePath } from "../api/access";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (!token) {
      setLoading(false);
      return;
    }
    apiClient
      .get("/api/auth/me")
      .then((res) => setUser(res.data))
      .catch(() => localStorage.removeItem("access_token"))
      .finally(() => setLoading(false));
  }, []);

  async function login(email, password) {
    // Backend expects OAuth2 password-flow form fields (username/password).
    const form = new URLSearchParams();
    form.set("username", email);
    form.set("password", password);

    const res = await apiClient.post("/api/auth/login", form, {
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    });
    localStorage.setItem("access_token", res.data.access_token);
    const me = await apiClient.get("/api/auth/me");
    setUser(me.data);
    return me.data;
  }

  async function getHomePath(currentUser = user) {
    if (currentUser?.role === "admin") return "/dashboard";
    const settings = await getCredentialSettings();
    return getAccessHomePath(currentUser, settings);
  }

  async function register(email, password) {
    await apiClient.post("/api/auth/register", { email, password });
    return login(email, password);
  }

  function logout() {
    localStorage.removeItem("access_token");
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, register, getHomePath, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

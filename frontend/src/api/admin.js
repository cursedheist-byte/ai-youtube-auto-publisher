import apiClient from "./client";
export function listAdminUsers() { return apiClient.get("/api/admin/users").then((res) => res.data); }
export function terminateUser(userId) { return apiClient.post(`/api/admin/users/${userId}/terminate`).then((res) => res.data); }

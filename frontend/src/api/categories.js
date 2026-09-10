import apiClient from "./client";
export function listCategories() { return apiClient.get("/api/categories").then((res) => res.data); }
export function createCategory(name) { return apiClient.post("/api/admin/categories", { name }).then((res) => res.data); }
export function updateCategory(id, name) { return apiClient.patch(`/api/admin/categories/${id}`, { name }).then((res) => res.data); }
export function deleteCategory(id) { return apiClient.delete(`/api/admin/categories/${id}`); }

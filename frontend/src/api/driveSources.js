import apiClient from "./client";

export function listDriveSources() {
  return apiClient.get("/api/admin/drive-sources").then((res) => res.data);
}

export function createDriveSource(name, folderLink, categoryId) {
  return apiClient
    .post("/api/admin/drive-sources", { name, folder_link: folderLink, category_id: categoryId })
    .then((res) => res.data);
}

export function updateDriveSource(id, patch) {
  return apiClient.patch(`/api/admin/drive-sources/${id}`, patch).then((res) => res.data);
}

export function deleteDriveSource(id) {
  return apiClient.delete(`/api/admin/drive-sources/${id}`);
}

export function scanDriveSource(id) {
  return apiClient.post(`/api/admin/drive-sources/${id}/scan`).then((res) => res.data);
}

export function listDriveVideos(id) {
  return apiClient.get(`/api/admin/drive-sources/${id}/videos`).then((res) => res.data);
}

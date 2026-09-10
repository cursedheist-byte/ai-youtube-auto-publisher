import apiClient from "./client";

export function listEligibleVideos(channelId, categoryId = null) {
  const query = categoryId ? `?category_id=${categoryId}` : "";
  return apiClient.get(`/api/uploads/channels/${channelId}/eligible-videos${query}`).then((res) => res.data);
}

export function listUploadHistory(channelId) {
  return apiClient.get(`/api/uploads/channels/${channelId}/history`).then((res) => res.data);
}

export function uploadNow(channelId, driveVideoId = null, categoryId = null) {
  return apiClient
    .post(`/api/uploads/channels/${channelId}/upload-now`, { ...(driveVideoId ? { drive_video_id: driveVideoId } : {}), ...(categoryId ? { category_id: categoryId } : {}) })
    .then((res) => res.data);
}

export function listAutomationRuns(channelId) {
  return apiClient.get(`/api/channels/${channelId}/runs`).then((res) => res.data);
}

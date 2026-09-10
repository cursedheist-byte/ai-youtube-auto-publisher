import apiClient from "./client";

export function listMyChannels() {
  return apiClient.get("/api/channels").then((res) => res.data);
}

export function startOAuth() {
  return apiClient.get("/api/channels/oauth/start").then((res) => res.data);
}

export function disconnectChannel(channelId) {
  return apiClient.post(`/api/channels/${channelId}/disconnect`);
}

export function updateChannelSettings(channelId, patch) {
  return apiClient.patch(`/api/channels/${channelId}/settings`, patch).then((res) => res.data);
}

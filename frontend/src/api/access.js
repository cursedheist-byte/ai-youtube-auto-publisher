import apiClient from "./client";

export async function getCredentialSettings(){ return (await apiClient.get("/api/access/credentials")).data; }
export async function saveCredentialSettings(payload){ return (await apiClient.put("/api/access/credentials", payload)).data; }
export async function redeemAccessCode(code){ return (await apiClient.post("/api/access/redeem", {code})).data; }

// The API is authoritative. `own` is the default for new users, so the
// configuration flags distinguish an actually configured own-credentials
// account from a new/unconfigured account.
export function isAccessConfigured(settings){
  return settings?.access_mode === "admin" || (
    settings?.access_mode === "own" &&
    settings.google_client_id_configured &&
    settings.google_client_secret_configured &&
    settings.openrouter_api_key_configured
  );
}

export function getAccessHomePath(user, settings){
  return user?.role === "admin" || isAccessConfigured(settings) ? "/dashboard" : "/setup";
}
export async function listAccessCodes(){ return (await apiClient.get("/api/admin/access-codes")).data; }
export async function generateAccessCode(){ return (await apiClient.post("/api/admin/access-codes")).data; }

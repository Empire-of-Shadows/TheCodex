import type { User, Guild, GuideData, WelcomeData, UserActivity, Channel, Role } from "./types";

async function apiFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (res.status === 401) {
    window.location.href = "/login";
    throw new Error("Unauthorized");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export const api = {
  me: () => apiFetch<User>("/api/me"),
  guilds: () => apiFetch<Guild[]>("/api/guilds"),
  botInviteUrl: () => apiFetch<{ url: string }>("/api/bot-invite-url"),
  getUserActivity: (guildId?: string) =>
    apiFetch<UserActivity>(guildId ? `/api/user-activity?guild_id=${guildId}` : "/api/user-activity"),

  getGuide: (guildId: string) =>
    apiFetch<{ guide_data: GuideData | null }>(`/api/guilds/${guildId}/guide`),
  putGuide: (guildId: string, guide_data: GuideData) =>
    apiFetch<{ ok: boolean; guide_data: GuideData }>(`/api/guilds/${guildId}/guide`, {
      method: "PUT",
      body: JSON.stringify({ guide_data }),
    }),

  getWelcome: (guildId: string) =>
    apiFetch<{ welcome_data: WelcomeData | null }>(`/api/guilds/${guildId}/welcome`),
  putWelcome: (guildId: string, welcome_data: WelcomeData) =>
    apiFetch<{ ok: boolean }>(`/api/guilds/${guildId}/welcome`, {
      method: "PUT",
      body: JSON.stringify({ welcome_data }),
    }),

  validateGuide: (data: GuideData) =>
    apiFetch<{ valid: boolean; error: string | null }>("/api/validate/guide", {
      method: "POST",
      body: JSON.stringify({ data }),
    }),
  validateWelcome: (data: WelcomeData) =>
    apiFetch<{ valid: boolean; error: string | null }>("/api/validate/welcome", {
      method: "POST",
      body: JSON.stringify({ data }),
    }),

  getChannels: (guildId: string) =>
    apiFetch<Channel[]>(`/api/guilds/${guildId}/channels`),
  getRoles: (guildId: string) =>
    apiFetch<Role[]>(`/api/guilds/${guildId}/roles`),

  getDocs: (builder: "guide" | "welcome", topic: string) =>
    apiFetch<{ title: string; content: string }>(`/api/docs/${builder}/${topic}`),
};

export interface PublicStats {
  servers: number;
  suggestions: number;
  wyr_votes: number;
}

export async function fetchPublicStats(): Promise<PublicStats | null> {
  try {
    const resp = await fetch("/api/stats/public", { credentials: "omit" });
    if (!resp.ok) return null;
    return (await resp.json()) as PublicStats;
  } catch {
    return null;
  }
}

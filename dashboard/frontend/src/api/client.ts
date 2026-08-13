import type {
  User,
  Guild,
  GuideData,
  GreetingData,
  BoardData,
  BoardPosted,
  UserActivity,
  UserEntitlements,
  GuildOverview,
  Channel,
  Role,
  AuditLogResponse,
  SettingsResponse,
  SettingsPatch,
  GuildSettings,
} from "./types";
import { apiFetch, apiUrl } from "../_engine/api/http";

// Re-export the shared transport surface for pages/components.
export {
  UnauthorizedError,
  ApiError,
  TimeoutError,
  discordLoginUrl,
  logoutUrl,
} from "../_engine/api/http";

export const api = {
  me: () => apiFetch<User>("/api/me", { suppressAuthHandler: true }),
  guilds: () => apiFetch<Guild[]>("/api/guilds"),
  botInviteUrl: () => apiFetch<{ url: string }>("/api/bot-invite-url"),
  getUserActivity: (guildId?: string) =>
    apiFetch<UserActivity>(guildId ? `/api/user-activity?guild_id=${guildId}` : "/api/user-activity"),

  /** What the member can use in one guild. Guild-scoped; any member of it may ask. */
  getUserEntitlements: (guildId: string) =>
    apiFetch<UserEntitlements>(`/api/user-entitlements?guild_id=${guildId}`),

  /**
   * Everything the admin home shows for one guild, in one request.
   * Panel-access gated; 403 for a member with no admin tier in that guild.
   */
  getGuildOverview: (guildId: string) =>
    apiFetch<GuildOverview>(`/api/guilds/${guildId}/overview`),

  getGuide: (guildId: string) =>
    apiFetch<{ guide_data: GuideData | null }>(`/api/guilds/${guildId}/guide`),
  putGuide: (guildId: string, guide_data: GuideData) =>
    apiFetch<{ ok: boolean; guide_data: GuideData }>(`/api/guilds/${guildId}/guide`, {
      method: "PUT",
      body: JSON.stringify({ guide_data }),
    }),

  getGreeting: (guildId: string) =>
    apiFetch<{ greeting_data: GreetingData | null }>(`/api/guilds/${guildId}/greeting`),
  putGreeting: (guildId: string, greeting_data: GreetingData) =>
    apiFetch<{ ok: boolean }>(`/api/guilds/${guildId}/greeting`, {
      method: "PUT",
      body: JSON.stringify({ greeting_data }),
    }),

  getBoard: (guildId: string) =>
    apiFetch<{ board_data: BoardData | null; posted: BoardPosted | null }>(
      `/api/guilds/${guildId}/board`,
    ),
  putBoard: (guildId: string, board_data: BoardData) =>
    apiFetch<{ ok: boolean }>(`/api/guilds/${guildId}/board`, {
      method: "PUT",
      body: JSON.stringify({ board_data }),
    }),

  validateGuide: (data: GuideData) =>
    apiFetch<{ valid: boolean; error: string | null }>("/api/validate/guide", {
      method: "POST",
      body: JSON.stringify({ data }),
    }),
  validateGreeting: (data: GreetingData) =>
    apiFetch<{ valid: boolean; error: string | null }>("/api/validate/greeting", {
      method: "POST",
      body: JSON.stringify({ data }),
    }),
  validateBoard: (data: BoardData) =>
    apiFetch<{ valid: boolean; error: string | null }>("/api/validate/board", {
      method: "POST",
      body: JSON.stringify({ data }),
    }),

  getChannels: (guildId: string) =>
    apiFetch<Channel[]>(`/api/guilds/${guildId}/channels`),
  getRoles: (guildId: string) =>
    apiFetch<Role[]>(`/api/guilds/${guildId}/roles`),

  getDocs: (builder: "guide" | "greeting" | "board", topic: string) =>
    apiFetch<{ title: string; content: string }>(`/api/docs/${builder}/${topic}`),

  settings: (guildId: string) =>
    apiFetch<SettingsResponse>(`/api/guilds/${guildId}/settings`),
  saveSettings: (guildId: string, patch: SettingsPatch) =>
    apiFetch<{ config: GuildSettings }>(`/api/guilds/${guildId}/settings`, {
      method: "PUT",
      body: JSON.stringify(patch),
    }),

  auditLog: (
    guildId: string,
    before?: string | null,
    section?: string | null,
    limit = 50,
  ) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (before) params.set("before", before);
    if (section) params.set("section", section);
    return apiFetch<AuditLogResponse>(
      `/api/guilds/${guildId}/audit-log?${params.toString()}`,
    );
  },

  userDataGuilds: () =>
    apiFetch<{ id: string; name: string | null; icon: string | null }[]>(
      "/api/user/data/guilds",
    ),
  exportUserDataUrl: (guildId?: string | null) =>
    guildId
      ? apiUrl(`/api/user/data/export?guild_id=${encodeURIComponent(guildId)}`)
      : apiUrl("/api/user/data/export"),
  deleteUserData: (guildId?: string | null) =>
    apiFetch<{ user_id: string; guild_id: string | null; deleted: Record<string, number> }>(
      "/api/user/data",
      { method: "DELETE", body: JSON.stringify({ confirm: true, guild_id: guildId ?? null }) },
    ),
};

export interface PublicStats {
  servers: number;
  suggestions: number;
  wyr_votes: number;
}

export async function fetchPublicStats(): Promise<PublicStats | null> {
  try {
    const resp = await fetch(apiUrl("/api/stats/public"), { credentials: "omit" });
    if (!resp.ok) return null;
    return (await resp.json()) as PublicStats;
  } catch {
    return null;
  }
}

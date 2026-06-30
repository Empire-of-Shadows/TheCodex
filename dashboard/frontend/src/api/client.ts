import type {
  User,
  Guild,
  GuideData,
  WelcomeData,
  UserActivity,
  Channel,
  Role,
  AuditLogResponse,
  SettingsResponse,
  SettingsPatch,
  GuildSettings,
} from "./types";

const API_BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");
const DEFAULT_TIMEOUT_MS = 15000;
const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

let _csrfToken: string | null = null;
let _csrfInFlight: Promise<string | null> | null = null;

async function fetchCsrfToken(): Promise<string | null> {
  const res = await fetch(`${API_BASE}/auth/csrf`, { credentials: "include" });
  if (res.status === 401) return null;
  if (!res.ok) return null;
  const body = (await res.json().catch(() => ({}))) as { csrf_token?: string };
  return body.csrf_token ?? null;
}

async function ensureCsrf(force = false): Promise<string | null> {
  if (force) _csrfToken = null;
  if (_csrfToken) return _csrfToken;
  if (!_csrfInFlight) {
    _csrfInFlight = fetchCsrfToken().finally(() => {
      _csrfInFlight = null;
    });
  }
  const token = await _csrfInFlight;
  if (token) _csrfToken = token;
  return token;
}

function buildUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) return path;
  return `${API_BASE}${path}`;
}

async function rawFetch(url: string, init: RequestInit): Promise<Response> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), DEFAULT_TIMEOUT_MS);
  try {
    return await fetch(url, { ...init, signal: ctrl.signal });
  } finally {
    clearTimeout(timer);
  }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method ?? "GET").toUpperCase();
  const isUnsafe = UNSAFE_METHODS.has(method);
  const url = buildUrl(path);

  const baseHeaders: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string> | undefined),
  };

  if (isUnsafe) {
    const token = await ensureCsrf();
    if (token) baseHeaders["X-CSRF-Token"] = token;
  }

  let res: Response;
  try {
    res = await rawFetch(url, {
      credentials: "include",
      ...init,
      method,
      headers: baseHeaders,
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") {
      throw new Error("Request timed out");
    }
    throw e;
  }

  if (isUnsafe && res.status === 403) {
    const body = await res.clone().json().catch(() => ({}));
    const detail = String(body?.detail ?? "");
    if (/csrf/i.test(detail)) {
      const token = await ensureCsrf(true);
      if (token) {
        baseHeaders["X-CSRF-Token"] = token;
        res = await rawFetch(url, {
          credentials: "include",
          ...init,
          method,
          headers: baseHeaders,
        });
      }
    }
  }

  if (res.status === 401) {
    _csrfToken = null;
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
      ? `${API_BASE}/api/user/data/export?guild_id=${encodeURIComponent(guildId)}`
      : `${API_BASE}/api/user/data/export`,
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
    const resp = await fetch(`${API_BASE}/api/stats/public`, { credentials: "omit" });
    if (!resp.ok) return null;
    return (await resp.json()) as PublicStats;
  } catch {
    return null;
  }
}

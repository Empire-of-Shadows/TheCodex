/**
 * Codex-specific select options.
 *
 * These mirror the constants in the bot's admin/settings/panel_configs.py, so the
 * dashboard and the Discord panel offer the same choices.
 *
 * The bot-neutral lists (timezones, hours, minutes, Discord's thread auto-archive
 * values) and the `optionLabel` helper moved to the shared engine at
 * `_engine/components/settings/options.ts` on 2026-08-12.
 */

export const WYR_CATEGORY_OPTIONS: [string, string][] = [
  ["sfw", "SFW only"],
  ["nsfw", "NSFW only"],
  ["mixed", "Mixed"],
];

export const WYR_CLEANUP_OPTIONS: [number, string][] = [
  [7, "7 Days"],
  [14, "14 Days"],
  [30, "30 Days"],
  [60, "60 Days"],
  [90, "90 Days"],
];

// Mirrors WYR._build_scope_clause - the three banks a server can draw from.
export const WYR_SOURCE_OPTIONS: [string, string][] = [
  ["both", "Shared questions and this server's own"],
  ["global_only", "Shared questions only"],
  ["guild_only", "This server's own questions only"],
];

// Mirrors wyr_bank.FORMATS / FORMAT_LABELS.
export const WYR_FORMAT_OPTIONS: [string, string][] = [
  ["wyr", "Would You Rather"],
  ["poll", "Question with answers"],
  ["open", "Open-ended question"],
];

export const WYR_MAX_PENDING_OPTIONS: [number, string][] = [
  [1, "1 waiting"],
  [2, "2 waiting"],
  [3, "3 waiting"],
  [5, "5 waiting"],
  [10, "10 waiting"],
];

export const ACCOUNT_AGE_OPTIONS: [number, string][] = [
  [30, "30 Days"],
  [60, "60 Days"],
  [90, "90 Days"],
  [120, "120 Days"],
  [180, "180 Days"],
];

export const DROPS_TRACKER_BUCKETS = ["Updates", "Free", "Prime"] as const;

/** How many Panel Access roles a server may hand out. */
export const PANEL_ACCESS_ROLE_MAX = 10;

/**
 * Static option lists for the admin settings form.
 *
 * These mirror the constants in the bot's `admin/settings/panel_configs.py`.
 * The Discord panel and this dashboard write the same config keys, so a value
 * that exists here but not there (or the other way round) is a real bug -
 * change both together, never one alone.
 */

export const TIMEZONE_OPTIONS: [string, string][] = [
  ["America/New_York", "US Eastern"],
  ["America/Chicago", "US Central"],
  ["America/Denver", "US Mountain"],
  ["America/Los_Angeles", "US Pacific"],
  ["Europe/London", "UK / GMT"],
  ["Europe/Paris", "Central Europe"],
  ["Europe/Berlin", "Germany"],
  ["Asia/Tokyo", "Japan"],
  ["Australia/Sydney", "Australia Eastern"],
];

export const HOUR_OPTIONS: [number, string][] = Array.from({ length: 24 }, (_, h) => [
  h,
  `${String(h).padStart(2, "0")}:00`,
]);

export const MINUTE_OPTIONS: [number, string][] = [
  [0, ":00"],
  [15, ":15"],
  [30, ":30"],
  [45, ":45"],
];

export const ARCHIVE_OPTIONS: [number, string][] = [
  [60, "1 Hour"],
  [1440, "1 Day"],
  [4320, "3 Days"],
  [10080, "1 Week"],
];

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

/** Look up a label from one of the lists above, falling back to the raw value. */
export function optionLabel<V extends string | number>(
  options: [V, string][],
  value: V,
): string {
  const hit = options.find(([v]) => v === value);
  return hit ? hit[1] : String(value);
}

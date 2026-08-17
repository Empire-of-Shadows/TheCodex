// ── User & Guild ──────────────────────────────────────────────────────────

import type {
  Guild as EngineGuild,
  SessionUser,
} from "../_engine/api/types";

// Shapes that are the same across the fleet now live in the engine. Re-exported
// here so codex's own modules keep importing their types from one place.
export type {
  Channel,
  FeatureState,
  FeatureStatus,
  PanelRole,
  Role,
} from "../_engine/api/types";
// Also needed in local scope below - a `export type {...}` re-export does not bind.
import type { FeatureStatus, PanelRole } from "../_engine/api/types";

export interface User extends SessionUser {
  // codex's backend always populates these; narrow them back to non-null.
  username: string;
  discriminator: string;
  can_access_admin_any: boolean;
  can_access_settings_any: boolean;
}

// The engine leaves panel_role optional because TheDecree and ImperialReminder
// omit it. Codex's /api/guilds always sends it, so narrow it back to required.
//
// member_count is the same story with one twist: codex always sends the KEY, but
// the value is null for a guild with no ServerData snapshot yet - so it narrows
// to required-and-nullable, not required.
export interface Guild extends EngineGuild {
  panel_role: PanelRole;
  member_count: number | null;
}

// ── User Activity ────────────────────────────────────────────────────────

/** One day of a vote trend. `date` is YYYY-MM-DD in UTC. */
export interface TrendPoint {
  date: string;
  votes: number;
}

export interface WyrActivity {
  total_votes: number;
  // Five options: the poll question format carries up to five answers.
  //
  // Still returned by the endpoint, no longer rendered. Summing "option 1
  // votes" across unrelated questions is meaningless - option order is
  // arbitrary per question - so the bar that drew it has been removed.
  // Left on the wire rather than deleted; dropping it is its own change.
  option_breakdown: {
    option1: number;
    option2: number;
    option3: number;
    option4: number;
    option5: number;
  };
  /**
   * Votes by question format, from the format stamped on each vote document.
   * Open-ended questions post no vote buttons, so an "open" vote is never
   * recorded - the UI says "not counted", never zero. `unclassified` covers
   * votes from before the stamp existed whose question was deleted before the
   * backfill could classify them; render it only when non-zero.
   */
  format_breakdown: {
    wyr: number;
    poll: number;
    unclassified: number;
  };
  first_vote: string | null;
  last_vote: string | null;
  /** "voted within the last day". NOT a streak length - see streak_days. */
  streak_active: boolean;
  /** True consecutive-day count, from Daily.WYR_Votes.created_at. */
  streak_days: number;
  /** Real per-day history. Replaces the hardcoded sparkline array. */
  trend: TrendPoint[];
  days_voted_30d: number;
}

/** One of the user's own suggestions, with the outcome they came to see. */
export interface SuggestionItem {
  suggestion_id: string;
  text: string;
  status: string;
  votes: number;
  created_at: string | null;
}

export interface SuggestionsActivity {
  submitted: number;
  votes_cast: number;
  by_status: Record<string, number>;
  last_activity: string | null;
  items: SuggestionItem[];
}

/**
 * The member's own question submissions and what became of them.
 *
 * This closes the loop the whole question-bank feature exists to close: the
 * complaint that started it was that submitted questions never visibly get used.
 */
export interface SubmissionsActivity {
  sent: number;
  posted: number;
  waiting: number;
  declined: number;
  /** Submissions by intended question format, recorded at submit time. */
  by_format: {
    wyr: number;
    poll: number;
    open: number;
    unclassified?: number;
  };
  latest_posted: {
    question_id: number | null;
    posted_at: string | null;
    votes: number | null;
  } | null;
}

export interface TagTrackerGuild {
  guild_id: string;
  guild_name: string;
  server_tag: string;
  has_role: boolean | null;
}

export interface BoostActivity {
  is_boosting: boolean;
  boosts: {
    guild_id: string;
    guild_name: string;
    boost_start: string | null;
    /** Whole days boosting. The bot already computes this and dropped it. */
    duration_days: number | null;
  }[];
}

export interface UserActivity {
  wyr: WyrActivity;
  suggestions: SuggestionsActivity;
  tag_tracker: TagTrackerGuild[];
  boost: BoostActivity;
  submissions: SubmissionsActivity;
}

// ── Member entitlements ──────────────────────────────────────────────────

export interface EmbedFeatureEntitlement {
  key: string;
  label: string;
  /** Whether THIS member can use it, under the guild-keyed rule. */
  available: boolean;
  /** Whether the guild restricted it to specific tiers at all. */
  restricted: boolean;
}

export interface EmbedEntitlements {
  /** May open the embed builder at all (admin, or holds any tier role). */
  access: boolean;
  enabled: boolean;
  tiers: string[];
  features: EmbedFeatureEntitlement[];
  colors: {
    /**
     * "free" = the guild opted into free colour access for everyone;
     * "palette" = the member's assigned sets below; "default_only" = no
     * palette assigned, embeds post with the server default colour.
     */
    mode: "free" | "palette" | "default_only";
    default_color: string | null;
    sets: { name: string; colors: Record<string, string> }[];
  };
  description_limit: number;
}

export interface CapabilityEntitlement {
  key: string;
  label: string;
  granted: boolean;
}

export interface ToggleRole {
  source: "board" | "guide";
  role_id: string;
  name: string | null;
  held: boolean;
}

export interface UserEntitlements {
  guild_id: string;
  /** Every section independently nullable - one failure never blanks the page. */
  embed: EmbedEntitlements | null;
  capabilities: CapabilityEntitlement[] | null;
  self_serve: {
    wyr_ping: { available: boolean; subscribed: boolean };
    toggle_roles: ToggleRole[];
  } | null;
  status: {
    screening_whitelisted: boolean;
    whitelist_role_held: boolean;
  } | null;
  submissions: { enabled: boolean; pending: number; max: number } | null;
}

// ── Guild overview (admin home) ──────────────────────────────────────────

export interface WyrToday {
  question_id: number | null;
  text: string;
  format: string;
  votes: number;
  voters: number;
  posted_at: string | null;
  /**
   * The post itself, for a jump link. There is deliberately no thread_id: the
   * bot never stores one, and deriving it from the message id would produce a
   * dead link on exactly the servers where opening the thread failed.
   */
  message_id: string | null;
  channel_id: string | null;
}

export interface WyrBank {
  /** Shared questions this guild is allowed to draw from. */
  global: number;
  /** Questions private to this guild. */
  guild: number;
  used_here: number;
  formats: string[];
  /**
   * Questions in the bank whose format this guild does not post - they can
   * never appear. Zero unless the guild narrowed question_formats.
   */
  unpostable: number;
}

export interface WyrOverview {
  enabled: boolean;
  channel_id: string | null;
  next_post_at: string | null;
  today: WyrToday | null;
  trend: TrendPoint[];
  voters_30d: number;
  days_posted_30d: number;
  avg_votes_per_day: number;
  bank: WyrBank;
  submissions_pending: number;
}

export interface PendingSuggestion {
  suggestion_id: string;
  text: string;
  votes: number;
  created_at: string | null;
  message_id: string | null;
}

export interface SuggestionsOverview {
  total: number;
  by_status: Record<string, number>;
  pending: PendingSuggestion[];
  /**
   * The configured suggestions channel. A Discord jump link needs a channel as
   * well as a message, and the suggestion documents only store the message.
   */
  channel_id: string | null;
}

export interface MembersOverview {
  /** From the guild snapshot; null when no snapshot has been written yet. */
  total: number | null;
  joined_30d: number;
  left_30d: number;
  whitelisted: number;
  monthly: { month: string; joined: number }[];
  /**
   * When the guild snapshot was last written. ServerData refreshes on member
   * events, so a quiet server's totals lag - the UI says so rather than
   * presenting a stale number as current.
   */
  snapshot_at: string | null;
}

export interface DropsOverview {
  enabled: boolean;
  this_month: number;
  all_time: number;
  /** Category order is stable so colours never move between renders. */
  categories: string[];
  monthly: { month: string; counts: Record<string, number> }[];
}

export interface ContentDoc {
  exists: boolean;
  /** Guide pages, board responses, or 1/0 for the greeting. */
  count: number;
  updated_at: string | null;
  updated_by: string | null;
}

export interface ContentOverview {
  guide: ContentDoc;
  board: ContentDoc & { posted_channel_id: string | null; posted_at: string | null };
  greeting: ContentDoc;
}

/** One feature that has gone quiet: used during the baseline window, not once recently. */
export interface QuietFeature {
  feature: string;
  uses_before: number;
  last_used: string | null;
}

/**
 * Which parts of Codex are actually being used.
 *
 * Aggregate only - the underlying documents hold no user id at all, so nothing
 * here is personal data and no member can be profiled from it.
 *
 * `quiet` is the point of this section: features used during the baseline window
 * but not once in the recent one. That is the "I don't remember why I stopped
 * using those" list, which a popularity ranking buries.
 */
export interface FeatureUsageOverview {
  recent_days: number;
  baseline_days: number;
  total_uses: number;
  active_features: number;
  known_features: number;
  quiet: QuietFeature[];
  least_used: { feature: string; uses: number }[];
  top: { feature: string; uses: number }[];
}

export interface TrackersOverview {
  tag: { enabled: boolean; server_tag: string | null; wearing: number | null };
  boost: { count: number; tier: number | null };
}

/**
 * Everything the admin home renders, in one round trip.
 *
 * Every section is independently nullable: a section that fails returns null
 * rather than failing the whole page, so one slow or broken collection cannot
 * blank the dashboard.
 */
export interface GuildOverview {
  guild_id: string;
  features: FeatureStatus[];
  wyr: WyrOverview | null;
  suggestions: SuggestionsOverview | null;
  members: MembersOverview | null;
  drops: DropsOverview | null;
  content: ContentOverview | null;
  trackers: TrackersOverview | null;
  feature_usage: FeatureUsageOverview | null;
}

// ── Component V2 types ───────────────────────────────────────────────────

export type ComponentType =
  | "text"
  | "separator"
  | "section"
  | "action_row"
  | "container"
  | "media_gallery";

export interface ComponentDef {
  _id: string; // temp UUID for builder
  type: ComponentType;
  [key: string]: unknown;
}

export interface TextComponent extends ComponentDef {
  type: "text";
  content: string;
}

export interface SeparatorComponent extends ComponentDef {
  type: "separator";
}

export interface ThumbnailAccessory {
  type: "thumbnail";
  media: string;
}

export interface ButtonDef {
  type: "button";
  style: "primary" | "secondary" | "success" | "danger" | "link";
  label: string;
  emoji?: string;
  action?: string;
  target?: string;
  url?: string;
  params?: Record<string, string>;
}

export interface SectionComponent extends ComponentDef {
  type: "section";
  content: { type: "text"; content: string }[];
  accessory: ThumbnailAccessory | ButtonDef;
}

export interface SelectOptionDef {
  label: string;
  action?: string;
  target?: string;
  description?: string;
  emoji?: string;
}

export interface SelectDef {
  placeholder?: string;
  options: SelectOptionDef[];
  min_values?: number;
  max_values?: number;
}

export interface ActionRowComponent extends ComponentDef {
  type: "action_row";
  buttons?: ButtonDef[];
  select?: SelectDef;
}

export interface ContainerComponent extends ComponentDef {
  type: "container";
  accent_color?: string | number;
  spoiler?: boolean;
  components: ComponentDef[];
}

export interface MediaItem {
  media: string;
  description?: string;
  spoiler?: boolean;
}

export interface MediaGalleryComponent extends ComponentDef {
  type: "media_gallery";
  items: MediaItem[];
}

// ── Discord resources ────────────────────────────────────────────────────
// Channel and Role are engine-owned; re-exported at the top of this file.

// ── Guide page tree ──────────────────────────────────────────────────────

export interface GuidePage {
  id: string;
  label: string;
  description?: string;
  icon?: string;
  order?: number;
  content?: {
    components: ComponentDef[];
  };
  children?: GuidePage[];
}

export interface GuideData {
  accent_color?: string | number;
  pages: GuidePage[];
}

// ── Greeting ──────────────────────────────────────────────────────────────

export interface GreetingData {
  accent_color?: string | number;
  components: ComponentDef[];
}

// ── Info Board ───────────────────────────────────────────────────────────

/** One named private reply a board button or dropdown option can reveal. */
export interface BoardResponse {
  id: string;
  label?: string;
  accent_color?: string | number;
  components: ComponentDef[];
}

export interface BoardData {
  accent_color?: string | number;
  components: ComponentDef[];
  responses?: BoardResponse[];
}

/** Where the board is currently posted (read-only; posting stays with the bot). */
export interface BoardPosted {
  channel_id: string | null;
  message_id: string | null;
}

/** What a board button or option does. Mirrors board_actions.VALID_ACTIONS. */
export const BOARD_ACTIONS: Record<string, { label: string; description: string }> = {
  reply: { label: "Private reply", description: "Sends one of your responses, only the clicker sees it" },
  channel: { label: "Jump to channel", description: "Points the clicker at a channel" },
  role: { label: "Toggle role", description: "Gives or removes a self-assignable role" },
};

// ── Builder mode ─────────────────────────────────────────────────────────

export type BuilderMode = "guide" | "greeting" | "board";

// ── Simulation action ────────────────────────────────────────────────────

export interface SimulationAction {
  type:
    | "navigate"
    | "back"
    | "home"
    | "search"
    | "greeting_action"
    | "channel"
    | "role"
    | "board_reply";
  target?: string;
  action?: string;
}

// ── Greeting valid actions ────────────────────────────────────────────────

export const VALID_ACTIONS: Record<string, { description: string }> = {
  open_guide: { description: "Opens the server guide menu" },
  server_info: { description: "Shows server statistics" },
  channel_list: { description: "Shows channel overview" },
  getting_started: { description: "Shows getting started tips" },
  suggest: { description: "Opens the suggestion submission form" },
  browse_drops: { description: "Browse available free gaming drops" },
  server_rules: { description: "Shows link to server rules channel" },
  role_info: { description: "Shows server roles overview" },
};


// ── Audit log ────────────────────────────────────────────────────────────

export interface AuditLogEntry {
  guild_id: string;
  actor_id: string;
  actor_name: string;
  source: "discord" | "dashboard";
  section: string;
  key: string;
  old_value: unknown;
  new_value: unknown;
  action: "set" | "clear" | "toggle" | "create" | "remove";
  created_at: string;
}

export interface AuditLogResponse {
  entries: AuditLogEntry[];
  next_cursor: string | null;
}

/**
 * Totals over the whole audit log for one guild, independent of the page of
 * entries on screen. `by_source` and `by_section` only carry keys that actually
 * occur, so an untouched section is absent rather than zero.
 */
export interface AuditLogSummary {
  total: number;
  by_source: Record<string, number>;
  by_section: Record<string, number>;
  distinct_actors: number;
  oldest_at: string | null;
  retention_days: number;
}


// ── Settings ─────────────────────────────────────────────────────────────

// PanelRole is engine-owned (admin-only fleet-wide, no Mod tier); re-exported above.

export interface RolesSection {
  admin_role_ids: string[];
  tiers?: Record<string, unknown>;
}

export interface ServerSection {
  admin_channel_id: string | null;
}

export interface WyrSection {
  enabled: boolean;
  channel_id: string | null;
  ping_role_id: string | null;
  post_hour: number;
  post_minute: number;
  timezone: string;
  default_category: string;
  thread_name_format: string;
  thread_starter_message: string;
  thread_auto_archive: number;
  mapping_cleanup_days: number;
  subscribe_prompt_enabled: boolean;
  // Which bank the server draws from: "both" | "global_only" | "guild_only".
  question_source: string;
  // Which question formats the server posts. A list, not an enum -
  // "wyr" | "poll" | "open", any combination.
  question_formats: string[];
  submissions_enabled: boolean;
  submission_review_channel_id: string | null;
  submission_moderator_role_id: string | null;
  submission_max_pending: number;
  // Separate thread templates per format - one shared template cannot work,
  // because a saved WYR starter message hard-codes its {option_1} lines.
  thread_name_format_poll: string;
  thread_starter_message_poll: string;
  thread_name_format_open: string;
  thread_starter_message_open: string;
}

export interface NewMembersSection {
  enabled: boolean;
  account_age_requirement_days: number;
  auto_kick: boolean;
  greeting_channel_id: string | null;
  whitelist_role_id: string | null;
  whitelist_enabled: boolean;
  whitelist_role_name: string;
  greeting_enabled: boolean;
}

export interface AnnouncementSection {
  channel_id: string | null;
  thread_auto_create: boolean;
  thread_name_format: string;
  thread_auto_archive_duration: number;
  thread_welcome_message: string;
  auto_delete_threads: boolean;
}

export interface TagTrackerSection {
  enabled: boolean;
  server_tag: string | null;
  role_id: string | null;
}

export interface DropsSection {
  enabled: boolean;
  channel_id: string | null;
  tracker_channels: Record<string, string | null>;
  manager_role_id: string | null;
  post_hour: number;
  post_minute: number;
  timezone: string;
}

export interface SuggestionsSection {
  channel_id: string | null;
}

export interface BoostSection {
  enabled: boolean;
  channel_id: string | null;
}

export interface GuideSection {
  enabled: boolean;
  channel_id: string | null;
}

export interface GuildSettings {
  roles: RolesSection;
  server: ServerSection;
  wyr: WyrSection;
  new_members: NewMembersSection;
  announcement: AnnouncementSection;
  tag_tracker: TagTrackerSection;
  drops: DropsSection;
  suggestions: SuggestionsSection;
  boost: BoostSection;
  guide: GuideSection;
  setup_complete: boolean;
}

export type SettingsSection = keyof Omit<GuildSettings, "setup_complete">;

export type SettingsPatch = Partial<{
  [K in SettingsSection]: Partial<GuildSettings[K]>;
}>;

export interface SettingsResponse {
  config: GuildSettings;
  defaults: GuildSettings;
  panel_role: PanelRole;
}

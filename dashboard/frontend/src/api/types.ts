// ── User & Guild ──────────────────────────────────────────────────────────

import type { SessionUser } from "../_engine/api/types";

export interface User extends SessionUser {
  // codex's backend always populates these; narrow them back to non-null.
  username: string;
  discriminator: string;
  can_access_admin_any: boolean;
  can_access_settings_any: boolean;
}

export interface Guild {
  id: string;
  name: string;
  icon: string | null;
  bot_in_guild: boolean;
  has_config: boolean;
  setup_required: boolean;
  panel_role: PanelRole;
}

// ── User Activity ────────────────────────────────────────────────────────

export interface WyrActivity {
  total_votes: number;
  // Five options: the poll question format carries up to five answers.
  option_breakdown: {
    option1: number;
    option2: number;
    option3: number;
    option4: number;
    option5: number;
  };
  first_vote: string | null;
  last_vote: string | null;
  streak_active: boolean;
}

export interface SuggestionsActivity {
  submitted: number;
  votes_cast: number;
  by_status: Record<string, number>;
  last_activity: string | null;
}

export interface TagTrackerGuild {
  guild_id: string;
  guild_name: string;
  server_tag: string;
  has_role: boolean | null;
}

export interface BoostActivity {
  is_boosting: boolean;
  boosts: { guild_id: string; guild_name: string; boost_start: string | null }[];
}

export interface UserActivity {
  wyr: WyrActivity;
  suggestions: SuggestionsActivity;
  tag_tracker: TagTrackerGuild[];
  boost: BoostActivity;
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

export interface Channel {
  id: string;
  name: string;
  type: number;
  position: number;
}

export interface Role {
  id: string;
  name: string;
  color: number;
  position: number;
}

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


// ── Settings ─────────────────────────────────────────────────────────────

// The admin panel and dashboard are admin-only fleet-wide - there is no Mod tier.
export type PanelRole = "admin" | "none";

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

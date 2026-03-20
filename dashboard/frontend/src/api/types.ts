// ── User & Guild ──────────────────────────────────────────────────────────

export interface User {
  id: string;
  username: string;
  global_name: string | null;
  avatar: string | null;
  discriminator: string;
}

export interface Guild {
  id: string;
  name: string;
  icon: string | null;
  bot_in_guild: boolean;
  has_config: boolean;
  setup_required: boolean;
}

// ── User Activity ────────────────────────────────────────────────────────

export interface WyrActivity {
  total_votes: number;
  option_breakdown: { option1: number; option2: number; option3: number };
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

// ── Welcome ──────────────────────────────────────────────────────────────

export interface WelcomeData {
  accent_color?: string | number;
  components: ComponentDef[];
}

// ── Builder mode ─────────────────────────────────────────────────────────

export type BuilderMode = "guide" | "welcome";

// ── Simulation action ────────────────────────────────────────────────────

export interface SimulationAction {
  type: "navigate" | "back" | "home" | "search" | "welcome_action" | "channel" | "role";
  target?: string;
  action?: string;
}

// ── Welcome valid actions ────────────────────────────────────────────────

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

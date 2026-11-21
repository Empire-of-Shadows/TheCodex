import type { GuildSettings, SettingsSection } from "../../api/types";

/*
 * What a switched-on feature cannot run without (added 2026-11-20).
 *
 * The page shows each problem in red on the field that fixes it and keeps that
 * section's Save button off until it is fixed or the feature is switched off.
 * The server refuses the same saves with the same words: dashboard/routers/
 * settings.py `_requirement_errors`, whose comment cites the bot code each rule
 * was checked against. Change both together.
 *
 * Keys are the field names inside the section. A rule that either of two fields
 * can satisfy marks both: the full message on the first, "Or ..." on the second.
 */

export type FieldErrors = Record<string, string>;

function blank(v: unknown): boolean {
  return v === null || v === undefined || (typeof v === "string" && v.trim() === "");
}

/** Same words as dashboard/routers/settings.py NO_SERVER_TAGS. */
export const NO_SERVER_TAGS =
  "This server cannot have a server tag yet. Server tags are a boost perk: once " +
  "Discord unlocks them for this server, set your tag in Server Settings and then " +
  "switch the Tag Tracker on.";

/** Facts about the server the rules need beyond the draft itself. */
export interface RuleContext {
  /** GUILD_TAGS from Discord; null/undefined when unknown (never blocks). */
  tagTrackerAvailable?: boolean | null;
  /** The saved value: switching it OFF and back ON is not "switching on". */
  tagTrackerWasOn?: boolean;
}

export function sectionErrors(
  section: SettingsSection,
  d: GuildSettings,
  ctx: RuleContext = {},
): FieldErrors {
  const out: FieldErrors = {};
  switch (section) {
    case "wyr": {
      const s = d.wyr;
      if (s.enabled && blank(s.channel_id)) {
        out.channel_id = "Pick a WYR channel, or switch Would You Rather off.";
      }
      if (
        s.submissions_enabled &&
        blank(s.submission_review_channel_id) &&
        blank(s.submission_moderator_role_id)
      ) {
        out.submission_review_channel_id =
          "Pick a suggestion review channel or a reviewer role, or switch member suggestions off.";
        out.submission_moderator_role_id = "Or pick a reviewer role here.";
      }
      break;
    }
    case "new_members": {
      const s = d.new_members;
      if (s.enabled && s.greeting_enabled && blank(s.greeting_channel_id)) {
        out.greeting_channel_id = "Pick a greeting channel, or switch greeting messages off.";
      }
      if (
        s.enabled &&
        s.whitelist_enabled &&
        blank(s.whitelist_role_id) &&
        blank(s.whitelist_role_name)
      ) {
        out.whitelist_role_id =
          "Pick a whitelist role or type a name for one, or switch the whitelist system off.";
        out.whitelist_role_name = "Or type a name here and the role is created when it is first needed.";
      }
      break;
    }
    // No announcement rule: auto-create defaults on with no channel, which is
    // that feature's normal "off" state. See settings.py for the reasoning.
    case "drops":
      if (d.drops.enabled && blank(d.drops.channel_id)) {
        out.channel_id = "Pick a drops channel, or switch drops off.";
      }
      break;
    case "boost":
      if (d.boost.enabled && blank(d.boost.channel_id)) {
        out.channel_id = "Pick a boost log channel, or switch the Boost Tracker off.";
      }
      break;
    case "tag_tracker":
      // No tag-text rule (2026-11-20): members are matched by this server's id
      // and the bot fills the text in from whoever wears it.
      if (d.tag_tracker.enabled && blank(d.tag_tracker.role_id)) {
        out.role_id = "Pick a tag role, or switch the Tag Tracker off.";
      }
      if (d.tag_tracker.enabled && ctx.tagTrackerAvailable === false && !ctx.tagTrackerWasOn) {
        out.enabled = NO_SERVER_TAGS;
      }
      break;
    default:
      break;
  }
  return out;
}

/** The section-level messages, one per rule, for the save bar. */
export function sectionProblems(
  section: SettingsSection,
  d: GuildSettings,
  ctx: RuleContext = {},
): string[] {
  return Object.values(sectionErrors(section, d, ctx)).filter((m) => !m.startsWith("Or "));
}

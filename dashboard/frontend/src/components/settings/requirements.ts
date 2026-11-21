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

export function sectionErrors(section: SettingsSection, d: GuildSettings): FieldErrors {
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
    case "announcement":
      if (d.announcement.thread_auto_create && blank(d.announcement.channel_id)) {
        out.channel_id = "Pick an announcement channel, or switch Auto-Create Threads off.";
      }
      break;
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
      if (d.tag_tracker.enabled && blank(d.tag_tracker.server_tag)) {
        out.server_tag = "Type your server tag, or switch the Tag Tracker off.";
      }
      if (d.tag_tracker.enabled && blank(d.tag_tracker.role_id)) {
        out.role_id = "Pick a tag role, or switch the Tag Tracker off.";
      }
      break;
    default:
      break;
  }
  return out;
}

/** The section-level messages, one per rule, for the save bar. */
export function sectionProblems(section: SettingsSection, d: GuildSettings): string[] {
  return Object.values(sectionErrors(section, d)).filter((m) => !m.startsWith("Or "));
}

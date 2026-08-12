import { Link } from "react-router-dom";
import type {
  AnnouncementSection,
  BoostSection,
  Channel,
  DropsSection,
  GuideSection,
  NewMembersSection,
  Role,
  RolesSection,
  ServerSection,
  SuggestionsSection,
  TagTrackerSection,
  WyrSection,
} from "../../api/types";
import {
  ChannelField,
  Fieldset,
  FRow,
  MultiOptionField,
  MultiRoleField,
  OptionSelect,
  RoleField,
  TextareaField,
  TextField,
  ToggleField,
} from "./fields";
import {
  ACCOUNT_AGE_OPTIONS,
  ARCHIVE_OPTIONS,
  DROPS_TRACKER_BUCKETS,
  HOUR_OPTIONS,
  MINUTE_OPTIONS,
  PANEL_ACCESS_ROLE_MAX,
  TIMEZONE_OPTIONS,
  WYR_CATEGORY_OPTIONS,
  WYR_CLEANUP_OPTIONS,
  WYR_FORMAT_OPTIONS,
  WYR_MAX_PENDING_OPTIONS,
  WYR_SOURCE_OPTIONS,
} from "./options";

/*
 * The settings form, one component per rail section.
 *
 * Each component ships with a SEARCH_* array holding the labels and help text
 * of the fields it renders. That is what the rail search box matches against.
 * Keep the array next to the component and update both in the same edit - the
 * arrays are only used for search, so a stale one costs findability, not data.
 */

// ---------------------------------------------------------------------------
// Would You Rather
// ---------------------------------------------------------------------------

export const SEARCH_WYR = [
  "WYR Channel",
  "Ping Role",
  "Pinged on each post, and self-assignable by members. Leave blank for no ping.",
  "Enabled",
  "Notification Offer",
  "Offer the ping role to members who vote or check results without it.",
  "Where questions come from",
  "Shared questions are the pool every server draws from. Questions you add yourself stay private to this server.",
  "Question types this server posts",
  "A question of a type you have not ticked stays in the bank and is never posted. At least one type has to stay ticked.",
  "Let members suggest questions",
  "Suggestions go to a review channel first. Nothing reaches the daily post until someone approves it.",
  "Suggestion review channel",
  "Where member suggestions land to be approved or rejected.",
  "Who reviews suggestions",
  "Members with this role can approve or reject suggestions.",
  "Suggestions a member can have waiting",
  "Once a member has this many suggestions awaiting review, they wait for one to be handled before sending another.",
  "Post Hour",
  "Post Minute",
  "Timezone",
  "Default Category",
  "NSFW questions are only posted in age-restricted channels. If the WYR channel is not age-restricted, SFW questions are posted instead.",
  "Thread Name Format",
  "Starter Message",
  "Thread Name Format (question with answers)",
  "Starter Message (question with answers)",
  "Thread Name Format (open-ended)",
  "Starter Message (open-ended)",
  "Auto-Archive",
  "Mapping Cleanup",
  "Days before old message-question mappings are pruned.",
];

export function WyrSectionForm({
  value,
  channels,
  roles,
  onChange,
}: {
  value: WyrSection;
  channels: Channel[];
  roles: Role[];
  onChange: (v: WyrSection) => void;
}) {
  return (
    <>
      <Fieldset title="Posting">
        <FRow>
          <ToggleField
            label="Enabled"
            value={value.enabled}
            onChange={(v) => onChange({ ...value, enabled: v })}
          />
          <ToggleField
            label="Notification Offer"
            value={value.subscribe_prompt_enabled}
            onChange={(v) => onChange({ ...value, subscribe_prompt_enabled: v })}
            description="Offer the ping role to members who vote or check results without it."
          />
        </FRow>
        <FRow>
          <ChannelField
            label="WYR Channel"
            value={value.channel_id}
            channels={channels}
            filterType={0}
            onChange={(v) => onChange({ ...value, channel_id: v })}
          />
          <RoleField
            label="Ping Role"
            value={value.ping_role_id}
            roles={roles}
            onChange={(v) => onChange({ ...value, ping_role_id: v })}
            description="Pinged on each post, and self-assignable by members. Leave blank for no ping."
          />
        </FRow>
      </Fieldset>

      <Fieldset title="Schedule">
        <FRow>
          <OptionSelect<number>
            label="Post Hour"
            value={value.post_hour}
            options={HOUR_OPTIONS}
            onChange={(v) => onChange({ ...value, post_hour: v })}
          />
          <OptionSelect<number>
            label="Post Minute"
            value={value.post_minute}
            options={MINUTE_OPTIONS}
            onChange={(v) => onChange({ ...value, post_minute: v })}
          />
        </FRow>
        <FRow>
          <OptionSelect<string>
            label="Timezone"
            value={value.timezone}
            options={TIMEZONE_OPTIONS}
            onChange={(v) => onChange({ ...value, timezone: v })}
          />
          <OptionSelect<string>
            label="Default Category"
            value={value.default_category}
            options={WYR_CATEGORY_OPTIONS}
            onChange={(v) => onChange({ ...value, default_category: v })}
            description="NSFW questions are only posted in age-restricted channels. If the WYR channel is not age-restricted, SFW questions are posted instead."
          />
        </FRow>
      </Fieldset>

      <Fieldset title="Questions">
        <FRow>
          <OptionSelect<string>
            label="Where questions come from"
            value={value.question_source}
            options={WYR_SOURCE_OPTIONS}
            onChange={(v) => onChange({ ...value, question_source: v })}
            description="Shared questions are the pool every server draws from. Questions you add yourself stay private to this server."
          />
          <MultiOptionField<string>
            label="Question types this server posts"
            value={value.question_formats ?? []}
            options={WYR_FORMAT_OPTIONS}
            onChange={(v) => onChange({ ...value, question_formats: v })}
            requireOne
            description="A question of a type you have not ticked stays in the bank and is never posted. At least one type has to stay ticked."
          />
        </FRow>
      </Fieldset>

      <Fieldset title="Member suggestions">
        <FRow>
          <ToggleField
            label="Let members suggest questions"
            value={value.submissions_enabled}
            onChange={(v) => onChange({ ...value, submissions_enabled: v })}
            description="Suggestions go to a review channel first. Nothing reaches the daily post until someone approves it."
          />
          <OptionSelect<number>
            label="Suggestions a member can have waiting"
            value={value.submission_max_pending}
            options={WYR_MAX_PENDING_OPTIONS}
            onChange={(v) => onChange({ ...value, submission_max_pending: v })}
            description="Once a member has this many suggestions awaiting review, they wait for one to be handled before sending another."
          />
        </FRow>
        <FRow>
          <ChannelField
            label="Suggestion review channel"
            value={value.submission_review_channel_id}
            channels={channels}
            filterType={0}
            onChange={(v) => onChange({ ...value, submission_review_channel_id: v })}
            description="Where member suggestions land to be approved or rejected."
          />
          <RoleField
            label="Who reviews suggestions"
            value={value.submission_moderator_role_id}
            roles={roles}
            onChange={(v) => onChange({ ...value, submission_moderator_role_id: v })}
            description="Members with this role can approve or reject suggestions."
          />
        </FRow>
      </Fieldset>

      <Fieldset title="Discussion threads">
        <p className="muted" style={{ margin: 0 }}>
          Each question type gets its own thread wording, because a Would You Rather
          template lists its options and would leave empty numbering behind on a
          question that has different options or none.
        </p>
        <FRow full>
          <TextField
            label="Thread Name Format"
            value={value.thread_name_format}
            maxLength={100}
            onChange={(v) => onChange({ ...value, thread_name_format: v })}
            description="Placeholders: {date} {question_num} {category} {option_1} {option_2} {option_3} {question}"
          />
        </FRow>
        <FRow full>
          <TextareaField
            label="Starter Message"
            value={value.thread_starter_message}
            maxLength={500}
            onChange={(v) => onChange({ ...value, thread_starter_message: v })}
          />
        </FRow>
        <FRow full>
          <TextField
            label="Thread Name Format (question with answers)"
            value={value.thread_name_format_poll}
            maxLength={100}
            onChange={(v) => onChange({ ...value, thread_name_format_poll: v })}
            description="Placeholders: {date} {question_num} {category} {option_1} to {option_5} {question}"
          />
        </FRow>
        <FRow full>
          <TextareaField
            label="Starter Message (question with answers)"
            value={value.thread_starter_message_poll}
            maxLength={500}
            onChange={(v) => onChange({ ...value, thread_starter_message_poll: v })}
          />
        </FRow>
        <FRow full>
          <TextField
            label="Thread Name Format (open-ended)"
            value={value.thread_name_format_open}
            maxLength={100}
            onChange={(v) => onChange({ ...value, thread_name_format_open: v })}
            description="Placeholders: {date} {question_num} {category} {question} - an open-ended question has no options."
          />
        </FRow>
        <FRow full>
          <TextareaField
            label="Starter Message (open-ended)"
            value={value.thread_starter_message_open}
            maxLength={500}
            onChange={(v) => onChange({ ...value, thread_starter_message_open: v })}
          />
        </FRow>
        <FRow>
          <OptionSelect<number>
            label="Auto-Archive"
            value={value.thread_auto_archive}
            options={ARCHIVE_OPTIONS}
            onChange={(v) => onChange({ ...value, thread_auto_archive: v })}
          />
          <OptionSelect<number>
            label="Mapping Cleanup"
            value={value.mapping_cleanup_days}
            options={WYR_CLEANUP_OPTIONS}
            onChange={(v) => onChange({ ...value, mapping_cleanup_days: v })}
            description="Days before old message-question mappings are pruned."
          />
        </FRow>
      </Fieldset>
    </>
  );
}

// ---------------------------------------------------------------------------
// New members
// ---------------------------------------------------------------------------

export const SEARCH_NEW_MEMBERS = [
  "Greeting Channel",
  "Whitelist Role",
  "Account Age Requirement",
  "System Enabled",
  "Master toggle for new-member processing.",
  "Auto-Kick Underage Accounts",
  "Greeting Messages",
  "Whitelist System",
  "Whitelist Role Name",
  "Used when auto-creating the whitelist role if one is not set above.",
];

export function NewMembersSectionForm({
  guildId,
  value,
  channels,
  roles,
  onChange,
}: {
  guildId: string;
  value: NewMembersSection;
  channels: Channel[];
  roles: Role[];
  onChange: (v: NewMembersSection) => void;
}) {
  return (
    <>
      <Fieldset title="Screening">
        <FRow>
          <ToggleField
            label="System Enabled"
            value={value.enabled}
            onChange={(v) => onChange({ ...value, enabled: v })}
            description="Master toggle for new-member processing."
          />
          <ToggleField
            label="Auto-Kick Underage Accounts"
            value={value.auto_kick}
            onChange={(v) => onChange({ ...value, auto_kick: v })}
          />
        </FRow>
        <FRow>
          <OptionSelect<number>
            label="Account Age Requirement"
            value={value.account_age_requirement_days}
            options={ACCOUNT_AGE_OPTIONS}
            onChange={(v) => onChange({ ...value, account_age_requirement_days: v })}
          />
        </FRow>
      </Fieldset>

      <Fieldset title="Greeting">
        <FRow>
          <ToggleField
            label="Greeting Messages"
            value={value.greeting_enabled}
            onChange={(v) => onChange({ ...value, greeting_enabled: v })}
          />
          <ChannelField
            label="Greeting Channel"
            value={value.greeting_channel_id}
            channels={channels}
            filterType={0}
            onChange={(v) => onChange({ ...value, greeting_channel_id: v })}
          />
        </FRow>
        <p className="muted" style={{ margin: 0 }}>
          What the greeting actually says is put together in the{" "}
          <Link to={`/builder/${guildId}?mode=greeting`}>builder</Link>.
        </p>
      </Fieldset>

      <Fieldset title="Starter role">
        <FRow>
          <ToggleField
            label="Whitelist System"
            value={value.whitelist_enabled}
            onChange={(v) => onChange({ ...value, whitelist_enabled: v })}
          />
          <RoleField
            label="Whitelist Role"
            value={value.whitelist_role_id}
            roles={roles}
            onChange={(v) => onChange({ ...value, whitelist_role_id: v })}
          />
        </FRow>
        <FRow>
          <TextField
            label="Whitelist Role Name"
            value={value.whitelist_role_name}
            maxLength={100}
            onChange={(v) => onChange({ ...value, whitelist_role_name: v })}
            description="Used when auto-creating the whitelist role if one is not set above."
          />
        </FRow>
      </Fieldset>
    </>
  );
}

// ---------------------------------------------------------------------------
// Suggestions (plus the server-wide admin channel, which is the staff copy)
// ---------------------------------------------------------------------------

export const SEARCH_SUGGESTIONS = [
  "Suggestion Channel",
  "Admin Channel",
  "Channel used for admin notifications and alerts.",
];

export function SuggestionsSectionForm({
  value,
  server,
  channels,
  onChange,
  onServerChange,
}: {
  value: SuggestionsSection;
  server: ServerSection;
  channels: Channel[];
  onChange: (v: SuggestionsSection) => void;
  onServerChange: (v: ServerSection) => void;
}) {
  return (
    <Fieldset title="Where suggestions go">
      <FRow>
        <ChannelField
          label="Suggestion Channel"
          value={value.channel_id}
          channels={channels}
          filterType={0}
          onChange={(v) => onChange({ ...value, channel_id: v })}
        />
        <ChannelField
          label="Admin Channel"
          value={server.admin_channel_id}
          channels={channels}
          filterType={0}
          onChange={(v) => onServerChange({ ...server, admin_channel_id: v })}
          description="Channel used for admin notifications and alerts."
        />
      </FRow>
    </Fieldset>
  );
}

// ---------------------------------------------------------------------------
// Updates and drops
// ---------------------------------------------------------------------------

export const SEARCH_DROPS = [
  "Drops Channel",
  "Manager Role",
  "Role allowed to manage drops via /drop.",
  "Enabled",
  "Updates",
  "Free",
  "Prime",
  "Post Hour",
  "Post Minute",
  "Timezone",
  "Tracker Channels",
];

export function DropsSectionForm({
  value,
  channels,
  roles,
  onChange,
}: {
  value: DropsSection;
  channels: Channel[];
  roles: Role[];
  onChange: (v: DropsSection) => void;
}) {
  const tracker = value.tracker_channels ?? {};
  return (
    <>
      <Fieldset title="Posting">
        <FRow>
          <ToggleField
            label="Enabled"
            value={value.enabled}
            onChange={(v) => onChange({ ...value, enabled: v })}
          />
          <ChannelField
            label="Drops Channel"
            value={value.channel_id}
            channels={channels}
            filterType={0}
            onChange={(v) => onChange({ ...value, channel_id: v })}
          />
        </FRow>
        <FRow>
          <RoleField
            label="Manager Role"
            value={value.manager_role_id}
            roles={roles}
            onChange={(v) => onChange({ ...value, manager_role_id: v })}
            description="Role allowed to manage drops via /drop."
          />
        </FRow>
      </Fieldset>

      <Fieldset title="Tracker Channels">
        <p className="muted" style={{ margin: 0 }}>
          Each of these keeps its own running list in the channel you pick, so
          members can scroll back through one kind of drop without the others in
          the way. Leave one blank to skip it.
        </p>
        <FRow>
          {DROPS_TRACKER_BUCKETS.map((bucket) => (
            <ChannelField
              key={bucket}
              label={bucket}
              value={tracker[bucket] ?? null}
              channels={channels}
              filterType={0}
              onChange={(v) =>
                onChange({
                  ...value,
                  tracker_channels: { ...tracker, [bucket]: v },
                })
              }
            />
          ))}
        </FRow>
      </Fieldset>

      <Fieldset title="Schedule">
        <FRow>
          <OptionSelect<number>
            label="Post Hour"
            value={value.post_hour}
            options={HOUR_OPTIONS}
            onChange={(v) => onChange({ ...value, post_hour: v })}
          />
          <OptionSelect<number>
            label="Post Minute"
            value={value.post_minute}
            options={MINUTE_OPTIONS}
            onChange={(v) => onChange({ ...value, post_minute: v })}
          />
        </FRow>
        <FRow>
          <OptionSelect<string>
            label="Timezone"
            value={value.timezone}
            options={TIMEZONE_OPTIONS}
            onChange={(v) => onChange({ ...value, timezone: v })}
          />
        </FRow>
      </Fieldset>
    </>
  );
}

// ---------------------------------------------------------------------------
// Announcements
// ---------------------------------------------------------------------------

export const SEARCH_ANNOUNCEMENT = [
  "Announcement Channel",
  "Auto-Archive",
  "Auto-Create Threads",
  "Auto-Delete Threads",
  "Delete the discussion thread when the announcement is deleted.",
  "Thread Name Format",
  "Thread Welcome Message",
];

export function AnnouncementSectionForm({
  value,
  channels,
  onChange,
}: {
  value: AnnouncementSection;
  channels: Channel[];
  onChange: (v: AnnouncementSection) => void;
}) {
  return (
    <>
      <Fieldset title="Threads on announcements">
        <FRow>
          <ToggleField
            label="Auto-Create Threads"
            value={value.thread_auto_create}
            onChange={(v) => onChange({ ...value, thread_auto_create: v })}
          />
          <ToggleField
            label="Auto-Delete Threads"
            value={value.auto_delete_threads}
            onChange={(v) => onChange({ ...value, auto_delete_threads: v })}
            description="Delete the discussion thread when the announcement is deleted."
          />
        </FRow>
        <FRow>
          <ChannelField
            label="Announcement Channel"
            value={value.channel_id}
            channels={channels}
            filterType={0}
            onChange={(v) => onChange({ ...value, channel_id: v })}
          />
          <OptionSelect<number>
            label="Auto-Archive"
            value={value.thread_auto_archive_duration}
            options={ARCHIVE_OPTIONS}
            onChange={(v) => onChange({ ...value, thread_auto_archive_duration: v })}
          />
        </FRow>
      </Fieldset>

      <Fieldset title="Thread wording">
        <FRow full>
          <TextField
            label="Thread Name Format"
            value={value.thread_name_format}
            maxLength={100}
            onChange={(v) => onChange({ ...value, thread_name_format: v })}
            description="Placeholders: {message_content} {author_name} {channel_name}"
          />
        </FRow>
        <FRow full>
          <TextareaField
            label="Thread Welcome Message"
            value={value.thread_welcome_message}
            maxLength={500}
            onChange={(v) => onChange({ ...value, thread_welcome_message: v })}
          />
        </FRow>
      </Fieldset>
    </>
  );
}

// ---------------------------------------------------------------------------
// Guide and board
// ---------------------------------------------------------------------------

export const SEARCH_GUIDE = [
  "Guide Channel",
  "Optional - restrict /guide invocation to this channel.",
  "Enabled",
  "Info board",
];

export function GuideSectionForm({
  guildId,
  value,
  channels,
  onChange,
}: {
  guildId: string;
  value: GuideSection;
  channels: Channel[];
  onChange: (v: GuideSection) => void;
}) {
  return (
    <Fieldset title="Guide">
      <FRow>
        <ToggleField
          label="Enabled"
          value={value.enabled}
          onChange={(v) => onChange({ ...value, enabled: v })}
        />
        <ChannelField
          label="Guide Channel"
          value={value.channel_id}
          channels={channels}
          filterType={0}
          onChange={(v) => onChange({ ...value, channel_id: v })}
          description="Optional - restrict /guide invocation to this channel."
        />
      </FRow>
      <p className="muted" style={{ margin: 0 }}>
        Guide content (pages, components) is managed in the{" "}
        <Link to={`/builder/${guildId}`}>builder</Link>. The info board, the posted
        message with buttons that open private answers, is built{" "}
        <Link to={`/builder/${guildId}?mode=board`}>there too</Link>.
      </p>
    </Fieldset>
  );
}

// ---------------------------------------------------------------------------
// Trackers
// ---------------------------------------------------------------------------

export const SEARCH_TRACKERS = [
  "Server Tag",
  "The exact server tag string members must wear to qualify.",
  "Tag Role",
  "Role granted to members wearing the tag.",
  "Enabled",
  "Boost Log Channel",
  "Tag Tracker",
  "Boost Tracker",
];

export function TrackersSectionForm({
  tag,
  boost,
  channels,
  roles,
  onTagChange,
  onBoostChange,
}: {
  tag: TagTrackerSection;
  boost: BoostSection;
  channels: Channel[];
  roles: Role[];
  onTagChange: (v: TagTrackerSection) => void;
  onBoostChange: (v: BoostSection) => void;
}) {
  return (
    <>
      <Fieldset title="Tag Tracker">
        <p className="muted" style={{ margin: 0 }}>
          Gives a role to every member who is wearing your server tag, and takes
          it back when they stop.
        </p>
        <FRow>
          <ToggleField
            label="Enabled"
            value={tag.enabled}
            onChange={(v) => onTagChange({ ...tag, enabled: v })}
          />
          <TextField
            label="Server Tag"
            value={tag.server_tag ?? ""}
            maxLength={32}
            onChange={(v) => onTagChange({ ...tag, server_tag: v || null })}
            description="The exact server tag string members must wear to qualify."
          />
        </FRow>
        <FRow>
          <RoleField
            label="Tag Role"
            value={tag.role_id}
            roles={roles}
            onChange={(v) => onTagChange({ ...tag, role_id: v })}
            description="Role granted to members wearing the tag."
          />
        </FRow>
      </Fieldset>

      <Fieldset title="Boost Tracker">
        <p className="muted" style={{ margin: 0 }}>
          Posts a note in the channel you pick whenever someone boosts the server.
        </p>
        <FRow>
          <ToggleField
            label="Enabled"
            value={boost.enabled}
            onChange={(v) => onBoostChange({ ...boost, enabled: v })}
          />
          <ChannelField
            label="Boost Log Channel"
            value={boost.channel_id}
            channels={channels}
            filterType={0}
            onChange={(v) => onBoostChange({ ...boost, channel_id: v })}
          />
        </FRow>
      </Fieldset>
    </>
  );
}

// ---------------------------------------------------------------------------
// Who can manage
// ---------------------------------------------------------------------------

export const SEARCH_PANEL_ACCESS = [
  "Panel Access Roles",
  "Full admin access (acts like Manage Server).",
  "Who can manage",
];

export function PanelAccessSectionForm({
  value,
  roles,
  onChange,
}: {
  value: RolesSection;
  roles: Role[];
  onChange: (v: RolesSection) => void;
}) {
  return (
    <Fieldset title="Panel access roles">
      <FRow full>
        <MultiRoleField
          label="Panel Access Roles"
          description="Full admin access (acts like Manage Server)."
          value={value.admin_role_ids ?? []}
          roles={roles}
          max={PANEL_ACCESS_ROLE_MAX}
          onChange={(v) => onChange({ ...value, admin_role_ids: v })}
        />
      </FRow>
    </Fieldset>
  );
}

import { Component, type ReactNode } from "react";
import type {
  Channel,
  GuildOverview,
  GuildSettings,
  Role,
} from "../../api/types";
import { optionLabel, TIMEZONE_OPTIONS } from "../../_engine/components/settings/options";
import {
  PANEL_ACCESS_ROLE_MAX,
  WYR_CATEGORY_OPTIONS,
  WYR_FORMAT_OPTIONS,
  WYR_SOURCE_OPTIONS,
} from "./options";

/*
 * The right-hand column: what the selected feature is doing right now.
 *
 * Two sources feed it. The settings response is always there, so the "what is
 * configured" rows always render. The guild overview endpoint is optional - it
 * can fail or come back with null sections, and when it does those rows are
 * simply left out. Nothing here may throw when `overview` is null.
 */

function KvCard({
  title,
  rows,
  footer,
}: {
  title: string;
  rows: [string, string][];
  footer?: string;
}) {
  if (rows.length === 0 && !footer) return null;
  return (
    <div className="ov-card">
      <div className="ov-card__head">
        <span className="ov-card__title">{title}</span>
      </div>
      <div>
        {rows.map(([k, v]) => (
          <div className="ov-kv" key={k}>
            <span className="ov-kv__k">{k}</span>
            <span className="ov-kv__v">{v}</span>
          </div>
        ))}
      </div>
      {footer && <p className="ov-muted" style={{ margin: 0 }}>{footer}</p>}
    </div>
  );
}

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

function onOff(v: boolean): string {
  return v ? "On" : "Off";
}

function whenText(iso: string | null): string {
  if (!iso) return "Not yet";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "Not yet";
  return d.toLocaleString();
}

interface ContextProps {
  slug: string;
  draft: GuildSettings;
  channels: Channel[];
  roles: Role[];
  overview: GuildOverview | null;
}

/**
 * The settings form must survive anything the overview endpoint does.
 *
 * The types say every field is there once a section is non-null, but the
 * endpoint is new. If a section comes back a shape short, this column goes
 * quiet instead of taking the whole page down with it.
 */
class ContextBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (this.state.failed) {
      return (
        <div className="ov-card ov-card--quiet">
          <p className="ov-muted" style={{ margin: 0 }}>
            Live details could not be shown right now. Your settings below are
            unaffected.
          </p>
        </div>
      );
    }
    return this.props.children;
  }
}

export default function ContextColumn(props: ContextProps) {
  return (
    <ContextBoundary>
      <ContextBody {...props} />
    </ContextBoundary>
  );
}

function ContextBody({ slug, draft, channels, roles, overview }: ContextProps) {
  const channelName = (id: string | null | undefined): string => {
    if (!id) return "Not set";
    const hit = channels.find((c) => c.id === id);
    return hit ? `#${hit.name}` : "Already set";
  };
  const roleName = (id: string | null | undefined): string => {
    if (!id) return "Not set";
    const hit = roles.find((r) => r.id === id);
    return hit ? hit.name : "Already set";
  };

  if (slug === "wyr") {
    const w = draft.wyr;
    const formats = (w.question_formats ?? [])
      .map((f) => optionLabel(WYR_FORMAT_OPTIONS, f))
      .join(", ");
    const rows: [string, string][] = [
      ["Posting", onOff(w.enabled)],
      ["Channel", channelName(w.channel_id)],
      [
        "Posts at",
        `${pad2(w.post_hour)}:${pad2(w.post_minute)} ${optionLabel(TIMEZONE_OPTIONS, w.timezone)}`,
      ],
      ["Question types", formats || "None ticked"],
      ["Draws from", optionLabel(WYR_SOURCE_OPTIONS, w.question_source)],
      ["Content", optionLabel(WYR_CATEGORY_OPTIONS, w.default_category)],
      ["Member suggestions", onOff(w.submissions_enabled)],
    ];
    const ov = overview?.wyr ?? null;
    const liveRows: [string, string][] = [];
    if (ov) {
      liveRows.push([
        "Posted today",
        ov.today ? `${ov.today.votes} votes from ${ov.today.voters} members` : "Nothing yet",
      ]);
      liveRows.push(["Next post", whenText(ov.next_post_at)]);
      liveRows.push(["Days posted (30d)", String(ov.days_posted_30d)]);
      liveRows.push(["Shared questions", String(ov.bank.global)]);
      liveRows.push(["This server's questions", String(ov.bank.guild)]);
      if (ov.bank.unpostable > 0) {
        liveRows.push(["Cannot be posted", String(ov.bank.unpostable)]);
      }
      liveRows.push(["Suggestions waiting", String(ov.submissions_pending)]);
    }
    return (
      <>
        <KvCard title="Set up" rows={rows} />
        <KvCard
          title="Right now"
          rows={liveRows}
          footer={
            ov && ov.bank.unpostable > 0
              ? "Questions that cannot be posted are of a type this server has turned off."
              : undefined
          }
        />
      </>
    );
  }

  if (slug === "new_members") {
    const n = draft.new_members;
    const rows: [string, string][] = [
      ["Screening", onOff(n.enabled)],
      ["Minimum account age", `${n.account_age_requirement_days} days`],
      ["Kicks accounts that are too new", n.auto_kick ? "Yes" : "No"],
      ["Greeting", onOff(n.greeting_enabled)],
      ["Greeting channel", channelName(n.greeting_channel_id)],
      ["Starter role", n.whitelist_enabled ? roleName(n.whitelist_role_id) : "Off"],
    ];
    const ov = overview?.members ?? null;
    const liveRows: [string, string][] = [];
    if (ov) {
      if (ov.total !== null) liveRows.push(["Members", String(ov.total)]);
      liveRows.push(["Joined (30d)", String(ov.joined_30d)]);
      liveRows.push(["Left (30d)", String(ov.left_30d)]);
      liveRows.push(["Have the starter role", String(ov.whitelisted)]);
    }
    return (
      <>
        <KvCard title="Set up" rows={rows} />
        <KvCard
          title="Right now"
          rows={liveRows}
          footer={
            ov && ov.snapshot_at
              ? `Counts last refreshed ${whenText(ov.snapshot_at)}.`
              : undefined
          }
        />
      </>
    );
  }

  if (slug === "suggestions") {
    const rows: [string, string][] = [
      ["Suggestion channel", channelName(draft.suggestions.channel_id)],
      ["Staff copy channel", channelName(draft.server.admin_channel_id)],
    ];
    const ov = overview?.suggestions ?? null;
    const liveRows: [string, string][] = [];
    if (ov) {
      liveRows.push(["Suggestions received", String(ov.total)]);
      liveRows.push(["Waiting on a decision", String(ov.pending.length)]);
      Object.entries(ov.by_status).forEach(([status, count]) => {
        liveRows.push([status.charAt(0).toUpperCase() + status.slice(1), String(count)]);
      });
    }
    return (
      <>
        <KvCard title="Set up" rows={rows} />
        <KvCard title="Right now" rows={liveRows} />
      </>
    );
  }

  if (slug === "drops") {
    const d = draft.drops;
    const tracker = d.tracker_channels ?? {};
    const rows: [string, string][] = [
      ["Posting", onOff(d.enabled)],
      ["Channel", channelName(d.channel_id)],
      [
        "Posts at",
        `${pad2(d.post_hour)}:${pad2(d.post_minute)} ${optionLabel(TIMEZONE_OPTIONS, d.timezone)}`,
      ],
      ["Can manage drops", roleName(d.manager_role_id)],
      ["Updates list", channelName(tracker.Updates ?? null)],
      ["Free list", channelName(tracker.Free ?? null)],
      ["Prime list", channelName(tracker.Prime ?? null)],
    ];
    const ov = overview?.drops ?? null;
    const liveRows: [string, string][] = [];
    if (ov) {
      liveRows.push(["Posted this month", String(ov.this_month)]);
      liveRows.push(["Posted all time", String(ov.all_time)]);
    }
    return (
      <>
        <KvCard title="Set up" rows={rows} />
        <KvCard title="Right now" rows={liveRows} />
      </>
    );
  }

  if (slug === "announcement") {
    const a = draft.announcement;
    const rows: [string, string][] = [
      ["Threads open automatically", onOff(a.thread_auto_create)],
      ["Channel watched", channelName(a.channel_id)],
      ["Thread goes quiet after", `${Math.round(a.thread_auto_archive_duration / 60)} hours`],
      ["Thread removed with the post", a.auto_delete_threads ? "Yes" : "No"],
    ];
    return <KvCard title="Set up" rows={rows} />;
  }

  if (slug === "guide") {
    const g = draft.guide;
    const rows: [string, string][] = [
      ["Guide available", onOff(g.enabled)],
      ["Restricted to", channelName(g.channel_id)],
    ];
    const ov = overview?.content ?? null;
    const liveRows: [string, string][] = [];
    if (ov) {
      liveRows.push([
        "Guide pages",
        ov.guide.exists ? String(ov.guide.count) : "Nothing written yet",
      ]);
      liveRows.push(["Guide last edited", whenText(ov.guide.updated_at)]);
      liveRows.push([
        "Board answers",
        ov.board.exists ? String(ov.board.count) : "Nothing written yet",
      ]);
      liveRows.push(["Board posted in", channelName(ov.board.posted_channel_id)]);
    }
    return (
      <>
        <KvCard title="Set up" rows={rows} />
        <KvCard title="Right now" rows={liveRows} />
      </>
    );
  }

  if (slug === "trackers") {
    const t = draft.tag_tracker;
    const b = draft.boost;
    const rows: [string, string][] = [
      ["Tag tracking", onOff(t.enabled)],
      ["Tag members must wear", t.server_tag ? t.server_tag : "Not set"],
      ["Role it grants", roleName(t.role_id)],
      ["Boost log", onOff(b.enabled)],
      ["Boost log channel", channelName(b.channel_id)],
    ];
    const ov = overview?.trackers ?? null;
    const liveRows: [string, string][] = [];
    if (ov) {
      if (ov.tag.wearing !== null) liveRows.push(["Wearing the tag", String(ov.tag.wearing)]);
      liveRows.push(["Boosts", String(ov.boost.count)]);
      if (ov.boost.tier !== null) liveRows.push(["Boost level", String(ov.boost.tier)]);
    }
    return (
      <>
        <KvCard title="Set up" rows={rows} />
        <KvCard title="Right now" rows={liveRows} />
      </>
    );
  }

  if (slug === "panel_access") {
    const ids = draft.roles.admin_role_ids ?? [];
    const rows: [string, string][] = [
      ["Roles with access", `${ids.length} of ${PANEL_ACCESS_ROLE_MAX}`],
    ];
    ids.forEach((id, i) => {
      rows.push([`Role ${i + 1}`, roleName(id)]);
    });
    return (
      <KvCard
        title="Set up"
        rows={rows}
        footer="Anyone with Manage Server already has full access, with or without these roles."
      />
    );
  }

  return null;
}

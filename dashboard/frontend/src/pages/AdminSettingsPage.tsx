import { Fragment, useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import type {
  Channel,
  GuildOverview,
  GuildSettings,
  Role,
  SettingsPatch,
  SettingsResponse,
  SettingsSection,
} from "../api/types";
import AppHeader from "../components/AppHeader";
import ConfirmDialog from "../components/ConfirmDialog";
import { formatError } from "../_engine/api/formatError";
import { PickerStatusProvider } from "../_engine/components/settings/fields";
import ContextColumn from "../components/settings/ContextColumn";
import {
  AnnouncementSectionForm,
  DropsSectionForm,
  GuideSectionForm,
  NewMembersSectionForm,
  PanelAccessSectionForm,
  SEARCH_ANNOUNCEMENT,
  SEARCH_DROPS,
  SEARCH_GUIDE,
  SEARCH_NEW_MEMBERS,
  SEARCH_PANEL_ACCESS,
  SEARCH_SUGGESTIONS,
  SEARCH_TRACKERS,
  SEARCH_WYR,
  SuggestionsSectionForm,
  TrackersSectionForm,
  WyrSectionForm,
} from "../components/settings/sections";

/*
 * Admin settings.
 *
 * The nine-tab strip this replaced sat over one full-bleed card, so a section
 * holding a single dropdown put a 220px select alone in a box as wide as the
 * monitor. The layout is now a rail (grouped navigation plus a search box), a
 * reading-width form column, and a context column showing what the selected
 * feature is actually doing.
 *
 * The save model is unchanged and deliberately uniform: nothing autosaves,
 * every config section has its own Save button, and saving one section leaves
 * unsaved edits in the others alone.
 */

// ---------------------------------------------------------------------------
// Rail definition
// ---------------------------------------------------------------------------

type Slug =
  | "wyr"
  | "new_members"
  | "suggestions"
  | "drops"
  | "announcement"
  | "guide"
  | "trackers"
  | "panel_access";

interface RailItem {
  slug: Slug;
  /** Rail label. */
  label: string;
  /** Heading over the form column. */
  title: string;
  /** Plain-language description of what the feature does for members. */
  blurb: string;
  /** Config sections this rail entry saves, each with its own button. */
  saves: { section: SettingsSection; label: string }[];
  /** Field labels and help text, for the rail search box. */
  search: string[];
}

const RAIL_GROUPS: { name: string; items: RailItem[] }[] = [
  {
    name: "Server",
    items: [
      {
        slug: "wyr",
        label: "Would You Rather",
        title: "Would You Rather",
        blurb:
          "Posts a question in your chosen channel on a schedule and opens a thread underneath it. Members vote with buttons, argue about it in the thread, and can opt in to a ping whenever a new one goes up.",
        saves: [{ section: "wyr", label: "Save" }],
        search: SEARCH_WYR,
      },
      {
        slug: "new_members",
        label: "New members",
        title: "New members",
        blurb:
          "Checks how old an account is before it can settle in, welcomes people who join, and can hand out a starter role automatically.",
        saves: [{ section: "new_members", label: "Save" }],
        search: SEARCH_NEW_MEMBERS,
      },
      {
        slug: "suggestions",
        label: "Suggestions",
        title: "Suggestions",
        blurb:
          "Members send an idea with a command, it gets posted where everyone can vote on it, and a thread opens underneath for discussion. Staff can get their own copy in a private channel.",
        saves: [
          { section: "suggestions", label: "Save suggestions" },
          { section: "server", label: "Save admin channel" },
        ],
        search: SEARCH_SUGGESTIONS,
      },
      {
        slug: "drops",
        label: "Updates and drops",
        title: "Updates and drops",
        blurb:
          "Posts the day's free games and loot drops in your chosen channel, and can keep a separate running list for each kind so members can scroll back through one without the others in the way.",
        saves: [{ section: "drops", label: "Save" }],
        search: SEARCH_DROPS,
      },
      {
        slug: "announcement",
        label: "Announcements",
        title: "Announcements",
        blurb:
          "Watches your announcement channel and opens a discussion thread under each post, so replies stay together instead of burying the announcement itself.",
        saves: [{ section: "announcement", label: "Save" }],
        search: SEARCH_ANNOUNCEMENT,
      },
      {
        slug: "guide",
        label: "Guide and board",
        title: "Guide and board",
        blurb:
          "The guide is a set of pages members browse with a command. The info board is a message you post once, with buttons that show each member a private answer.",
        saves: [{ section: "guide", label: "Save" }],
        search: SEARCH_GUIDE,
      },
      {
        slug: "trackers",
        label: "Trackers",
        title: "Trackers",
        blurb:
          "Two small watchers. One gives a role to members who wear your server tag and takes it back when they stop. The other posts a note whenever someone boosts the server.",
        saves: [
          { section: "tag_tracker", label: "Save Tag Tracker" },
          { section: "boost", label: "Save Boost Tracker" },
        ],
        search: SEARCH_TRACKERS,
      },
    ],
  },
  {
    name: "Access",
    items: [
      {
        slug: "panel_access",
        label: "Who can manage",
        title: "Who can manage",
        blurb:
          "Members holding any of these roles get the same access to the admin panel and this dashboard as someone with Manage Server. Everyone else sees nothing here.",
        saves: [{ section: "roles", label: "Save" }],
        search: SEARCH_PANEL_ACCESS,
      },
    ],
  },
];

const RAIL_ITEMS: RailItem[] = RAIL_GROUPS.flatMap((g) => g.items);

const DEFAULT_SLUG: Slug = "wyr";

function parseSlug(raw: string | null): Slug {
  const hit = RAIL_ITEMS.find((i) => i.slug === raw);
  return hit ? hit.slug : DEFAULT_SLUG;
}

/** Terms that reach the audit-log link in the rail search. */
const AUDIT_LOG_SEARCH = [
  "Audit log",
  "History of changes",
  "Who changed a setting and when",
];

// ---------------------------------------------------------------------------
// Rail badges
// ---------------------------------------------------------------------------

type BadgeTone = "ok" | "warn" | "";

interface Badge {
  text: string;
  tone: BadgeTone;
}

/**
 * What the rail badge says about a feature.
 *
 * "Set up" is the load-bearing one: switched on but missing something it
 * cannot run without, which is the state that looks fine and silently does
 * nothing.
 */
function railBadge(slug: Slug, d: GuildSettings): Badge {
  switch (slug) {
    case "wyr":
      if (!d.wyr.enabled) return { text: "Off", tone: "" };
      return d.wyr.channel_id
        ? { text: "On", tone: "ok" }
        : { text: "Set up", tone: "warn" };
    case "new_members": {
      if (!d.new_members.enabled) return { text: "Off", tone: "" };
      const greetingGap =
        d.new_members.greeting_enabled && !d.new_members.greeting_channel_id;
      const roleGap =
        d.new_members.whitelist_enabled &&
        !d.new_members.whitelist_role_id &&
        !d.new_members.whitelist_role_name;
      return greetingGap || roleGap
        ? { text: "Set up", tone: "warn" }
        : { text: "On", tone: "ok" };
    }
    case "suggestions":
      return d.suggestions.channel_id
        ? { text: "On", tone: "ok" }
        : { text: "Off", tone: "" };
    case "drops":
      if (!d.drops.enabled) return { text: "Off", tone: "" };
      return d.drops.channel_id
        ? { text: "On", tone: "ok" }
        : { text: "Set up", tone: "warn" };
    case "announcement":
      if (!d.announcement.thread_auto_create) return { text: "Off", tone: "" };
      return d.announcement.channel_id
        ? { text: "On", tone: "ok" }
        : { text: "Set up", tone: "warn" };
    case "guide":
      return d.guide.enabled ? { text: "On", tone: "ok" } : { text: "Off", tone: "" };
    case "trackers": {
      const tagOn = d.tag_tracker.enabled;
      const boostOn = d.boost.enabled;
      if (!tagOn && !boostOn) return { text: "Off", tone: "" };
      const tagGap = tagOn && (!d.tag_tracker.server_tag || !d.tag_tracker.role_id);
      const boostGap = boostOn && !d.boost.channel_id;
      return tagGap || boostGap
        ? { text: "Set up", tone: "warn" }
        : { text: "On", tone: "ok" };
    }
    case "panel_access": {
      const count = (d.roles.admin_role_ids ?? []).length;
      return { text: String(count), tone: count > 0 ? "ok" : "" };
    }
  }
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function AdminSettingsPage() {
  const { guildId = "" } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const [resp, setResp] = useState<SettingsResponse | null>(null);
  const [draft, setDraft] = useState<GuildSettings | null>(null);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [channelsFailed, setChannelsFailed] = useState(false);
  const [rolesFailed, setRolesFailed] = useState(false);
  const [overview, setOverview] = useState<GuildOverview | null>(null);
  const [savingSection, setSavingSection] = useState<SettingsSection | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [pendingSlug, setPendingSlug] = useState<Slug | null>(null);
  const [message, setMessage] = useState<
    { kind: "success" | "danger"; text: string } | null
  >(null);

  const slug = parseSlug(searchParams.get("s"));

  useEffect(() => {
    setMessage(null);
    setLoadError(null);

    api
      .settings(guildId)
      .then((s) => {
        setResp(s);
        setDraft(s.config);
      })
      .catch((e) => {
        if ((e as Error).message === "Unauthorized") return;
        setLoadError(formatError(e, "Failed to load settings."));
      });

    // The channel and role lists are loaded separately from the settings so a
    // permission problem on one of them cannot blank the whole page. When one
    // fails the pickers say so rather than showing an empty dropdown.
    api
      .getChannels(guildId)
      .then((c) => {
        setChannels(c);
        setChannelsFailed(false);
      })
      .catch(() => {
        setChannels([]);
        setChannelsFailed(true);
      });

    api
      .getRoles(guildId)
      .then((r) => {
        setRoles(r);
        setRolesFailed(false);
      })
      .catch(() => {
        setRoles([]);
        setRolesFailed(true);
      });

    // Optional. The context column drops the rows it cannot fill.
    api
      .getGuildOverview(guildId)
      .then((o) => setOverview(o))
      .catch(() => setOverview(null));
  }, [guildId]);

  if (loadError) {
    return (
      <div className="app-layout admin-settings-page">
        <AppHeader />
        <div className="alert danger" role="alert" style={{ margin: 24 }}>
          {loadError}
        </div>
      </div>
    );
  }
  if (!resp || !draft) {
    return (
      <div className="app-layout admin-settings-page">
        <AppHeader />
        <p className="muted" style={{ padding: 24 }}>
          Loading settings...
        </p>
      </div>
    );
  }

  const updateSection = <K extends SettingsSection>(
    key: K,
    value: GuildSettings[K],
  ) => {
    setDraft({ ...draft, [key]: value });
  };

  const isDirty = (section: SettingsSection): boolean => {
    return JSON.stringify(draft[section]) !== JSON.stringify(resp.config[section]);
  };

  const saveSection = async (section: SettingsSection) => {
    setSavingSection(section);
    setMessage(null);
    try {
      const patch: SettingsPatch = {
        [section]: draft[section],
      } as SettingsPatch;
      const result = await api.saveSettings(guildId, patch);
      // resp is the canonical server state (full config returned by PUT).
      // draft preserves unsaved edits on other sections - only the just-saved
      // section is replaced with the server's canonical version.
      setResp((prev) => (prev ? { ...prev, config: result.config } : prev));
      setDraft((prev) =>
        prev ? { ...prev, [section]: result.config[section] } : result.config,
      );
      setMessage({ kind: "success", text: `Saved ${section.replace("_", " ")}.` });
    } catch (e) {
      setMessage({ kind: "danger", text: formatError(e, "Save failed.") });
    } finally {
      setSavingSection(null);
    }
  };

  const active = RAIL_ITEMS.find((i) => i.slug === slug) ?? RAIL_ITEMS[0];
  const activeDirty = active.saves.some((s) => isDirty(s.section));

  const goTo = (next: Slug) => {
    setSearchParams(
      (prev) => {
        const params = new URLSearchParams(prev);
        params.set("s", next);
        return params;
      },
      { replace: true },
    );
  };

  const requestSlug = (next: Slug) => {
    if (next === slug) return;
    if (activeDirty) {
      setPendingSlug(next);
      return;
    }
    goTo(next);
  };

  const q = query.trim().toLowerCase();
  const itemMatches = (item: RailItem): boolean => {
    if (!q) return true;
    if (item.label.toLowerCase().includes(q)) return true;
    if (item.title.toLowerCase().includes(q)) return true;
    return item.search.some((s) => s.toLowerCase().includes(q));
  };
  const auditMatches = !q || AUDIT_LOG_SEARCH.some((s) => s.toLowerCase().includes(q));
  const anyMatch = RAIL_ITEMS.some(itemMatches) || auditMatches;

  return (
    <div className="app-layout admin-settings-page">
      <AppHeader
        title="Server Settings"
        left={
          <Link to="/dashboard" className="btn btn-secondary" style={{ marginLeft: 12 }}>
            &larr; Dashboard
          </Link>
        }
      />

      <div className="page">
        {message && (
          <div className={`alert ${message.kind}`} style={{ marginTop: 16 }}>
            {message.text}
          </div>
        )}

        <div className="set-layout">
          <div>
            <div className="set-search">
              <span className="set-search__i" aria-hidden="true">
                &#8981;
              </span>
              <input
                type="search"
                value={query}
                placeholder="Search settings"
                aria-label="Search settings"
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>

            <nav className="set-rail" aria-label="Settings sections">
              {RAIL_GROUPS.map((group) => {
                const items = group.items.filter(itemMatches);
                const showAudit = group.name === "Access" && auditMatches;
                if (items.length === 0 && !showAudit) return null;
                return (
                  <Fragment key={group.name}>
                    <div className="set-rail__grp">{group.name}</div>
                    {items.map((item) => {
                      const dirty = item.saves.some((s) => isDirty(s.section));
                      const badge = dirty
                        ? { text: "Unsaved", tone: "warn" as BadgeTone }
                        : railBadge(item.slug, draft);
                      return (
                        <button
                          key={item.slug}
                          type="button"
                          className={
                            "set-rail__item" + (item.slug === slug ? " is-active" : "")
                          }
                          aria-current={item.slug === slug ? "page" : undefined}
                          onClick={() => requestSlug(item.slug)}
                        >
                          <span>{item.label}</span>
                          <span
                            className={
                              "set-rail__badge" +
                              (badge.tone ? ` set-rail__badge--${badge.tone}` : "")
                            }
                          >
                            {badge.text}
                          </span>
                        </button>
                      );
                    })}
                    {showAudit && (
                      <Link
                        className="set-rail__item"
                        to={`/settings/${guildId}/audit-log`}
                      >
                        <span>Audit log</span>
                      </Link>
                    )}
                  </Fragment>
                );
              })}
              {!anyMatch && (
                <p className="set-rail__empty">
                  Nothing here matches "{query.trim()}".
                </p>
              )}
            </nav>
          </div>

          <PickerStatusProvider value={{ channelsFailed, rolesFailed }}>
            <div className="set-main">
              <div className="set-head">
                <h1>{active.title}</h1>
                <p>{active.blurb}</p>
              </div>

              {slug === "wyr" && (
                <WyrSectionForm
                  value={draft.wyr}
                  channels={channels}
                  roles={roles}
                  onChange={(v) => updateSection("wyr", v)}
                />
              )}
              {slug === "new_members" && (
                <NewMembersSectionForm
                  guildId={guildId}
                  value={draft.new_members}
                  channels={channels}
                  roles={roles}
                  onChange={(v) => updateSection("new_members", v)}
                />
              )}
              {slug === "suggestions" && (
                <SuggestionsSectionForm
                  value={draft.suggestions}
                  server={draft.server}
                  channels={channels}
                  onChange={(v) => updateSection("suggestions", v)}
                  onServerChange={(v) => updateSection("server", v)}
                />
              )}
              {slug === "drops" && (
                <DropsSectionForm
                  value={draft.drops}
                  channels={channels}
                  roles={roles}
                  onChange={(v) => updateSection("drops", v)}
                />
              )}
              {slug === "announcement" && (
                <AnnouncementSectionForm
                  value={draft.announcement}
                  channels={channels}
                  onChange={(v) => updateSection("announcement", v)}
                />
              )}
              {slug === "guide" && (
                <GuideSectionForm
                  guildId={guildId}
                  value={draft.guide}
                  channels={channels}
                  onChange={(v) => updateSection("guide", v)}
                />
              )}
              {slug === "trackers" && (
                <TrackersSectionForm
                  tag={draft.tag_tracker}
                  boost={draft.boost}
                  channels={channels}
                  roles={roles}
                  onTagChange={(v) => updateSection("tag_tracker", v)}
                  onBoostChange={(v) => updateSection("boost", v)}
                />
              )}
              {slug === "panel_access" && (
                <PanelAccessSectionForm
                  value={draft.roles}
                  roles={roles}
                  onChange={(v) => updateSection("roles", v)}
                />
              )}

              <div className="savebar">
                {active.saves.map((s) => {
                  const dirty = isDirty(s.section);
                  const saving = savingSection === s.section;
                  return (
                    <button
                      key={s.section}
                      type="button"
                      className="btn btn-primary"
                      disabled={!dirty || saving}
                      onClick={() => saveSection(s.section)}
                    >
                      {saving ? "Saving..." : s.label}
                    </button>
                  );
                })}
                <span className="muted" style={{ fontSize: 13 }}>
                  {activeDirty ? "Unsaved changes" : "Everything here is saved"}
                </span>
              </div>
            </div>
          </PickerStatusProvider>

          <aside className="set-ctx" aria-label="Current state">
            <ContextColumn
              slug={slug}
              draft={draft}
              channels={channels}
              roles={roles}
              overview={overview}
            />
          </aside>
        </div>
      </div>

      <ConfirmDialog
        open={pendingSlug !== null}
        title="You have unsaved changes"
        message={`"${active.title}" has changes you have not saved yet. They are kept while you move around this page, but they are lost if you reload or close it.`}
        confirmLabel="Switch anyway"
        cancelLabel="Stay here"
        onConfirm={() => {
          const next = pendingSlug;
          setPendingSlug(null);
          if (next) goTo(next);
        }}
        onCancel={() => setPendingSlug(null)}
      />
    </div>
  );
}

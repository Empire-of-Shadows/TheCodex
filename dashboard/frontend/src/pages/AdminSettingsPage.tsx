import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import type {
  AnnouncementSection,
  BoostSection,
  Channel,
  DropsSection,
  GuildSettings,
  GuideSection,
  NewMembersSection,
  Role,
  RolesSection,
  ServerSection,
  SettingsPatch,
  SettingsResponse,
  SettingsSection,
  SuggestionsSection,
  TagTrackerSection,
  WyrSection,
} from "../api/types";
import AppHeader from "../components/AppHeader";
import { formatError } from "../utils/formatError";

// ── Tab definitions ────────────────────────────────────────────────────────

type TabKey =
  | "panel_access"
  | "general"
  | "wyr"
  | "new_members"
  | "drops"
  | "announcement"
  | "suggestions"
  | "trackers"
  | "guide";

interface TabDef {
  key: TabKey;
  label: string;
  /** Settings sections this tab edits. Used for mod-tier filtering. */
  sections: SettingsSection[];
}

const TABS: TabDef[] = [
  { key: "panel_access", label: "Panel Access", sections: ["roles"] },
  { key: "general", label: "General", sections: ["server"] },
  { key: "wyr", label: "Would You Rather", sections: ["wyr"] },
  { key: "new_members", label: "New Members", sections: ["new_members"] },
  { key: "drops", label: "Drops", sections: ["drops"] },
  { key: "announcement", label: "Announcements", sections: ["announcement"] },
  { key: "suggestions", label: "Suggestions", sections: ["suggestions"] },
  { key: "trackers", label: "Trackers", sections: ["tag_tracker", "boost"] },
  { key: "guide", label: "Guide", sections: ["guide"] },
];

// Static option lists (mirrors panel_configs.py constants).

const TIMEZONE_OPTIONS: [string, string][] = [
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

const HOUR_OPTIONS: [number, string][] = Array.from({ length: 24 }, (_, h) => [
  h,
  `${String(h).padStart(2, "0")}:00`,
]);

const MINUTE_OPTIONS: [number, string][] = [
  [0, ":00"],
  [15, ":15"],
  [30, ":30"],
  [45, ":45"],
];

const ARCHIVE_OPTIONS: [number, string][] = [
  [60, "1 Hour"],
  [1440, "1 Day"],
  [4320, "3 Days"],
  [10080, "1 Week"],
];

const WYR_CATEGORY_OPTIONS: [string, string][] = [
  ["sfw", "SFW only"],
  ["nsfw", "NSFW only"],
  ["mixed", "Mixed"],
];

const WYR_CLEANUP_OPTIONS: [number, string][] = [
  [7, "7 Days"],
  [14, "14 Days"],
  [30, "30 Days"],
  [60, "60 Days"],
  [90, "90 Days"],
];

const ACCOUNT_AGE_OPTIONS: [number, string][] = [
  [30, "30 Days"],
  [60, "60 Days"],
  [90, "90 Days"],
  [120, "120 Days"],
  [180, "180 Days"],
];

const DROPS_TRACKER_BUCKETS = ["Updates", "Free", "Prime"] as const;

// ── Page ───────────────────────────────────────────────────────────────────

export default function AdminSettingsPage() {
  const { guildId = "" } = useParams();
  const [resp, setResp] = useState<SettingsResponse | null>(null);
  const [draft, setDraft] = useState<GuildSettings | null>(null);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [tab, setTab] = useState<TabKey>("panel_access");
  const [savingSection, setSavingSection] = useState<SettingsSection | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [message, setMessage] = useState<
    { kind: "success" | "danger"; text: string } | null
  >(null);

  useEffect(() => {
    setMessage(null);
    setLoadError(null);
    Promise.all([
      api.settings(guildId),
      api.getChannels(guildId),
      api.getRoles(guildId),
    ])
      .then(([s, c, r]) => {
        setResp(s);
        setDraft(s.config);
        setChannels(c);
        setRoles(r);
      })
      .catch((e) => {
        if ((e as Error).message === "Unauthorized") return;
        setLoadError(formatError(e, "Failed to load settings."));
      });
  }, [guildId]);

  const visibleTabs = useMemo(() => {
    if (!resp) return TABS;
    if (resp.panel_role === "mod") {
      const allowed = new Set(resp.mod_allowed_sections);
      return TABS.filter((t) => t.sections.some((s) => allowed.has(s)));
    }
    return TABS;
  }, [resp]);

  useEffect(() => {
    if (visibleTabs.length === 0) return;
    if (!visibleTabs.some((t) => t.key === tab)) {
      setTab(visibleTabs[0].key);
    }
  }, [visibleTabs, tab]);

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
      // draft preserves unsaved edits on other tabs — only the just-saved
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

  const isMod = resp.panel_role === "mod";
  const readOnly = (section: SettingsSection): boolean => {
    if (!isMod) return false;
    return !resp.mod_allowed_sections.includes(section);
  };

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

      {message && (
        <div className={`alert ${message.kind}`} style={{ margin: "12px 24px" }}>
          {message.text}
        </div>
      )}

      {isMod && visibleTabs.length === 0 && (
        <div className="alert" style={{ margin: 24 }}>
          You have <strong>Mod</strong> access. No dashboard sections are currently
          opted-in for mod tier &mdash; use the Discord <code>/admin</code> panel.
        </div>
      )}

      {visibleTabs.length > 0 && (
        <>
          <div className="tabs" style={{ padding: "0 24px" }}>
            {visibleTabs.map((t) => (
              <button
                key={t.key}
                className={"tab" + (tab === t.key ? " active" : "")}
                onClick={() => setTab(t.key)}
              >
                {t.label}
              </button>
            ))}
          </div>

          <div style={{ padding: "16px 24px 32px" }}>
            {tab === "panel_access" && (
              <PanelAccessTab
                value={draft.roles}
                roles={roles}
                onChange={(v) => updateSection("roles", v)}
                onSave={() => saveSection("roles")}
                dirty={isDirty("roles")}
                saving={savingSection === "roles"}
                readOnly={readOnly("roles")}
              />
            )}
            {tab === "general" && (
              <GeneralTab
                value={draft.server}
                channels={channels}
                onChange={(v) => updateSection("server", v)}
                onSave={() => saveSection("server")}
                dirty={isDirty("server")}
                saving={savingSection === "server"}
                readOnly={readOnly("server")}
              />
            )}
            {tab === "wyr" && (
              <WyrTab
                value={draft.wyr}
                channels={channels}
                roles={roles}
                onChange={(v) => updateSection("wyr", v)}
                onSave={() => saveSection("wyr")}
                dirty={isDirty("wyr")}
                saving={savingSection === "wyr"}
                readOnly={readOnly("wyr")}
              />
            )}
            {tab === "new_members" && (
              <NewMembersTab
                guildId={guildId}
                value={draft.new_members}
                channels={channels}
                roles={roles}
                onChange={(v) => updateSection("new_members", v)}
                onSave={() => saveSection("new_members")}
                dirty={isDirty("new_members")}
                saving={savingSection === "new_members"}
                readOnly={readOnly("new_members")}
              />
            )}
            {tab === "drops" && (
              <DropsTab
                value={draft.drops}
                channels={channels}
                roles={roles}
                onChange={(v) => updateSection("drops", v)}
                onSave={() => saveSection("drops")}
                dirty={isDirty("drops")}
                saving={savingSection === "drops"}
                readOnly={readOnly("drops")}
              />
            )}
            {tab === "announcement" && (
              <AnnouncementTab
                value={draft.announcement}
                channels={channels}
                onChange={(v) => updateSection("announcement", v)}
                onSave={() => saveSection("announcement")}
                dirty={isDirty("announcement")}
                saving={savingSection === "announcement"}
                readOnly={readOnly("announcement")}
              />
            )}
            {tab === "suggestions" && (
              <SuggestionsTab
                value={draft.suggestions}
                channels={channels}
                onChange={(v) => updateSection("suggestions", v)}
                onSave={() => saveSection("suggestions")}
                dirty={isDirty("suggestions")}
                saving={savingSection === "suggestions"}
                readOnly={readOnly("suggestions")}
              />
            )}
            {tab === "trackers" && (
              <TrackersTab
                tag={draft.tag_tracker}
                boost={draft.boost}
                channels={channels}
                roles={roles}
                onTagChange={(v) => updateSection("tag_tracker", v)}
                onBoostChange={(v) => updateSection("boost", v)}
                onSaveTag={() => saveSection("tag_tracker")}
                onSaveBoost={() => saveSection("boost")}
                tagDirty={isDirty("tag_tracker")}
                boostDirty={isDirty("boost")}
                savingTag={savingSection === "tag_tracker"}
                savingBoost={savingSection === "boost"}
                tagReadOnly={readOnly("tag_tracker")}
                boostReadOnly={readOnly("boost")}
              />
            )}
            {tab === "guide" && (
              <GuideTab
                guildId={guildId}
                value={draft.guide}
                channels={channels}
                onChange={(v) => updateSection("guide", v)}
                onSave={() => saveSection("guide")}
                dirty={isDirty("guide")}
                saving={savingSection === "guide"}
                readOnly={readOnly("guide")}
              />
            )}
          </div>
        </>
      )}
    </div>
  );
}

// ── Reusable field renderers ───────────────────────────────────────────────

function ChannelField({
  label,
  value,
  channels,
  onChange,
  disabled,
  filterType,
  description,
}: {
  label: string;
  value: string | null;
  channels: Channel[];
  onChange: (v: string | null) => void;
  disabled?: boolean;
  filterType?: number;
  description?: string;
}) {
  const options = filterType !== undefined
    ? channels.filter((c) => c.type === filterType)
    : channels;
  return (
    <div className="field">
      <label>{label}</label>
      {description && (
        <p className="muted" style={{ marginTop: 0, marginBottom: 6 }}>
          {description}
        </p>
      )}
      <select
        value={value ?? ""}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value || null)}
      >
        <option value="">-- not set --</option>
        {options.map((c) => (
          <option key={c.id} value={c.id}>
            #{c.name}
          </option>
        ))}
      </select>
    </div>
  );
}

function RoleField({
  label,
  value,
  roles,
  onChange,
  disabled,
  description,
}: {
  label: string;
  value: string | null;
  roles: Role[];
  onChange: (v: string | null) => void;
  disabled?: boolean;
  description?: string;
}) {
  const sorted = [...roles].sort((a, b) => b.position - a.position);
  return (
    <div className="field">
      <label>{label}</label>
      {description && (
        <p className="muted" style={{ marginTop: 0, marginBottom: 6 }}>
          {description}
        </p>
      )}
      <select
        value={value ?? ""}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value || null)}
      >
        <option value="">-- not set --</option>
        {sorted.map((r) => (
          <option key={r.id} value={r.id}>
            {r.name}
          </option>
        ))}
      </select>
    </div>
  );
}

function MultiRoleField({
  label,
  description,
  value,
  roles,
  max,
  onChange,
  disabled,
}: {
  label: string;
  description?: string;
  value: string[];
  roles: Role[];
  max?: number;
  onChange: (v: string[]) => void;
  disabled?: boolean;
}) {
  const selected = new Set(value);
  const sorted = [...roles].sort((a, b) => b.position - a.position);
  const limitReached = max !== undefined && selected.size >= max;
  const toggle = (id: string) => {
    if (disabled) return;
    const next = new Set(selected);
    if (next.has(id)) {
      next.delete(id);
    } else {
      if (max !== undefined && next.size >= max) return;
      next.add(id);
    }
    onChange(sorted.filter((r) => next.has(r.id)).map((r) => r.id));
  };
  return (
    <div className="field">
      <label>{label}</label>
      {description && (
        <p className="muted" style={{ marginTop: 0, marginBottom: 6 }}>
          {description}
        </p>
      )}
      <div
        style={{
          maxHeight: 220,
          overflowY: "auto",
          border: "1px solid var(--border, #2a2a2a)",
          borderRadius: 6,
          padding: 8,
          display: "flex",
          flexDirection: "column",
          gap: 4,
        }}
      >
        {sorted.length === 0 && (
          <p className="muted" style={{ margin: 0 }}>No roles available.</p>
        )}
        {sorted.map((r) => {
          const checked = selected.has(r.id);
          const lockedByCap = !checked && limitReached;
          const rowDisabled = disabled || lockedByCap;
          return (
            <label
              key={r.id}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                cursor: rowDisabled ? "not-allowed" : "pointer",
                opacity: rowDisabled ? 0.5 : 1,
              }}
            >
              <input
                type="checkbox"
                checked={checked}
                disabled={rowDisabled}
                onChange={() => toggle(r.id)}
              />
              <span>{r.name}</span>
            </label>
          );
        })}
      </div>
      <p className="muted" style={{ marginTop: 6, marginBottom: 0 }}>
        {selected.size} selected{max !== undefined ? ` / ${max} max` : ""}
      </p>
    </div>
  );
}

function OptionSelect<V extends string | number>({
  label,
  value,
  options,
  onChange,
  disabled,
  description,
}: {
  label: string;
  value: V;
  options: [V, string][];
  onChange: (v: V) => void;
  disabled?: boolean;
  description?: string;
}) {
  return (
    <div className="field">
      <label>{label}</label>
      {description && (
        <p className="muted" style={{ marginTop: 0, marginBottom: 6 }}>
          {description}
        </p>
      )}
      <select
        value={String(value)}
        disabled={disabled}
        onChange={(e) => {
          const raw = e.target.value;
          const sample = options[0]?.[0];
          if (typeof sample === "number") {
            onChange(Number(raw) as V);
          } else {
            onChange(raw as V);
          }
        }}
      >
        {options.map(([v, optLabel]) => (
          <option key={String(v)} value={String(v)}>
            {optLabel}
          </option>
        ))}
      </select>
    </div>
  );
}

function ToggleField({
  label,
  value,
  onChange,
  disabled,
  description,
}: {
  label: string;
  value: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
  description?: string;
}) {
  return (
    <div className="field">
      <label className="toggle">
        <input
          type="checkbox"
          checked={!!value}
          disabled={disabled}
          onChange={(e) => onChange(e.target.checked)}
        />
        <span>{label}</span>
      </label>
      {description && (
        <p className="muted" style={{ marginTop: 4, marginBottom: 0 }}>
          {description}
        </p>
      )}
    </div>
  );
}

function TextField({
  label,
  value,
  onChange,
  disabled,
  description,
  placeholder,
  maxLength,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
  description?: string;
  placeholder?: string;
  maxLength?: number;
}) {
  return (
    <div className="field">
      <label>{label}</label>
      {description && (
        <p className="muted" style={{ marginTop: 0, marginBottom: 6 }}>
          {description}
        </p>
      )}
      <input
        type="text"
        value={value}
        disabled={disabled}
        placeholder={placeholder}
        maxLength={maxLength}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}

function TextareaField({
  label,
  value,
  onChange,
  disabled,
  description,
  placeholder,
  maxLength,
  rows = 4,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
  description?: string;
  placeholder?: string;
  maxLength?: number;
  rows?: number;
}) {
  return (
    <div className="field">
      <label>{label}</label>
      {description && (
        <p className="muted" style={{ marginTop: 0, marginBottom: 6 }}>
          {description}
        </p>
      )}
      <textarea
        value={value}
        rows={rows}
        disabled={disabled}
        placeholder={placeholder}
        maxLength={maxLength}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}

function SaveBar({
  dirty,
  saving,
  onSave,
  readOnly,
  label = "Save",
}: {
  dirty: boolean;
  saving: boolean;
  onSave: () => void;
  readOnly?: boolean;
  label?: string;
}) {
  if (readOnly) {
    return (
      <p className="muted" style={{ marginTop: 12 }}>
        Read-only for your tier.
      </p>
    );
  }
  return (
    <div style={{ marginTop: 16, display: "flex", gap: 8, alignItems: "center" }}>
      <button
        className="btn btn-primary"
        disabled={!dirty || saving}
        onClick={onSave}
      >
        {saving ? "Saving..." : label}
      </button>
      {dirty && (
        <span className="muted" style={{ fontSize: 13 }}>
          Unsaved changes
        </span>
      )}
    </div>
  );
}

function SectionCard({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <section className="section card" style={{ marginBottom: 16 }}>
      <h2 className="section-title" style={{ marginTop: 0 }}>{title}</h2>
      {description && (
        <p className="muted" style={{ marginTop: 0 }}>{description}</p>
      )}
      {children}
    </section>
  );
}

// ── Tab: Panel Access ──────────────────────────────────────────────────────

function PanelAccessTab({
  value,
  roles,
  onChange,
  onSave,
  dirty,
  saving,
  readOnly,
}: {
  value: RolesSection;
  roles: Role[];
  onChange: (v: RolesSection) => void;
  onSave: () => void;
  dirty: boolean;
  saving: boolean;
  readOnly: boolean;
}) {
  return (
    <SectionCard
      title="Panel Access Roles"
      description="Members holding any Panel Access role get full admin panel access (same as Manage Server). Mod Access roles grant the mod tier."
    >
      <div className="field-row">
        <MultiRoleField
          label="Panel Access Roles"
          description="Full admin access (acts like Manage Server)."
          value={value.admin_role_ids ?? []}
          roles={roles}
          max={10}
          disabled={readOnly}
          onChange={(v) => onChange({ ...value, admin_role_ids: v })}
        />
        <MultiRoleField
          label="Mod Access Roles"
          description="Limited (mod-tier) access to opted-in sections."
          value={value.mod_role_ids ?? []}
          roles={roles}
          max={10}
          disabled={readOnly}
          onChange={(v) => onChange({ ...value, mod_role_ids: v })}
        />
      </div>
      <SaveBar dirty={dirty} saving={saving} onSave={onSave} readOnly={readOnly} />
    </SectionCard>
  );
}

// ── Tab: General ───────────────────────────────────────────────────────────

function GeneralTab({
  value,
  channels,
  onChange,
  onSave,
  dirty,
  saving,
  readOnly,
}: {
  value: ServerSection;
  channels: Channel[];
  onChange: (v: ServerSection) => void;
  onSave: () => void;
  dirty: boolean;
  saving: boolean;
  readOnly: boolean;
}) {
  return (
    <SectionCard
      title="General"
      description="Server-wide settings."
    >
      <div className="field-row">
        <ChannelField
          label="Admin Channel"
          value={value.admin_channel_id}
          channels={channels}
          filterType={0}
          disabled={readOnly}
          onChange={(v) => onChange({ ...value, admin_channel_id: v })}
          description="Channel used for admin notifications and alerts."
        />
      </div>
      <SaveBar dirty={dirty} saving={saving} onSave={onSave} readOnly={readOnly} />
    </SectionCard>
  );
}

// ── Tab: WYR ───────────────────────────────────────────────────────────────

function WyrTab({
  value,
  channels,
  roles,
  onChange,
  onSave,
  dirty,
  saving,
  readOnly,
}: {
  value: WyrSection;
  channels: Channel[];
  roles: Role[];
  onChange: (v: WyrSection) => void;
  onSave: () => void;
  dirty: boolean;
  saving: boolean;
  readOnly: boolean;
}) {
  return (
    <SectionCard
      title="Would You Rather"
      description="Daily WYR question posting and discussion threads."
    >
      <div className="field-row">
        <ChannelField
          label="WYR Channel"
          value={value.channel_id}
          channels={channels}
          filterType={0}
          disabled={readOnly}
          onChange={(v) => onChange({ ...value, channel_id: v })}
        />
        <RoleField
          label="Ping Role"
          value={value.ping_role_id}
          roles={roles}
          disabled={readOnly}
          onChange={(v) => onChange({ ...value, ping_role_id: v })}
          description="Pinged on each post. Leave blank for no ping."
        />
        <ToggleField
          label="Enabled"
          value={value.enabled}
          disabled={readOnly}
          onChange={(v) => onChange({ ...value, enabled: v })}
        />
      </div>

      <h3 style={{ marginTop: 20 }}>Schedule</h3>
      <div className="field-row">
        <OptionSelect<number>
          label="Post Hour"
          value={value.post_hour}
          options={HOUR_OPTIONS}
          disabled={readOnly}
          onChange={(v) => onChange({ ...value, post_hour: v })}
        />
        <OptionSelect<number>
          label="Post Minute"
          value={value.post_minute}
          options={MINUTE_OPTIONS}
          disabled={readOnly}
          onChange={(v) => onChange({ ...value, post_minute: v })}
        />
        <OptionSelect<string>
          label="Timezone"
          value={value.timezone}
          options={TIMEZONE_OPTIONS}
          disabled={readOnly}
          onChange={(v) => onChange({ ...value, timezone: v })}
        />
        <OptionSelect<string>
          label="Default Category"
          value={value.default_category}
          options={WYR_CATEGORY_OPTIONS}
          disabled={readOnly}
          onChange={(v) => onChange({ ...value, default_category: v })}
        />
      </div>

      <h3 style={{ marginTop: 20 }}>Threads</h3>
      <TextField
        label="Thread Name Format"
        value={value.thread_name_format}
        maxLength={100}
        disabled={readOnly}
        onChange={(v) => onChange({ ...value, thread_name_format: v })}
        description="Placeholders: {date} {question_num} {category} {option_1} {option_2} {option_3} {question}"
      />
      <TextareaField
        label="Starter Message"
        value={value.thread_starter_message}
        maxLength={500}
        disabled={readOnly}
        onChange={(v) => onChange({ ...value, thread_starter_message: v })}
      />
      <div className="field-row">
        <OptionSelect<number>
          label="Auto-Archive"
          value={value.thread_auto_archive}
          options={ARCHIVE_OPTIONS}
          disabled={readOnly}
          onChange={(v) => onChange({ ...value, thread_auto_archive: v })}
        />
        <OptionSelect<number>
          label="Mapping Cleanup"
          value={value.mapping_cleanup_days}
          options={WYR_CLEANUP_OPTIONS}
          disabled={readOnly}
          onChange={(v) => onChange({ ...value, mapping_cleanup_days: v })}
          description="Days before old message-question mappings are pruned."
        />
      </div>

      <SaveBar dirty={dirty} saving={saving} onSave={onSave} readOnly={readOnly} />
    </SectionCard>
  );
}

// ── Tab: New Members ───────────────────────────────────────────────────────

function NewMembersTab({
  guildId,
  value,
  channels,
  roles,
  onChange,
  onSave,
  dirty,
  saving,
  readOnly,
}: {
  guildId: string;
  value: NewMembersSection;
  channels: Channel[];
  roles: Role[];
  onChange: (v: NewMembersSection) => void;
  onSave: () => void;
  dirty: boolean;
  saving: boolean;
  readOnly: boolean;
}) {
  return (
    <SectionCard
      title="New Members"
      description="Account-age screening, welcome messages, and whitelist role assignment."
    >
      <div className="field-row">
        <ChannelField
          label="Welcome Channel"
          value={value.welcome_channel_id}
          channels={channels}
          filterType={0}
          disabled={readOnly}
          onChange={(v) => onChange({ ...value, welcome_channel_id: v })}
        />
        <RoleField
          label="Whitelist Role"
          value={value.whitelist_role_id}
          roles={roles}
          disabled={readOnly}
          onChange={(v) => onChange({ ...value, whitelist_role_id: v })}
        />
        <OptionSelect<number>
          label="Account Age Requirement"
          value={value.account_age_requirement_days}
          options={ACCOUNT_AGE_OPTIONS}
          disabled={readOnly}
          onChange={(v) => onChange({ ...value, account_age_requirement_days: v })}
        />
      </div>

      <h3 style={{ marginTop: 20 }}>Toggles</h3>
      <div className="field-row">
        <ToggleField
          label="System Enabled"
          value={value.enabled}
          disabled={readOnly}
          onChange={(v) => onChange({ ...value, enabled: v })}
          description="Master toggle for new-member processing."
        />
        <ToggleField
          label="Auto-Kick Underage Accounts"
          value={value.auto_kick}
          disabled={readOnly}
          onChange={(v) => onChange({ ...value, auto_kick: v })}
        />
        <ToggleField
          label="Welcome Messages"
          value={value.welcome_message_enabled}
          disabled={readOnly}
          onChange={(v) => onChange({ ...value, welcome_message_enabled: v })}
        />
        <ToggleField
          label="Whitelist System"
          value={value.whitelist_enabled}
          disabled={readOnly}
          onChange={(v) => onChange({ ...value, whitelist_enabled: v })}
        />
      </div>

      <TextField
        label="Whitelist Role Name"
        value={value.whitelist_role_name}
        maxLength={100}
        disabled={readOnly}
        onChange={(v) => onChange({ ...value, whitelist_role_name: v })}
        description="Used when auto-creating the whitelist role if one is not set above."
      />

      <p className="muted" style={{ marginTop: 16 }}>
        Welcome message layout is managed in the{" "}
        <Link to={`/builder/${guildId}`}>builder</Link>.
      </p>

      <SaveBar dirty={dirty} saving={saving} onSave={onSave} readOnly={readOnly} />
    </SectionCard>
  );
}

// ── Tab: Drops ─────────────────────────────────────────────────────────────

function DropsTab({
  value,
  channels,
  roles,
  onChange,
  onSave,
  dirty,
  saving,
  readOnly,
}: {
  value: DropsSection;
  channels: Channel[];
  roles: Role[];
  onChange: (v: DropsSection) => void;
  onSave: () => void;
  dirty: boolean;
  saving: boolean;
  readOnly: boolean;
}) {
  const tracker = value.tracker_channels ?? {};
  return (
    <SectionCard
      title="Updates &amp; Drops"
      description="Daily Prime Gaming drops feed and per-bucket tracking."
    >
      <div className="field-row">
        <ChannelField
          label="Drops Channel"
          value={value.channel_id}
          channels={channels}
          filterType={0}
          disabled={readOnly}
          onChange={(v) => onChange({ ...value, channel_id: v })}
        />
        <RoleField
          label="Manager Role"
          value={value.manager_role_id}
          roles={roles}
          disabled={readOnly}
          onChange={(v) => onChange({ ...value, manager_role_id: v })}
          description="Role allowed to manage drops via /drop."
        />
        <ToggleField
          label="Enabled"
          value={value.enabled}
          disabled={readOnly}
          onChange={(v) => onChange({ ...value, enabled: v })}
        />
      </div>

      <h3 style={{ marginTop: 20 }}>Tracker Channels</h3>
      <div className="field-row">
        {DROPS_TRACKER_BUCKETS.map((bucket) => (
          <ChannelField
            key={bucket}
            label={bucket}
            value={tracker[bucket] ?? null}
            channels={channels}
            filterType={0}
            disabled={readOnly}
            onChange={(v) =>
              onChange({
                ...value,
                tracker_channels: { ...tracker, [bucket]: v },
              })
            }
          />
        ))}
      </div>

      <h3 style={{ marginTop: 20 }}>Schedule</h3>
      <div className="field-row">
        <OptionSelect<number>
          label="Post Hour"
          value={value.post_hour}
          options={HOUR_OPTIONS}
          disabled={readOnly}
          onChange={(v) => onChange({ ...value, post_hour: v })}
        />
        <OptionSelect<number>
          label="Post Minute"
          value={value.post_minute}
          options={MINUTE_OPTIONS}
          disabled={readOnly}
          onChange={(v) => onChange({ ...value, post_minute: v })}
        />
        <OptionSelect<string>
          label="Timezone"
          value={value.timezone}
          options={TIMEZONE_OPTIONS}
          disabled={readOnly}
          onChange={(v) => onChange({ ...value, timezone: v })}
        />
      </div>

      <SaveBar dirty={dirty} saving={saving} onSave={onSave} readOnly={readOnly} />
    </SectionCard>
  );
}

// ── Tab: Announcement ──────────────────────────────────────────────────────

function AnnouncementTab({
  value,
  channels,
  onChange,
  onSave,
  dirty,
  saving,
  readOnly,
}: {
  value: AnnouncementSection;
  channels: Channel[];
  onChange: (v: AnnouncementSection) => void;
  onSave: () => void;
  dirty: boolean;
  saving: boolean;
  readOnly: boolean;
}) {
  return (
    <SectionCard
      title="Announcements"
      description="Auto-thread creation on announcement posts."
    >
      <div className="field-row">
        <ChannelField
          label="Announcement Channel"
          value={value.channel_id}
          channels={channels}
          filterType={0}
          disabled={readOnly}
          onChange={(v) => onChange({ ...value, channel_id: v })}
        />
        <OptionSelect<number>
          label="Auto-Archive"
          value={value.thread_auto_archive_duration}
          options={ARCHIVE_OPTIONS}
          disabled={readOnly}
          onChange={(v) => onChange({ ...value, thread_auto_archive_duration: v })}
        />
      </div>

      <div className="field-row">
        <ToggleField
          label="Auto-Create Threads"
          value={value.thread_auto_create}
          disabled={readOnly}
          onChange={(v) => onChange({ ...value, thread_auto_create: v })}
        />
        <ToggleField
          label="Auto-Delete Threads"
          value={value.auto_delete_threads}
          disabled={readOnly}
          onChange={(v) => onChange({ ...value, auto_delete_threads: v })}
          description="Delete the discussion thread when the announcement is deleted."
        />
      </div>

      <TextField
        label="Thread Name Format"
        value={value.thread_name_format}
        maxLength={100}
        disabled={readOnly}
        onChange={(v) => onChange({ ...value, thread_name_format: v })}
        description="Placeholders: {message_content} {author_name} {channel_name}"
      />
      <TextareaField
        label="Thread Welcome Message"
        value={value.thread_welcome_message}
        maxLength={500}
        disabled={readOnly}
        onChange={(v) => onChange({ ...value, thread_welcome_message: v })}
      />

      <SaveBar dirty={dirty} saving={saving} onSave={onSave} readOnly={readOnly} />
    </SectionCard>
  );
}

// ── Tab: Suggestions ───────────────────────────────────────────────────────

function SuggestionsTab({
  value,
  channels,
  onChange,
  onSave,
  dirty,
  saving,
  readOnly,
}: {
  value: SuggestionsSection;
  channels: Channel[];
  onChange: (v: SuggestionsSection) => void;
  onSave: () => void;
  dirty: boolean;
  saving: boolean;
  readOnly: boolean;
}) {
  return (
    <SectionCard
      title="Suggestions"
      description="User-submitted suggestion posting."
    >
      <div className="field-row">
        <ChannelField
          label="Suggestion Channel"
          value={value.channel_id}
          channels={channels}
          filterType={0}
          disabled={readOnly}
          onChange={(v) => onChange({ ...value, channel_id: v })}
        />
      </div>
      <SaveBar dirty={dirty} saving={saving} onSave={onSave} readOnly={readOnly} />
    </SectionCard>
  );
}

// ── Tab: Trackers ──────────────────────────────────────────────────────────

function TrackersTab({
  tag,
  boost,
  channels,
  roles,
  onTagChange,
  onBoostChange,
  onSaveTag,
  onSaveBoost,
  tagDirty,
  boostDirty,
  savingTag,
  savingBoost,
  tagReadOnly,
  boostReadOnly,
}: {
  tag: TagTrackerSection;
  boost: BoostSection;
  channels: Channel[];
  roles: Role[];
  onTagChange: (v: TagTrackerSection) => void;
  onBoostChange: (v: BoostSection) => void;
  onSaveTag: () => void;
  onSaveBoost: () => void;
  tagDirty: boolean;
  boostDirty: boolean;
  savingTag: boolean;
  savingBoost: boolean;
  tagReadOnly: boolean;
  boostReadOnly: boolean;
}) {
  return (
    <>
      <SectionCard
        title="Tag Tracker"
        description="Track which members are wearing the server tag."
      >
        <div className="field-row">
          <TextField
            label="Server Tag"
            value={tag.server_tag ?? ""}
            maxLength={32}
            disabled={tagReadOnly}
            onChange={(v) => onTagChange({ ...tag, server_tag: v || null })}
            description="The exact server tag string members must wear to qualify."
          />
          <RoleField
            label="Tag Role"
            value={tag.role_id}
            roles={roles}
            disabled={tagReadOnly}
            onChange={(v) => onTagChange({ ...tag, role_id: v })}
            description="Role granted to members wearing the tag."
          />
          <ToggleField
            label="Enabled"
            value={tag.enabled}
            disabled={tagReadOnly}
            onChange={(v) => onTagChange({ ...tag, enabled: v })}
          />
        </div>
        <SaveBar
          dirty={tagDirty}
          saving={savingTag}
          onSave={onSaveTag}
          readOnly={tagReadOnly}
          label="Save Tag Tracker"
        />
      </SectionCard>

      <SectionCard
        title="Boost Tracker"
        description="Logs server boosts to a dedicated channel."
      >
        <div className="field-row">
          <ChannelField
            label="Boost Log Channel"
            value={boost.channel_id}
            channels={channels}
            filterType={0}
            disabled={boostReadOnly}
            onChange={(v) => onBoostChange({ ...boost, channel_id: v })}
          />
          <ToggleField
            label="Enabled"
            value={boost.enabled}
            disabled={boostReadOnly}
            onChange={(v) => onBoostChange({ ...boost, enabled: v })}
          />
        </div>
        <SaveBar
          dirty={boostDirty}
          saving={savingBoost}
          onSave={onSaveBoost}
          readOnly={boostReadOnly}
          label="Save Boost Tracker"
        />
      </SectionCard>
    </>
  );
}

// ── Tab: Guide ─────────────────────────────────────────────────────────────

function GuideTab({
  guildId,
  value,
  channels,
  onChange,
  onSave,
  dirty,
  saving,
  readOnly,
}: {
  guildId: string;
  value: GuideSection;
  channels: Channel[];
  onChange: (v: GuideSection) => void;
  onSave: () => void;
  dirty: boolean;
  saving: boolean;
  readOnly: boolean;
}) {
  return (
    <SectionCard
      title="Guide"
      description="The server guide system."
    >
      <div className="field-row">
        <ChannelField
          label="Guide Channel"
          value={value.channel_id}
          channels={channels}
          filterType={0}
          disabled={readOnly}
          onChange={(v) => onChange({ ...value, channel_id: v })}
          description="Optional — restrict /guide invocation to this channel."
        />
        <ToggleField
          label="Enabled"
          value={value.enabled}
          disabled={readOnly}
          onChange={(v) => onChange({ ...value, enabled: v })}
        />
      </div>

      <p className="muted" style={{ marginTop: 16 }}>
        Guide content (pages, components) is managed in the{" "}
        <Link to={`/builder/${guildId}`}>builder</Link>.
      </p>

      <SaveBar dirty={dirty} saving={saving} onSave={onSave} readOnly={readOnly} />
    </SectionCard>
  );
}

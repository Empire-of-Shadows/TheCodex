import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import type { AuditLogEntry, AuditLogSummary } from "../api/types";
import AppHeader from "../components/AppHeader";
import BarChart, { type BarChartSeries } from "../_engine/components/charts/BarChart";
import {
  Rule,
  SectionUnavailable,
  Stat,
  Tile,
} from "../_engine/components/overview/Tile";
import { formatCount, formatDate, formatDayCount } from "../_engine/format";
import { formatError } from "../_engine/api/formatError";

/*
 * The change history.
 *
 * This page used to render a bare .container with a hand-rolled header, which
 * made it the one page in the dashboard that did not sit on the app shell. It
 * is now .app-layout + AppHeader + .page like everything else, and the entry
 * table sits in a tile under a summary of the whole log - the table only ever
 * shows one page of entries, so nothing on it could answer "how much is in
 * here" or "who has been changing things".
 */

interface SectionDef {
  /** The value stored on an audit entry, and the one mirrored into the URL. */
  key: string;
  /** Filter and table wording, matching the names the settings page uses. */
  label: string;
  /** Chart x-axis label, where a full feature name collides with its neighbour. */
  short: string;
}

const SECTIONS: SectionDef[] = [
  { key: "", label: "Every section", short: "All" },
  { key: "roles", label: "Who can manage", short: "Access" },
  { key: "wyr", label: "Would You Rather", short: "WYR" },
  { key: "server", label: "Server", short: "Server" },
  { key: "new_members", label: "New members", short: "Members" },
  { key: "announcement", label: "Announcements", short: "Announcements" },
  { key: "tag_tracker", label: "Tag tracker", short: "Tags" },
  { key: "drops", label: "Updates and drops", short: "Drops" },
  { key: "suggestions", label: "Suggestions", short: "Suggestions" },
  { key: "boost", label: "Boost tracker", short: "Boosts" },
  { key: "guide", label: "Guide and board", short: "Guide" },
  { key: "embed", label: "Embeds", short: "Embeds" },
];

/** A section the map does not know is shown as it was stored, never dropped. */
function sectionLabel(key: string): string {
  return SECTIONS.find((s) => s.key === key)?.label ?? key;
}

function sectionShort(key: string): string {
  return SECTIONS.find((s) => s.key === key)?.short ?? key;
}

/**
 * How long history is kept, said the way a person would say it. The engine's
 * formatDayCount turns the one-year retention into "12 months, 5 days", which is
 * arithmetically right and reads like a receipt.
 */
function formatRetention(days: number): string {
  if (days >= 365 && days % 365 === 0) {
    const years = days / 365;
    return years === 1 ? "a year" : `${years} years`;
  }
  return formatDayCount(days);
}

/** Where a change came from, in words rather than the stored token. */
function sourceLabel(source: string): string {
  if (source === "dashboard") return "From the dashboard";
  if (source === "discord") return "From Discord";
  return `From ${source}`;
}

function formatValue(v: unknown): string {
  if (v === null || v === undefined) return "-";
  if (typeof v === "boolean") return v ? "true" : "false";
  if (typeof v === "string") return v.length > 80 ? v.slice(0, 77) + "..." : v;
  if (typeof v === "number") return String(v);
  try {
    const s = JSON.stringify(v);
    return s.length > 80 ? s.slice(0, 77) + "..." : s;
  } catch {
    return String(v);
  }
}

function formatTs(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export default function AdminAuditLogPage() {
  const { guildId = "" } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const sectionFilter = searchParams.get("section") ?? "";
  const actorFilter = searchParams.get("actor") ?? "";

  const updateParam = (key: string, value: string) => {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (value) next.set(key, value);
        else next.delete(key);
        return next;
      },
      { replace: true },
    );
  };

  const [entries, setEntries] = useState<AuditLogEntry[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<AuditLogSummary | null>(null);
  const [summaryFailed, setSummaryFailed] = useState(false);

  const loadFirst = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await api.auditLog(guildId, null, sectionFilter || null);
      setEntries(r.entries);
      setNextCursor(r.next_cursor);
    } catch (e) {
      console.error("Audit log load failed", e);
      setError(formatError(e, "Failed to load audit entries."));
    } finally {
      setLoading(false);
    }
  }, [guildId, sectionFilter]);

  useEffect(() => {
    loadFirst();
  }, [loadFirst]);

  // The summary covers the whole log, so it is not reloaded when the section
  // filter changes, and it is loaded separately so a failure on it cannot take
  // the entry table down with it.
  useEffect(() => {
    let alive = true;
    api
      .auditLogSummary(guildId)
      .then((s) => {
        if (!alive) return;
        setSummary(s);
        setSummaryFailed(false);
      })
      .catch((e) => {
        if (!alive) return;
        console.error("Audit log summary load failed", e);
        setSummary(null);
        setSummaryFailed(true);
      });
    return () => {
      alive = false;
    };
  }, [guildId]);

  const loadMore = async () => {
    if (!nextCursor) return;
    setLoading(true);
    try {
      const r = await api.auditLog(guildId, nextCursor, sectionFilter || null);
      setEntries((prev) => [...prev, ...r.entries]);
      setNextCursor(r.next_cursor);
    } catch (e) {
      console.error("Audit log loadMore failed", e);
      setError(formatError(e, "Failed to load more entries."));
    } finally {
      setLoading(false);
    }
  };

  const filtered = useMemo(() => {
    const needle = actorFilter.trim().toLowerCase();
    if (!needle) return entries;
    return entries.filter(
      (e) =>
        e.actor_name.toLowerCase().includes(needle) ||
        e.actor_id.includes(needle),
    );
  }, [entries, actorFilter]);

  // Busiest section first: the chart answers "what gets changed around here",
  // which is a ranking, not a sequence.
  const sectionRanking = useMemo(() => {
    if (!summary) return [];
    return Object.entries(summary.by_section).sort((a, b) => b[1] - a[1]);
  }, [summary]);

  const sourceRanking = useMemo(() => {
    if (!summary) return [];
    return Object.entries(summary.by_source).sort((a, b) => b[1] - a[1]);
  }, [summary]);

  // One measure over one set of categories, so one series: colour carries no
  // identity here and the engine draws no legend for a single series.
  const sectionSeries: BarChartSeries[] = [
    { key: "changes", label: "Changes", values: sectionRanking.map(([, n]) => n) },
  ];

  return (
    <div className="app-layout">
      <AppHeader
        title="Change history"
        left={
          <Link
            to={`/settings/${guildId}`}
            className="btn btn-secondary"
            style={{ marginLeft: 12 }}
          >
            &larr; Settings
          </Link>
        }
      />

      <div className="page">
        {error && (
          <div className="alert danger" role="alert" style={{ marginTop: 16 }}>
            {error}
          </div>
        )}

        <div className="ov-grid audit-grid">
          <Tile
            span={12}
            title="At a glance"
            chips={
              summary ? (
                <span className="ov-chip">
                  Kept for {formatRetention(summary.retention_days)}
                </span>
              ) : null
            }
          >
            {summaryFailed ? (
              <SectionUnavailable what="The totals for this log" />
            ) : !summary ? (
              <p className="ov-muted">Counting up the changes...</p>
            ) : summary.total === 0 ? (
              <p className="ov-body">
                Nothing has been changed yet. Every settings change made from the dashboard
                or from the admin panel in Discord is recorded here.
              </p>
            ) : (
              <>
                <div className="ov-statrow">
                  <Stat small value={formatCount(summary.total)} label="Changes recorded" />
                  <Stat
                    small
                    value={formatCount(summary.distinct_actors)}
                    label="People who changed something"
                  />
                  {sourceRanking.map(([source, count]) => (
                    <Stat
                      key={source}
                      small
                      value={formatCount(count)}
                      label={sourceLabel(source)}
                    />
                  ))}
                </div>
                <BarChart
                  groups={sectionRanking.map(([key]) => sectionShort(key))}
                  series={sectionSeries}
                  ariaLabel="Number of recorded changes in each settings section"
                  unit="changes"
                  emptyLabel="No changes recorded yet."
                />
                <Rule />
                <p className="ov-muted">
                  Oldest change still held: {formatDate(summary.oldest_at)}. Entries drop off
                  on their own once they are {formatRetention(summary.retention_days)} old.
                </p>
              </>
            )}
          </Tile>

          <Tile
            span={12}
            title="Every change"
            action={
              <button
                type="button"
                className="ov-link"
                onClick={loadFirst}
                disabled={loading}
              >
                Refresh
              </button>
            }
          >
            <div className="audit-filters">
              <div className="eos-field">
                <label htmlFor="audit-section">Section</label>
                <select
                  id="audit-section"
                  value={sectionFilter}
                  onChange={(e) => updateParam("section", e.target.value)}
                >
                  {SECTIONS.map((s) => (
                    <option key={s.key} value={s.key}>
                      {s.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="eos-field">
                <label htmlFor="audit-actor">Who made the change</label>
                <input
                  id="audit-actor"
                  type="text"
                  placeholder="name or id"
                  value={actorFilter}
                  onChange={(e) => updateParam("actor", e.target.value)}
                />
              </div>
            </div>

            {loading && entries.length === 0 ? (
              <p className="ov-muted">Loading...</p>
            ) : filtered.length === 0 ? (
              <p className="ov-muted">No audit entries.</p>
            ) : (
              <div className="audit-scroll">
                <table className="audit-table">
                  <thead>
                    <tr>
                      <th>When</th>
                      <th>Actor</th>
                      <th>Source</th>
                      <th>Section</th>
                      <th>Key</th>
                      <th>Action</th>
                      <th>Old</th>
                      <th>New</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((e, i) => (
                      <tr key={`${e.created_at}-${e.key}-${i}`}>
                        <td>{formatTs(e.created_at)}</td>
                        <td title={e.actor_id}>{e.actor_name}</td>
                        <td>{e.source}</td>
                        <td title={e.section}>{sectionLabel(e.section)}</td>
                        <td><code>{e.key}</code></td>
                        <td>{e.action}</td>
                        <td><code>{formatValue(e.old_value)}</code></td>
                        <td><code>{formatValue(e.new_value)}</code></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {nextCursor && (
              <div style={{ textAlign: "center" }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={loadMore}
                  disabled={loading}
                >
                  {loading ? "Loading..." : "Load more"}
                </button>
              </div>
            )}
          </Tile>
        </div>
      </div>
    </div>
  );
}

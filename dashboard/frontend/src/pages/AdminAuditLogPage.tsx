import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import type { AuditLogEntry } from "../api/types";
import { formatError } from "../_engine/api/formatError";

const SECTIONS = [
  "",
  "roles",
  "wyr",
  "server",
  "new_members",
  "announcement",
  "tag_tracker",
  "drops",
  "suggestions",
  "boost",
  "guide",
  "embed",
];

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

  return (
    <div className="container">
      <header style={{ display: "flex", alignItems: "center", gap: "1rem", margin: "1rem 0" }}>
        <Link to="/dashboard">&larr; Back</Link>
        <h1 style={{ margin: 0 }}>Audit Log</h1>
      </header>

      {error && <div className="alert danger">{error}</div>}

      <div className="card" style={{ marginBottom: "1rem", padding: "1rem" }}>
        <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap", alignItems: "center" }}>
          <label>
            Section:{" "}
            <select
              value={sectionFilter}
              onChange={(e) => updateParam("section", e.target.value)}
            >
              {SECTIONS.map((s) => (
                <option key={s} value={s}>
                  {s || "(all)"}
                </option>
              ))}
            </select>
          </label>
          <label>
            Actor:{" "}
            <input
              type="text"
              placeholder="name or id"
              value={actorFilter}
              onChange={(e) => updateParam("actor", e.target.value)}
            />
          </label>
          <button onClick={loadFirst} disabled={loading}>
            Refresh
          </button>
        </div>
      </div>

      <div className="card" style={{ padding: "1rem" }}>
        {loading && entries.length === 0 ? (
          <p>Loading...</p>
        ) : filtered.length === 0 ? (
          <p>No audit entries.</p>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
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
                  <td>{e.section}</td>
                  <td><code>{e.key}</code></td>
                  <td>{e.action}</td>
                  <td><code>{formatValue(e.old_value)}</code></td>
                  <td><code>{formatValue(e.new_value)}</code></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {nextCursor && (
          <div style={{ marginTop: "1rem", textAlign: "center" }}>
            <button onClick={loadMore} disabled={loading}>
              {loading ? "Loading..." : "Load more"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

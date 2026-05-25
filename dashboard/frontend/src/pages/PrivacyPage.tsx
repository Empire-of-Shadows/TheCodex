import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { User } from "../api/types";
import AppHeader from "../components/AppHeader";

type ScopeGuild = { id: string; name: string | null; icon: string | null };

const MUTED = { color: "var(--text-muted)" } as const;

export default function PrivacyPage() {
  const [user, setUser] = useState<User | null>(null);
  const [guilds, setGuilds] = useState<ScopeGuild[]>([]);
  const [scopeGuildId, setScopeGuildId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [confirmText, setConfirmText] = useState("");
  const [deleteResult, setDeleteResult] = useState<string | null>(null);
  const [showDeleteModal, setShowDeleteModal] = useState(false);

  useEffect(() => {
    api.me().then(setUser).catch(() => {});
    api.userDataGuilds().then(setGuilds).catch(() => setGuilds([]));
  }, []);

  const scopeGuild = useMemo(
    () => guilds.find((g) => g.id === scopeGuildId) ?? null,
    [guilds, scopeGuildId],
  );
  const scopeLabel = scopeGuild ? (scopeGuild.name ?? `Guild ${scopeGuild.id}`) : "all servers";

  async function runDelete() {
    setDeleteResult(null);
    try {
      const r = await api.deleteUserData(scopeGuildId || null);
      const total = Object.values(r.deleted).reduce((a, n) => a + n, 0);
      const where = scopeGuild ? `from ${scopeLabel}` : "across all servers";
      setDeleteResult(`Deleted ${total} record${total === 1 ? "" : "s"} ${where}.`);
      setShowDeleteModal(false);
      setConfirmText("");
    } catch (e) {
      setError(String(e));
    }
  }

  const inputStyle: React.CSSProperties = {
    width: "100%",
    padding: "0.5rem 0.75rem",
    background: "var(--bg-card)",
    border: "1px solid var(--border-subtle)",
    borderRadius: "var(--radius-sm)",
    color: "var(--text-1)",
  };

  return (
    <div className="app-layout">
      <AppHeader user={user} />

      <section className="dash-hero">
        <div className="dash-hero__orb" />
        <img className="dash-hero__sigil" src="/brand/logo-mark.png" alt="" />
        <div className="dash-hero__copy">
          <span className="dash-hero__eyebrow">Account Control</span>
          <h1 className="dash-hero__title">Privacy & Data</h1>
          <p className="dash-hero__sub">Export or delete the data Codex holds for you.</p>
        </div>
      </section>

      <div style={{ padding: "0 24px 24px" }}>
        {error && <div className="alert danger">{error}</div>}

        <div className="card" style={{ marginBottom: "1rem" }}>
          <h2 className="section-title" style={{ marginTop: 0 }}>Data Collection</h2>
          <p style={MUTED}>
            Codex records your Would-You-Rather votes, the suggestions you submit and vote
            on, and active server-boost records. Tag-tracker status is read live from your
            Discord roles and is not stored, so it is not listed below.
          </p>
        </div>

        <div className="card" style={{ marginBottom: "1rem" }}>
          <h2 className="section-title" style={{ marginTop: 0 }}>Data Scope</h2>
          <p style={MUTED}>Choose whether export and delete cover all servers or a single one.</p>
          <select
            value={scopeGuildId}
            onChange={(e) => setScopeGuildId(e.target.value)}
            style={inputStyle}
          >
            <option value="">All servers</option>
            {guilds.map((g) => (
              <option key={g.id} value={g.id}>{g.name ?? `Guild ${g.id}`}</option>
            ))}
          </select>
        </div>

        <div className="card" style={{ marginBottom: "1rem" }}>
          <h2 className="section-title" style={{ marginTop: 0 }}>Export Data</h2>
          <p style={MUTED}>
            Download a JSON file with every WYR, suggestion, and boost record Codex has for
            you in {scopeLabel}.
          </p>
          <a href={api.exportUserDataUrl(scopeGuildId || null)} className="btn btn-secondary" download>
            Download my data
          </a>
        </div>

        <div className="card" style={{ marginBottom: "1rem" }}>
          <h2 className="section-title" style={{ marginTop: 0, color: "var(--danger)" }}>Delete My Data</h2>
          <p style={MUTED}>
            Permanently removes your WYR votes, suggestions, suggestion stats, and boost
            records in {scopeLabel}. This cannot be undone.
          </p>
          <button className="btn btn-danger" onClick={() => setShowDeleteModal(true)}>
            Delete my data...
          </button>
          {deleteResult && (
            <p style={{ marginTop: "0.75rem", color: "var(--success)" }}>{deleteResult}</p>
          )}
        </div>
      </div>

      {showDeleteModal && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.65)",
            display: "grid",
            placeItems: "center",
            zIndex: 100,
          }}
          onClick={() => setShowDeleteModal(false)}
        >
          <div className="card" style={{ maxWidth: 500, width: "90%" }} onClick={(e) => e.stopPropagation()}>
            <h3 style={{ marginTop: 0 }}>Delete your data in {scopeLabel}?</h3>
            <p>
              Type <code>DELETE</code> to confirm. This wipes the WYR, suggestion, and boost
              records tied to your account in {scopeLabel}.
            </p>
            <input
              type="text"
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              placeholder="Type DELETE"
              style={{ ...inputStyle, marginBottom: "1rem" }}
            />
            <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end" }}>
              <button
                className="btn btn-secondary"
                onClick={() => {
                  setShowDeleteModal(false);
                  setConfirmText("");
                }}
              >
                Cancel
              </button>
              <button
                className="btn btn-danger"
                disabled={confirmText !== "DELETE"}
                onClick={runDelete}
              >
                Delete everything
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, type PrivacyFeatures } from "../api/client";
import type { User } from "../api/types";
import type { Guild as PickerGuild } from "../_engine/api/types";
import AppHeader from "../components/AppHeader";
import ServerPicker from "../_engine/components/overview/ServerPicker";
import { Rule, Tile } from "../_engine/components/overview/Tile";
import { ToggleField } from "../_engine/components/settings/fields";
import { formatError } from "../_engine/api/formatError";

/*
 * Privacy and data - the member's own control panel.
 *
 * Three things live here, and they do not share a scope, which is the one
 * thing the copy has to keep straight:
 *
 *   - Data collection opt-out is ACCOUNT-WIDE (every server using Codex) and
 *     FORWARD-ONLY. It never removes anything already stored.
 *   - Export and delete are scoped by the picker: one server or all of them.
 *
 * Anything that cannot be deleted is named on the page rather than quietly
 * left out of the count.
 */

/** What GET /api/user/data/guilds returns - servers Codex holds data for. */
type ScopeGuild = { id: string; name: string | null; icon: string | null };

type Feature = "wyr" | "suggestions" | "boosts" | "member_snapshot";

const FEATURES: { key: Feature; label: string; description: string }[] = [
  {
    key: "wyr",
    label: "Pause Would You Rather",
    description:
      "Your votes will be acknowledged but not counted, and you will not be able to submit questions.",
  },
  {
    key: "suggestions",
    label: "Pause suggestions",
    description:
      "Anything you suggest still posts, but always anonymously - no status messages, no record tied to you, and no editing it later - and your votes on other suggestions are acknowledged but not recorded.",
  },
  {
    key: "boosts",
    label: "Pause boost tracking",
    description:
      "Codex stops recording when you boost a server, so new boosts will not show on your dashboard or in your export.",
  },
  {
    key: "member_snapshot",
    label: "Pause member snapshot",
    description:
      "Codex stops keeping its cached copy of your server profile - your nickname, your roles and when you joined - which parts of the dashboard and the staff views read from.",
  },
];

export default function PrivacyPage() {
  const [user, setUser] = useState<User | null>(null);

  // Scope for export and delete only. The opt-out switches are account-wide.
  const [guilds, setGuilds] = useState<ScopeGuild[]>([]);
  const [guildsFailed, setGuildsFailed] = useState(false);
  const [scopeGuildId, setScopeGuildId] = useState<string | null>(null);

  // Data collection choices. `saved` is the server's copy, `draft` the edits.
  const [saved, setSaved] = useState<PrivacyFeatures | null>(null);
  const [draft, setDraft] = useState<PrivacyFeatures | null>(null);
  const [loadingPrivacy, setLoadingPrivacy] = useState(true);
  const [privacyLoadError, setPrivacyLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<
    { kind: "success" | "danger"; text: string } | null
  >(null);

  const [confirmOpen, setConfirmOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteResult, setDeleteResult] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  useEffect(() => {
    api.me().then(setUser).catch(() => {});

    api
      .userDataGuilds()
      .then((list) => {
        setGuilds(list);
        setGuildsFailed(false);
      })
      .catch(() => {
        setGuilds([]);
        setGuildsFailed(true);
      });

    api
      .getUserPrivacy()
      .then((r) => {
        setSaved(r.features);
        setDraft(r.features);
      })
      .catch((e) => {
        if ((e as Error).message === "Unauthorized") return;
        setPrivacyLoadError(
          formatError(e, "Your data collection choices could not be loaded."),
        );
      })
      .finally(() => setLoadingPrivacy(false));
  }, []);

  const scopeGuild = useMemo(
    () => guilds.find((g) => g.id === scopeGuildId) ?? null,
    [guilds, scopeGuildId],
  );
  const scopeLabel = scopeGuild
    ? (scopeGuild.name ?? `Server ${scopeGuild.id}`)
    : "all servers";

  // ServerPicker speaks the shared Guild shape. The data-guild list carries no
  // setup state, and every server in it is one Codex is already in.
  const pickerGuilds: PickerGuild[] = useMemo(
    () =>
      guilds.map((g) => ({
        id: g.id,
        name: g.name ?? `Server ${g.id}`,
        icon: g.icon,
        bot_in_guild: true,
        has_config: true,
        setup_required: false,
      })),
    [guilds],
  );

  const scopeMeta = scopeGuild
    ? "Export and delete cover this server only"
    : guilds.length === 0
      ? "Codex holds no server data for you yet"
      : guilds.length === 1
        ? "Export and delete cover your one server"
        : `Export and delete cover all ${guilds.length} of your servers`;

  const dirty =
    saved !== null && draft !== null && JSON.stringify(saved) !== JSON.stringify(draft);

  const setFeature = (key: Feature | "all", value: boolean) => {
    setSaveMessage(null);
    setDraft((prev) => (prev ? { ...prev, [key]: value } : prev));
  };

  async function savePrivacy() {
    if (!draft) return;
    setSaving(true);
    setSaveMessage(null);
    try {
      const r = await api.saveUserPrivacy(draft);
      setSaved(r.features);
      setDraft(r.features);
      setSaveMessage({
        kind: "success",
        text: "Saved. Your choices apply everywhere within about a minute.",
      });
    } catch (e) {
      setSaveMessage({ kind: "danger", text: formatError(e, "Your choices were not saved.") });
    } finally {
      setSaving(false);
    }
  }

  async function runDelete() {
    setDeleteResult(null);
    setDeleteError(null);
    setDeleting(true);
    try {
      const r = await api.deleteUserData(scopeGuildId);
      const total = Object.values(r.deleted).reduce((a, n) => a + n, 0);
      const where = scopeGuild ? `from ${scopeLabel}` : "across all servers";
      setDeleteResult(`Deleted ${total} record${total === 1 ? "" : "s"} ${where}.`);
    } catch (e) {
      setDeleteError(formatError(e, "Your data could not be deleted."));
    } finally {
      setDeleting(false);
      setConfirmOpen(false);
    }
  }

  const allPaused = draft?.all ?? false;

  return (
    <div className="app-layout">
      <AppHeader user={user} />

      <section className="dash-hero">
        <div className="dash-hero__orb" />
        <img className="dash-hero__sigil" src="/brand/logo-mark.png" alt="" />
        <div className="dash-hero__copy">
          <span className="dash-hero__eyebrow">Account Control</span>
          <h1 className="dash-hero__title">Privacy &amp; Data</h1>
          <p className="dash-hero__sub">
            Choose what Codex records about you, download a copy of what it already has,
            or delete it.
          </p>
        </div>
      </section>

      <div className="page">
        <h2 className="section-title" style={{ margin: "24px 0 12px" }}>
          Data collection
        </h2>

        <div className="ov-grid">
          <Tile span={12} title="What Codex records about you">
            <p className="ov-body">
              These switches stop Codex from recording anything new about you. They apply
              to your account everywhere - in every server that uses Codex, not just one -
              and take effect within about a minute.
            </p>
            <p className="ov-muted">
              They only stop future collection. Nothing already stored is removed by
              turning a switch on - use "Delete your data" below for that.
            </p>

            <Rule />

            {loadingPrivacy ? (
              <p className="ov-muted">Loading your choices...</p>
            ) : privacyLoadError ? (
              <p className="alert danger" role="alert">
                {privacyLoadError}
              </p>
            ) : draft ? (
              <>
                <ToggleField
                  label="Pause all data collection"
                  value={draft.all}
                  disabled={saving}
                  onChange={(v) => setFeature("all", v)}
                  description="One switch for all four below. Codex keeps working for you, it just stops writing anything new down about you."
                />

                <Rule />

                {allPaused && (
                  <p className="ov-muted">
                    All four below are paused by the switch above. Turn it off to choose
                    feature by feature.
                  </p>
                )}

                {FEATURES.map((feature) => (
                  <ToggleField
                    key={feature.key}
                    label={feature.label}
                    value={allPaused || draft[feature.key]}
                    disabled={allPaused || saving}
                    onChange={(v) => setFeature(feature.key, v)}
                    description={feature.description}
                  />
                ))}

                <div className="admin-actions" style={{ alignItems: "center", flexWrap: "wrap" }}>
                  <button
                    type="button"
                    className="btn btn-primary"
                    disabled={!dirty || saving}
                    onClick={savePrivacy}
                  >
                    {saving ? "Saving..." : "Save choices"}
                  </button>
                  <span className="ov-muted">
                    {dirty ? "Unsaved changes" : "Everything here is saved"}
                  </span>
                </div>

                {saveMessage && (
                  <p
                    className={saveMessage.kind === "danger" ? "alert danger" : "ov-muted"}
                    role={saveMessage.kind === "danger" ? "alert" : "status"}
                  >
                    {saveMessage.text}
                  </p>
                )}
              </>
            ) : null}
          </Tile>
        </div>

        <h2 className="section-title" style={{ margin: "28px 0 0" }}>
          Export and delete
        </h2>

        <div className="ov-command">
          <ServerPicker
            guilds={pickerGuilds}
            selectedGuildId={scopeGuildId}
            onSelect={(id) => {
              setScopeGuildId(id);
              setDeleteResult(null);
              setDeleteError(null);
            }}
            meta={scopeMeta}
          />
          <span className="ov-muted">
            One choice for both sections below. It does not affect the switches above,
            which always apply to every server.
          </span>
        </div>

        {guildsFailed && (
          <p className="ov-muted">
            Your server list could not be loaded, so only the all-servers option is
            available here. Reload the page to try again.
          </p>
        )}

        <div className="ov-grid">
          <Tile span={6} title="Export your data">
            <p className="ov-body">
              Download a JSON file with everything Codex holds for you in {scopeLabel}:
            </p>
            <ul className="ov-body" style={{ margin: 0, paddingLeft: "1.1rem" }}>
              <li>Would You Rather votes and the questions you submitted</li>
              <li>Suggestions you sent and the votes you cast on other suggestions</li>
              <li>Your notification preferences</li>
              <li>Your member profile snapshots</li>
              <li>Your boost history</li>
              <li>Your whitelist entry, if staff added one</li>
              <li>Admin audit entries, if you have taken admin actions</li>
            </ul>
            <p className="ov-muted">
              Suggestions you sent anonymously are not in the file - nothing links them to
              you, so there is nothing to look up.
            </p>
            <div className="admin-actions">
              <a
                href={api.exportUserDataUrl(scopeGuildId)}
                className="btn btn-secondary"
                download
              >
                Download my data
              </a>
            </div>
          </Tile>

          <Tile span={6} title="Delete your data">
            <p className="ov-body">
              Permanently removes your Would You Rather votes and question submissions,
              your suggestions and suggestion votes, your notification preferences, your
              member profile snapshots and your boost history in {scopeLabel}. This cannot
              be undone.
            </p>

            <Rule />

            <span className="ov-card__title">What stays behind</span>
            <ul className="ov-body" style={{ margin: 0, paddingLeft: "1.1rem" }}>
              <li>
                Your whitelist entry, if staff added one. It is a moderation record staff
                wrote, and it is also what grants your access, so only staff can remove it.
                It is still included in your export.
              </li>
              <li>
                Audit entries for admin actions you took, so a server keeps a complete
                history of who changed what.
              </li>
              <li>
                Suggestions you sent anonymously. Nothing links them to you, so they cannot
                be found and removed.
              </li>
              <li>
                Your data collection choices above, so opting out survives an erasure.
              </li>
            </ul>

            <div className="admin-actions">
              <button
                type="button"
                className="btn btn-danger"
                disabled={deleting}
                onClick={() => {
                  setDeleteResult(null);
                  setDeleteError(null);
                  setConfirmOpen(true);
                }}
              >
                {deleting ? "Deleting..." : "Delete my data..."}
              </button>
            </div>

            {deleteResult && (
              <p style={{ color: "var(--success)", margin: 0 }} role="status">
                {deleteResult}
              </p>
            )}
            {deleteError && (
              <p className="alert danger" role="alert">
                {deleteError}
              </p>
            )}
          </Tile>
        </div>

        <p className="ov-muted" style={{ margin: "20px 0 28px" }}>
          The full <Link to="/privacy">privacy policy</Link> explains what Codex stores and
          why.
        </p>
      </div>

      {confirmOpen && (
        <DeleteConfirm
          scopeLabel={scopeLabel}
          deleting={deleting}
          onConfirm={runDelete}
          onCancel={() => setConfirmOpen(false)}
        />
      )}
    </div>
  );
}

/**
 * Type-DELETE confirmation for the erase button.
 *
 * Written here rather than reached for from ConfirmDialog because that shared
 * dialog has no typed-confirmation step and is not this page's file to change.
 * The behaviour it does have is kept: the same .confirm-* markup, focus moved
 * into the dialog on open and handed back to whatever opened it on close, and
 * Escape or a backdrop click cancelling. Tab is additionally kept inside the
 * dialog, which matters more here than on a one-button confirm.
 *
 * Mounted only while open, so each opening starts with an empty box.
 */
function DeleteConfirm({
  scopeLabel,
  deleting,
  onConfirm,
  onCancel,
}: {
  scopeLabel: string;
  deleting: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const [text, setText] = useState("");
  const dialogRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const previousActive = useRef<HTMLElement | null>(null);
  // Held in a ref so the key handler is installed once on open. The parent
  // passes a fresh closure every render; depending on it would re-run the
  // effect mid-typing and steal focus back to the input.
  const cancelRef = useRef(onCancel);
  cancelRef.current = onCancel;

  useEffect(() => {
    previousActive.current = document.activeElement as HTMLElement | null;
    inputRef.current?.focus();

    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.preventDefault();
        cancelRef.current();
        return;
      }
      if (e.key !== "Tab") return;
      const dialog = dialogRef.current;
      if (!dialog) return;
      // Rebuilt on every Tab because the confirm button is disabled until the
      // word is typed, and a disabled control must not be a stop in the cycle.
      const stops = Array.from(
        dialog.querySelectorAll<HTMLElement>("input, button"),
      ).filter((node) => !node.hasAttribute("disabled"));
      if (stops.length === 0) return;
      const first = stops[0];
      const last = stops[stops.length - 1];
      const active = document.activeElement;
      if (!dialog.contains(active)) {
        e.preventDefault();
        first.focus();
      } else if (e.shiftKey && active === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      previousActive.current?.focus?.();
    };
    // Runs once for the lifetime of one opening; the cancel closure is a ref.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const armed = text === "DELETE" && !deleting;

  return (
    <div
      className="confirm-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="privacy-delete-title"
      aria-describedby="privacy-delete-message"
      onClick={onCancel}
    >
      <div className="confirm-dialog" ref={dialogRef} onClick={(e) => e.stopPropagation()}>
        <h2 id="privacy-delete-title" className="confirm-title">
          Delete your data in {scopeLabel}?
        </h2>
        <p id="privacy-delete-message" className="confirm-message">
          This removes your Would You Rather votes and question submissions, your
          suggestions and suggestion votes, your notification preferences, your member
          profile snapshots and your boost history in {scopeLabel}. Your whitelist entry,
          admin audit entries, anonymous suggestions and your data collection choices
          stay. This cannot be undone.
        </p>

        <div className="eos-field">
          <label htmlFor="privacy-delete-confirm">Type DELETE to confirm</label>
          <input
            id="privacy-delete-confirm"
            ref={inputRef}
            type="text"
            value={text}
            disabled={deleting}
            autoComplete="off"
            placeholder="DELETE"
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && armed) onConfirm();
            }}
          />
        </div>

        <div className="confirm-actions">
          <button
            type="button"
            className="btn btn-secondary"
            disabled={deleting}
            onClick={onCancel}
          >
            Cancel
          </button>
          <button type="button" className="btn btn-danger" disabled={!armed} onClick={onConfirm}>
            {deleting ? "Deleting..." : "Delete everything"}
          </button>
        </div>
      </div>
    </div>
  );
}

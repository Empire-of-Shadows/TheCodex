import { useState } from "react";
import type { BoardResponse } from "../../api/types";

/**
 * Board response switcher.
 *
 * A board is one static message plus a flat pool of named private responses, so
 * this is a simple list rather than the guide's nested tree. Reuses the
 * `page-tree*` styles so both builders look like the same tool.
 */

export const BOARD_MAIN_ID = "__board__";

interface Props {
  responses: BoardResponse[];
  /** BOARD_MAIN_ID for the board message itself, or a response id. */
  currentId: string;
  /** Response ids referenced by at least one button or option. */
  usedIds: Set<string>;
  onSelect: (id: string) => void;
  onAdd: (id: string, label: string) => void;
  onDelete: (id: string) => void;
  onRename: (id: string, label: string) => void;
}

/** Mirrors _RESPONSE_ID_RE in board_schema.py. */
const RESPONSE_ID_RE = /^[a-z0-9][a-z0-9_-]{0,47}$/;

function slugify(label: string): string {
  return (
    label
      .toLowerCase()
      .trim()
      .replace(/[^a-z0-9\s-]/g, "")
      .replace(/[\s-]+/g, "-")
      .replace(/^-|-$/g, "")
      .slice(0, 48) || "response"
  );
}

export default function ResponseListEditor({
  responses,
  currentId,
  usedIds,
  onSelect,
  onAdd,
  onDelete,
  onRename,
}: Props) {
  const [creating, setCreating] = useState(false);
  const [newLabel, setNewLabel] = useState("");
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");

  const existingIds = new Set(responses.map((r) => r.id));

  const uniqueId = (base: string): string => {
    if (!existingIds.has(base)) return base;
    let i = 2;
    while (existingIds.has(`${base}-${i}`)) i++;
    return `${base}-${i}`;
  };

  const submitCreate = () => {
    const label = newLabel.trim();
    if (!label) return;
    const id = uniqueId(slugify(label));
    if (!RESPONSE_ID_RE.test(id)) return;
    onAdd(id, label);
    setNewLabel("");
    setCreating(false);
  };

  const submitRename = (id: string) => {
    const label = renameValue.trim();
    if (label) onRename(id, label);
    setRenamingId(null);
  };

  return (
    <div className="palette-section">
      <div className="page-tree-header">
        <span>Board</span>
        <button
          className="btn btn-primary"
          style={{ fontSize: 11, padding: "2px 8px" }}
          onClick={() => setCreating(true)}
          title="Add a private response"
        >
          + Response
        </button>
      </div>

      <div className="page-tree">
        <div
          className={`page-tree-item${currentId === BOARD_MAIN_ID ? " active" : ""}`}
          onClick={() => onSelect(BOARD_MAIN_ID)}
        >
          <span style={{ flex: 1 }}>📌 Board message</span>
        </div>

        {responses.length > 0 && (
          <div
            style={{
              fontSize: 10,
              textTransform: "uppercase",
              letterSpacing: "0.04em",
              color: "var(--dc-text-muted)",
              padding: "10px 6px 4px",
            }}
          >
            Private responses
          </div>
        )}

        {responses.map((resp) => {
          const unused = !usedIds.has(resp.id);
          return (
            <div
              key={resp.id}
              className={`page-tree-item${currentId === resp.id ? " active" : ""}`}
              onClick={() => onSelect(resp.id)}
            >
              {renamingId === resp.id ? (
                <input
                  className="page-rename-input"
                  value={renameValue}
                  autoFocus
                  onClick={(e) => e.stopPropagation()}
                  onChange={(e) => setRenameValue(e.target.value)}
                  onBlur={() => submitRename(resp.id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") submitRename(resp.id);
                    if (e.key === "Escape") setRenamingId(null);
                  }}
                />
              ) : (
                <span style={{ flex: 1, minWidth: 0 }}>
                  <span
                    style={{
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                      display: "block",
                    }}
                  >
                    {resp.label || resp.id}
                  </span>
                  <span style={{ fontSize: 10, color: "var(--dc-text-muted)" }}>
                    {resp.id}
                    {unused && " - not linked yet"}
                  </span>
                </span>
              )}

              <div className="page-tree-actions">
                <button
                  title="Rename"
                  onClick={(e) => {
                    e.stopPropagation();
                    setRenamingId(resp.id);
                    setRenameValue(resp.label || resp.id);
                  }}
                >
                  ✏️
                </button>
                <button
                  title="Delete"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDelete(resp.id);
                  }}
                >
                  🗑️
                </button>
              </div>
            </div>
          );
        })}

        {responses.length === 0 && (
          <div style={{ fontSize: 12, color: "var(--dc-text-muted)", padding: "8px 6px" }}>
            Add a response, then point a button or dropdown option at it. Clicking it
            sends that response privately.
          </div>
        )}
      </div>

      {creating && (
        <div className="page-create-overlay" onClick={() => setCreating(false)}>
          <div className="page-create-dialog" onClick={(e) => e.stopPropagation()}>
            <h3 style={{ marginBottom: 8, fontSize: 14 }}>New response</h3>
            <input
              autoFocus
              placeholder="Name (e.g. Server Rules)"
              value={newLabel}
              onChange={(e) => setNewLabel(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") submitCreate();
                if (e.key === "Escape") setCreating(false);
              }}
            />
            {newLabel.trim() && (
              <div style={{ fontSize: 11, color: "var(--dc-text-muted)", marginTop: 6 }}>
                id: <code>{uniqueId(slugify(newLabel))}</code>
              </div>
            )}
            <div className="page-create-actions">
              <button className="btn btn-secondary" onClick={() => setCreating(false)}>
                Cancel
              </button>
              <button
                className="btn btn-primary"
                onClick={submitCreate}
                disabled={!newLabel.trim()}
              >
                Add
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

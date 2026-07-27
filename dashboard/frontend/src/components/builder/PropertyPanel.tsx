import { useState } from "react";
import type { ComponentDef, BuilderMode, GuidePage, Channel, Role, BoardResponse } from "../../api/types";
import { VALID_ACTIONS } from "../../api/types";

let _childId = 1;
function childUid(): string {
  return `child-${Date.now()}-${_childId++}`;
}

const CONTAINER_CHILD_TYPES = ["text", "separator", "section", "action_row", "media_gallery"] as const;

interface Props {
  component: ComponentDef | null;
  mode: BuilderMode;
  pages: GuidePage[];
  channels: Channel[];
  roles: Role[];
  boardResponses: BoardResponse[];
  onChange: (updated: ComponentDef) => void;
}

function collectPageIds(pages: GuidePage[]): { id: string; label: string }[] {
  const result: { id: string; label: string }[] = [];
  function walk(ps: GuidePage[]) {
    for (const p of ps) {
      result.push({ id: p.id, label: p.label });
      if (p.children) walk(p.children);
    }
  }
  walk(pages);
  return result;
}

export default function PropertyPanel({ component, mode, pages, channels, roles, boardResponses, onChange }: Props) {
  if (!component) {
    return (
      <div className="property-panel">
        <h3>Properties</h3>
        <p style={{ color: "var(--dc-text-muted)", fontSize: 13 }}>Select a component to edit</p>
      </div>
    );
  }

  const update = (patch: Partial<ComponentDef>) => {
    const merged = { ...component, ...patch } as Record<string, unknown>;
    for (const k of Object.keys(merged)) {
      if (merged[k] === undefined) delete merged[k];
    }
    onChange(merged as ComponentDef);
  };

  const comp = component as Record<string, any>;

  return (
    <div className="property-panel">
      <h3>Properties - {component.type}</h3>

      {component.type === "text" && (
        <div className="property-group">
          <label>Content (Markdown)</label>
          <textarea
            value={comp.content || ""}
            onChange={(e) => update({ content: e.target.value } as any)}
            maxLength={4000}
            rows={6}
          />
          <span style={{ fontSize: 11, color: "var(--dc-text-muted)" }}>
            {(comp.content || "").length}/4000
          </span>
        </div>
      )}

      {component.type === "section" && <SectionProps comp={comp} mode={mode} pages={pages} channels={channels} roles={roles} boardResponses={boardResponses} update={update} />}
      {component.type === "action_row" && <ActionRowProps comp={comp} mode={mode} pages={pages} channels={channels} roles={roles} boardResponses={boardResponses} update={update} />}
      {component.type === "container" && <ContainerProps comp={comp} mode={mode} pages={pages} channels={channels} roles={roles} boardResponses={boardResponses} update={update} />}
      {component.type === "media_gallery" && <MediaGalleryProps comp={comp} update={update} />}
      {component.type === "separator" && (
        <p style={{ color: "var(--dc-text-muted)", fontSize: 13 }}>Separator has no editable properties.</p>
      )}
    </div>
  );
}

// ── Shared types for sub-editors ────────────────────────────────────────

interface EditorResources {
  mode: BuilderMode;
  pages: GuidePage[];
  channels: Channel[];
  roles: Role[];
  /** Board mode only: the response pool a "reply" action can point at. */
  boardResponses: BoardResponse[];
}

// ── Section ──────────────────────────────────────────────────────────────

function SectionProps({ comp, mode, pages, channels, roles, boardResponses, update }: { comp: any; update: (p: any) => void } & EditorResources) {
  const content = comp.content || [{ type: "text", content: "" }];
  const accessory = comp.accessory || { type: "thumbnail", media: "member_avatar" };

  const updateText = (idx: number, text: string) => {
    const newContent = [...content];
    newContent[idx] = { type: "text", content: text };
    update({ content: newContent });
  };

  return (
    <>
      <div className="property-group">
        <label>Text fields (1-3)</label>
        {content.map((t: any, i: number) => (
          <textarea
            key={i}
            value={t.content || ""}
            onChange={(e) => updateText(i, e.target.value)}
            rows={2}
            placeholder={`Text ${i + 1}`}
          />
        ))}
        {content.length < 3 && (
          <button
            className="btn btn-secondary"
            style={{ fontSize: 12 }}
            onClick={() => update({ content: [...content, { type: "text", content: "" }] })}
          >
            + Add Text
          </button>
        )}
      </div>
      <div className="property-group">
        <label>Accessory type</label>
        <select
          value={accessory.type}
          onChange={(e) => {
            if (e.target.value === "thumbnail") {
              update({ accessory: { type: "thumbnail", media: "member_avatar" } });
            } else {
              update({ accessory: { type: "button", style: "secondary", label: "Button" } });
            }
          }}
        >
          <option value="thumbnail">Thumbnail</option>
          <option value="button">Button</option>
        </select>
        {accessory.type === "button" && (
          <ButtonEditor
            button={accessory}
            mode={mode}
            pages={pages}
            channels={channels}
            roles={roles}
            boardResponses={boardResponses}
            onChange={(btn) => update({ accessory: btn })}
          />
        )}
      </div>
    </>
  );
}

// ── Action Row ───────────────────────────────────────────────────────────

function ActionRowProps({ comp, mode, pages, channels, roles, boardResponses, update }: { comp: any; update: (p: any) => void } & EditorResources) {
  const hasSelect = !!comp.select;
  const buttons = comp.buttons || [];
  const select = comp.select || { placeholder: "", options: [] };

  return (
    <>
      <div className="property-group">
        <label>Row type</label>
        <select
          value={hasSelect ? "select" : "buttons"}
          onChange={(e) => {
            if (e.target.value === "select") {
              const defaultAction =
                mode === "guide" ? "navigate" : mode === "board" ? "reply" : "server_info";
              update({ select: { placeholder: "Choose...", options: [{ label: "Option 1", action: defaultAction, target: "" }] }, buttons: undefined });
            } else {
              update({ buttons: [{ type: "button", style: "primary", label: "Button" }], select: undefined });
            }
          }}
        >
          <option value="buttons">Buttons</option>
          <option value="select">Select Menu</option>
        </select>
      </div>

      {hasSelect ? (
        <SelectEditor select={select} mode={mode} pages={pages} channels={channels} roles={roles} boardResponses={boardResponses} onChange={(s) => update({ select: s })} />
      ) : (
        <div className="property-group">
          <label>Buttons (1-5)</label>
          {buttons.map((btn: any, i: number) => (
            <div key={i} style={{ background: "var(--dc-bg-tertiary)", padding: 8, borderRadius: 4, marginBottom: 4 }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                <span style={{ fontSize: 11, color: "var(--dc-text-muted)" }}>Button {i + 1}</span>
                <button
                  style={{ background: "none", border: "none", color: "var(--dc-button-danger)", cursor: "pointer", fontSize: 12 }}
                  onClick={() => {
                    const nb = buttons.filter((_: any, j: number) => j !== i);
                    update({ buttons: nb.length ? nb : undefined, select: nb.length ? undefined : comp.select });
                  }}
                >
                  Remove
                </button>
              </div>
              <ButtonEditor
                button={btn}
                mode={mode}
                pages={pages}
                channels={channels}
                roles={roles}
                boardResponses={boardResponses}
                onChange={(updated) => {
                  const nb = [...buttons];
                  nb[i] = updated;
                  update({ buttons: nb });
                }}
              />
            </div>
          ))}
          {buttons.length < 5 && (
            <button
              className="btn btn-secondary"
              style={{ fontSize: 12 }}
              onClick={() => update({ buttons: [...buttons, { type: "button", style: "secondary", label: "Button" }] })}
            >
              + Add Button
            </button>
          )}
        </div>
      )}
    </>
  );
}

// ── Board Action Picker ─────────────────────────────────────────────────

/**
 * What a board button or option does. "reply" is the headline case: it points at
 * a response the admin wrote, which the bot sends privately to whoever clicks.
 */
function BoardActionPicker({
  action,
  target,
  boardResponses,
  channels,
  roles,
  onChange,
}: {
  action: string;
  target: string;
  boardResponses: BoardResponse[];
  channels: Channel[];
  roles: Role[];
  onChange: (action: string, target: string) => void;
}) {
  const current = action || "reply";
  return (
    <>
      <select value={current} onChange={(e) => onChange(e.target.value, "")}>
        <option value="reply">Send a private reply</option>
        <option value="channel">Link to Channel</option>
        <option value="role">Give / Toggle Role</option>
      </select>
      {current === "reply" ? (
        boardResponses.length === 0 ? (
          <div style={{ fontSize: 11, color: "var(--dc-text-muted)", marginTop: 4 }}>
            No responses yet - add one in the Board list on the left, then pick it here.
          </div>
        ) : (
          <select value={target || ""} onChange={(e) => onChange("reply", e.target.value)}>
            <option value="">Select response...</option>
            {boardResponses.map((r) => (
              <option key={r.id} value={r.id}>{r.label || r.id}</option>
            ))}
          </select>
        )
      ) : current === "channel" ? (
        <select value={target || ""} onChange={(e) => onChange("channel", e.target.value)}>
          <option value="">Select channel...</option>
          {channels.map((ch) => (
            <option key={ch.id} value={ch.id}>#{ch.name}</option>
          ))}
        </select>
      ) : (
        <select value={target || ""} onChange={(e) => onChange("role", e.target.value)}>
          <option value="">Select role...</option>
          {roles.map((r) => (
            <option key={r.id} value={r.id} style={r.color ? { color: `#${r.color.toString(16).padStart(6, "0")}` } : undefined}>
              @{r.name}
            </option>
          ))}
        </select>
      )}
    </>
  );
}

// ── Guide Action Picker ─────────────────────────────────────────────────

function GuideActionPicker({
  action,
  target,
  pages,
  channels,
  roles,
  onChange,
}: {
  action: string;
  target: string;
  pages: GuidePage[];
  channels: Channel[];
  roles: Role[];
  onChange: (action: string, target: string) => void;
}) {
  const pageIds = collectPageIds(pages);

  return (
    <>
      <select
        value={action || "navigate"}
        onChange={(e) => onChange(e.target.value, "")}
      >
        <option value="navigate">Navigate to Page</option>
        <option value="channel">Link to Channel</option>
        <option value="role">Give / Toggle Role</option>
      </select>
      {action === "navigate" || !action ? (
        <select value={target || ""} onChange={(e) => onChange(action || "navigate", e.target.value)}>
          <option value="">Select page...</option>
          {pageIds.map((p) => (
            <option key={p.id} value={p.id}>{p.label}</option>
          ))}
        </select>
      ) : action === "channel" ? (
        <select value={target || ""} onChange={(e) => onChange("channel", e.target.value)}>
          <option value="">Select channel...</option>
          {channels.map((ch) => (
            <option key={ch.id} value={ch.id}>#{ch.name}</option>
          ))}
        </select>
      ) : action === "role" ? (
        <select value={target || ""} onChange={(e) => onChange("role", e.target.value)}>
          <option value="">Select role...</option>
          {roles.map((r) => (
            <option key={r.id} value={r.id} style={r.color ? { color: `#${r.color.toString(16).padStart(6, "0")}` } : undefined}>
              @{r.name}
            </option>
          ))}
        </select>
      ) : null}
    </>
  );
}

// ── Button Editor ────────────────────────────────────────────────────────

function ButtonEditor({
  button,
  mode,
  pages,
  channels,
  roles,
  boardResponses,
  onChange,
}: {
  button: any;
  onChange: (btn: any) => void;
} & EditorResources) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <select value={button.style || "secondary"} onChange={(e) => {
        const newStyle = e.target.value;
        if (newStyle === "link") {
          // Switching TO link: remove action/target, keep url
          const { action, target, ...rest } = button;
          onChange({ ...rest, style: newStyle });
        } else if (button.style === "link") {
          // Switching FROM link: remove url, keep action/target
          const { url, ...rest } = button;
          onChange({ ...rest, style: newStyle });
        } else {
          onChange({ ...button, style: newStyle });
        }
      }}>
        <option value="primary">Primary (Blue)</option>
        <option value="secondary">Secondary (Gray)</option>
        <option value="success">Success (Green)</option>
        <option value="danger">Danger (Red)</option>
        <option value="link">Link (URL)</option>
      </select>
      <input
        type="text"
        value={button.label || ""}
        onChange={(e) => onChange({ ...button, label: e.target.value })}
        placeholder="Label"
        maxLength={80}
      />
      <input
        type="text"
        value={button.emoji || ""}
        onChange={(e) => onChange({ ...button, emoji: e.target.value || undefined })}
        placeholder="Emoji (optional)"
      />
      {button.style === "link" ? (
        <input
          type="text"
          value={button.url || ""}
          onChange={(e) => onChange({ ...button, url: e.target.value, action: undefined, target: undefined })}
          placeholder="https://..."
        />
      ) : mode === "guide" ? (
        <GuideActionPicker
          action={button.action || "navigate"}
          target={button.target || ""}
          pages={pages}
          channels={channels}
          roles={roles}
          onChange={(action, target) => onChange({ ...button, action, target, url: undefined })}
        />
      ) : mode === "board" ? (
        <BoardActionPicker
          action={button.action || "reply"}
          target={button.target || ""}
          boardResponses={boardResponses}
          channels={channels}
          roles={roles}
          onChange={(action, target) => onChange({ ...button, action, target, url: undefined })}
        />
      ) : (
        <select
          value={button.action || ""}
          onChange={(e) => onChange({ ...button, action: e.target.value, url: undefined, target: undefined })}
        >
          <option value="">Select action...</option>
          {Object.entries(VALID_ACTIONS).map(([key, val]) => (
            <option key={key} value={key}>{key} - {val.description}</option>
          ))}
        </select>
      )}
    </div>
  );
}

// ── Select Editor ────────────────────────────────────────────────────────

function SelectEditor({
  select,
  mode,
  pages,
  channels,
  roles,
  boardResponses,
  onChange,
}: {
  select: any;
  onChange: (s: any) => void;
} & EditorResources) {
  const options = select.options || [];

  return (
    <div className="property-group">
      <label>Placeholder</label>
      <input
        type="text"
        value={select.placeholder || ""}
        onChange={(e) => onChange({ ...select, placeholder: e.target.value })}
        maxLength={150}
      />
      <label>Options (1-25)</label>
      {options.map((opt: any, i: number) => (
        <div key={i} style={{ background: "var(--dc-bg-tertiary)", padding: 6, borderRadius: 4, display: "flex", flexDirection: "column", gap: 4 }}>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ fontSize: 11, color: "var(--dc-text-muted)" }}>Option {i + 1}</span>
            {options.length > 1 && (
              <button
                style={{ background: "none", border: "none", color: "var(--dc-button-danger)", cursor: "pointer", fontSize: 12 }}
                onClick={() => {
                  const no = options.filter((_: any, j: number) => j !== i);
                  onChange({ ...select, options: no });
                }}
              >
                Remove
              </button>
            )}
          </div>
          <input
            type="text"
            value={opt.label || ""}
            onChange={(e) => {
              const no = [...options];
              no[i] = { ...no[i], label: e.target.value };
              onChange({ ...select, options: no });
            }}
            placeholder="Label"
            maxLength={100}
          />
          <input
            type="text"
            value={opt.description || ""}
            onChange={(e) => {
              const no = [...options];
              no[i] = { ...no[i], description: e.target.value || undefined };
              onChange({ ...select, options: no });
            }}
            placeholder="Description (optional)"
            maxLength={100}
          />
          {mode === "guide" ? (
            <GuideActionPicker
              action={opt.action || "navigate"}
              target={opt.target || ""}
              pages={pages}
              channels={channels}
              roles={roles}
              onChange={(action, target) => {
                const no = [...options];
                no[i] = { ...no[i], action, target };
                onChange({ ...select, options: no });
              }}
            />
          ) : mode === "board" ? (
            <BoardActionPicker
              action={opt.action || "reply"}
              target={opt.target || ""}
              boardResponses={boardResponses}
              channels={channels}
              roles={roles}
              onChange={(action, target) => {
                const no = [...options];
                no[i] = { ...no[i], action, target };
                onChange({ ...select, options: no });
              }}
            />
          ) : (
            <select
              value={opt.action || ""}
              onChange={(e) => {
                const no = [...options];
                no[i] = { ...no[i], action: e.target.value };
                onChange({ ...select, options: no });
              }}
            >
              <option value="">Select action...</option>
              {Object.entries(VALID_ACTIONS).map(([key, val]) => (
                <option key={key} value={key}>{key} - {val.description}</option>
              ))}
            </select>
          )}
        </div>
      ))}
      {options.length < 25 && (
        <button
          className="btn btn-secondary"
          style={{ fontSize: 12 }}
          onClick={() =>
            onChange({
              ...select,
              options: [
                ...options,
                {
                  label: "",
                  action: mode === "guide" ? "navigate" : mode === "board" ? "reply" : "",
                  target: "",
                },
              ],
            })
          }
        >
          + Add Option
        </button>
      )}
    </div>
  );
}

// ── Container ────────────────────────────────────────────────────────────

function ContainerProps({ comp, mode, pages, channels, roles, boardResponses, update }: { comp: any; update: (p: any) => void } & EditorResources) {
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
  const children: any[] = comp.components || [];

  const updateChild = (idx: number, patch: any) => {
    const nc = [...children];
    const merged = { ...nc[idx], ...patch };
    for (const k of Object.keys(merged)) {
      if (merged[k] === undefined) delete merged[k];
    }
    nc[idx] = merged;
    update({ components: nc });
  };

  const removeChild = (idx: number) => {
    const nc = children.filter((_: any, i: number) => i !== idx);
    if (expandedIdx === idx) setExpandedIdx(null);
    else if (expandedIdx !== null && expandedIdx > idx) setExpandedIdx(expandedIdx - 1);
    update({ components: nc });
  };

  const moveChild = (idx: number, dir: -1 | 1) => {
    const newIdx = idx + dir;
    if (newIdx < 0 || newIdx >= children.length) return;
    const nc = [...children];
    [nc[idx], nc[newIdx]] = [nc[newIdx], nc[idx]];
    if (expandedIdx === idx) setExpandedIdx(newIdx);
    else if (expandedIdx === newIdx) setExpandedIdx(idx);
    update({ components: nc });
  };

  const addChild = (type: string) => {
    const _id = childUid();
    let child: any;
    switch (type) {
      case "text": child = { _id, type: "text", content: "New text" }; break;
      case "separator": child = { _id, type: "separator" }; break;
      case "section": child = { _id, type: "section", content: [{ type: "text", content: "Section text" }], accessory: { type: "thumbnail", media: "member_avatar" } }; break;
      case "action_row": child = { _id, type: "action_row", buttons: [{ type: "button", style: "primary", label: "Button" }] }; break;
      case "media_gallery": child = { _id, type: "media_gallery", items: [{ media: "" }] }; break;
      default: child = { _id, type }; break;
    }
    update({ components: [...children, child] });
    setExpandedIdx(children.length);
  };

  return (
    <>
      <div className="property-group">
        <label>
          <input
            type="checkbox"
            checked={comp.accent_color != null}
            onChange={(e) => update({ accent_color: e.target.checked ? "#4e5058" : undefined })}
          />{" "}
          Accent Color
        </label>
        {comp.accent_color != null && (
          <input
            type="color"
            value={typeof comp.accent_color === "string" ? comp.accent_color : "#4e5058"}
            onChange={(e) => update({ accent_color: e.target.value })}
          />
        )}
      </div>
      <div className="property-group">
        <label>
          <input
            type="checkbox"
            checked={comp.spoiler || false}
            onChange={(e) => update({ spoiler: e.target.checked })}
          />{" "}
          Spoiler
        </label>
      </div>
      <div className="property-group">
        <label>Children ({children.length}/10)</label>
        {children.map((child: any, i: number) => (
          <div key={child._id || i} style={{ background: "var(--dc-bg-tertiary)", padding: 8, borderRadius: 4, marginBottom: 4 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: expandedIdx === i ? 8 : 0 }}>
              <span
                style={{ fontSize: 12, color: "var(--dc-text-normal)", cursor: "pointer", flex: 1 }}
                onClick={() => setExpandedIdx(expandedIdx === i ? null : i)}
              >
                {expandedIdx === i ? "▾" : "▸"} {child.type}
              </span>
              <div style={{ display: "flex", gap: 2 }}>
                <button
                  style={{ background: "none", border: "none", color: i === 0 ? "var(--dc-text-muted)" : "var(--dc-text-normal)", cursor: i === 0 ? "default" : "pointer", fontSize: 11, padding: "0 3px" }}
                  onClick={() => moveChild(i, -1)}
                  disabled={i === 0}
                >↑</button>
                <button
                  style={{ background: "none", border: "none", color: i === children.length - 1 ? "var(--dc-text-muted)" : "var(--dc-text-normal)", cursor: i === children.length - 1 ? "default" : "pointer", fontSize: 11, padding: "0 3px" }}
                  onClick={() => moveChild(i, 1)}
                  disabled={i === children.length - 1}
                >↓</button>
                <button
                  style={{ background: "none", border: "none", color: "var(--dc-button-danger)", cursor: "pointer", fontSize: 14, padding: "0 3px" }}
                  onClick={() => removeChild(i)}
                >×</button>
              </div>
            </div>
            {expandedIdx === i && (
              <ContainerChildEditor child={child} mode={mode} pages={pages} channels={channels} roles={roles} boardResponses={boardResponses} onChange={(patch) => updateChild(i, patch)} />
            )}
          </div>
        ))}
        {children.length < 10 && (
          <select
            value=""
            onChange={(e) => { if (e.target.value) addChild(e.target.value); }}
            style={{ fontSize: 12, marginTop: 4 }}
          >
            <option value="">+ Add child...</option>
            {CONTAINER_CHILD_TYPES.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        )}
      </div>
    </>
  );
}

function ContainerChildEditor({ child, mode, pages, channels, roles, boardResponses, onChange }: { child: any; onChange: (patch: any) => void } & EditorResources) {
  switch (child.type) {
    case "text":
      return (
        <div className="property-group">
          <textarea
            value={child.content || ""}
            onChange={(e) => onChange({ content: e.target.value })}
            maxLength={4000}
            rows={4}
          />
          <span style={{ fontSize: 11, color: "var(--dc-text-muted)" }}>
            {(child.content || "").length}/4000
          </span>
        </div>
      );
    case "section":
      return <SectionProps comp={child} mode={mode} pages={pages} channels={channels} roles={roles} boardResponses={boardResponses} update={onChange} />;
    case "action_row":
      return <ActionRowProps comp={child} mode={mode} pages={pages} channels={channels} roles={roles} boardResponses={boardResponses} update={onChange} />;
    case "media_gallery":
      return <MediaGalleryProps comp={child} update={onChange} />;
    case "separator":
      return <p style={{ color: "var(--dc-text-muted)", fontSize: 12 }}>No editable properties.</p>;
    default:
      return <p style={{ color: "var(--dc-text-muted)", fontSize: 12 }}>Unknown type: {child.type}</p>;
  }
}

// ── Media Gallery ────────────────────────────────────────────────────────

function MediaGalleryProps({ comp, update }: { comp: any; update: (p: any) => void }) {
  const items = comp.items || [];

  return (
    <div className="property-group">
      <label>Media Items (1-10)</label>
      {items.map((item: any, i: number) => (
        <div key={i} style={{ background: "var(--dc-bg-tertiary)", padding: 6, borderRadius: 4, display: "flex", flexDirection: "column", gap: 4 }}>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ fontSize: 11, color: "var(--dc-text-muted)" }}>Item {i + 1}</span>
            {items.length > 1 && (
              <button
                style={{ background: "none", border: "none", color: "var(--dc-button-danger)", cursor: "pointer", fontSize: 12 }}
                onClick={() => {
                  const ni = items.filter((_: any, j: number) => j !== i);
                  update({ items: ni });
                }}
              >
                Remove
              </button>
            )}
          </div>
          <input
            type="text"
            value={item.media || ""}
            onChange={(e) => {
              const ni = [...items];
              ni[i] = { ...ni[i], media: e.target.value };
              update({ items: ni });
            }}
            placeholder="https://... (image URL)"
          />
          <input
            type="text"
            value={item.description || ""}
            onChange={(e) => {
              const ni = [...items];
              ni[i] = { ...ni[i], description: e.target.value || undefined };
              update({ items: ni });
            }}
            placeholder="Description (optional)"
            maxLength={256}
          />
        </div>
      ))}
      {items.length < 10 && (
        <button
          className="btn btn-secondary"
          style={{ fontSize: 12 }}
          onClick={() => update({ items: [...items, { media: "" }] })}
        >
          + Add Item
        </button>
      )}
    </div>
  );
}

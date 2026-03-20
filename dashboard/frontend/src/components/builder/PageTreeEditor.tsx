import { useState, useRef, useEffect } from "react";
import type { GuidePage } from "../../api/types";

interface Props {
  pages: GuidePage[];
  currentPageId: string | null;
  onSelectPage: (pageId: string) => void;
  onAddPage: (parentId: string | null, label: string, icon?: string, description?: string) => void;
  onDeletePage: (pageId: string) => void;
  onRenamePage: (pageId: string, label: string) => void;
  onMovePage: (pageId: string, dir: -1 | 1) => void;
  onUpdatePageMeta: (pageId: string, field: "description" | "icon", value: string) => void;
}

function PageItem({
  page,
  depth,
  index,
  siblingCount,
  currentPageId,
  onSelectPage,
  onRequestAddPage,
  onDeletePage,
  onRenamePage,
  onMovePage,
  onUpdatePageMeta,
}: {
  page: GuidePage;
  depth: number;
  index: number;
  siblingCount: number;
  currentPageId: string | null;
  onSelectPage: (id: string) => void;
  onRequestAddPage: (parentId: string | null) => void;
  onDeletePage: (id: string) => void;
  onRenamePage: (id: string, label: string) => void;
  onMovePage: (id: string, dir: -1 | 1) => void;
  onUpdatePageMeta: (id: string, field: "description" | "icon", value: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [editValue, setEditValue] = useState(page.label);
  const [expanded, setExpanded] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const isActive = currentPageId === page.id;
  const isFirst = index === 0;
  const isLast = index === siblingCount - 1;

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editing]);

  const commitRename = () => {
    const trimmed = editValue.trim();
    if (trimmed && trimmed !== page.label) {
      onRenamePage(page.id, trimmed);
    } else {
      setEditValue(page.label);
    }
    setEditing(false);
  };

  return (
    <>
      <div
        className={`page-tree-item ${isActive ? "active" : ""}`}
        onClick={() => onSelectPage(page.id)}
      >
        {Array.from({ length: depth }).map((_, i) => (
          <span key={i} className="indent" />
        ))}
        {page.icon && <span style={{ flexShrink: 0 }}>{page.icon}</span>}

        {editing ? (
          <input
            ref={inputRef}
            className="page-rename-input"
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            onBlur={commitRename}
            onKeyDown={(e) => {
              if (e.key === "Enter") commitRename();
              if (e.key === "Escape") {
                setEditValue(page.label);
                setEditing(false);
              }
            }}
            onClick={(e) => e.stopPropagation()}
            maxLength={100}
          />
        ) : (
          <span
            style={{ flex: 1, cursor: "text", minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
            onDoubleClick={(e) => {
              e.stopPropagation();
              setEditValue(page.label);
              setEditing(true);
            }}
            title="Double-click to rename"
          >
            {page.label}
          </span>
        )}

        <div className="page-tree-actions">
          <button
            title="Move up"
            disabled={isFirst}
            onClick={(e) => { e.stopPropagation(); onMovePage(page.id, -1); }}
            style={{ opacity: isFirst ? 0.3 : 1 }}
          >
            ↑
          </button>
          <button
            title="Move down"
            disabled={isLast}
            onClick={(e) => { e.stopPropagation(); onMovePage(page.id, 1); }}
            style={{ opacity: isLast ? 0.3 : 1 }}
          >
            ↓
          </button>
          <button
            title="Edit details"
            onClick={(e) => { e.stopPropagation(); setExpanded(!expanded); }}
            style={{ color: expanded ? "var(--dc-blurple)" : undefined }}
          >
            ⚙
          </button>
          {depth < 4 && (
            <button
              title="Add child page"
              onClick={(e) => { e.stopPropagation(); onRequestAddPage(page.id); }}
            >
              +
            </button>
          )}
          <button
            title="Delete page"
            onClick={(e) => { e.stopPropagation(); onDeletePage(page.id); }}
          >
            ×
          </button>
        </div>
      </div>

      {expanded && (
        <div className="page-meta-editor" style={{ paddingLeft: depth * 16 + 8 }}>
          <label>
            Icon
            <input
              type="text"
              value={page.icon || ""}
              onChange={(e) => onUpdatePageMeta(page.id, "icon", e.target.value)}
              placeholder="e.g. 📖"
              maxLength={10}
            />
          </label>
          <label>
            Description
            <input
              type="text"
              value={page.description || ""}
              onChange={(e) => onUpdatePageMeta(page.id, "description", e.target.value)}
              placeholder="Short description"
              maxLength={100}
            />
          </label>
        </div>
      )}

      {page.children?.map((child, i) => (
        <PageItem
          key={child.id}
          page={child}
          depth={depth + 1}
          index={i}
          siblingCount={page.children!.length}
          currentPageId={currentPageId}
          onSelectPage={onSelectPage}
          onRequestAddPage={onRequestAddPage}
          onDeletePage={onDeletePage}
          onRenamePage={onRenamePage}
          onMovePage={onMovePage}
          onUpdatePageMeta={onUpdatePageMeta}
        />
      ))}
    </>
  );
}

// ── Create Page Dialog ──────────────────────────────────────────────────

function CreatePageDialog({
  parentId,
  onConfirm,
  onCancel,
}: {
  parentId: string | null;
  onConfirm: (parentId: string | null, label: string, icon?: string, description?: string) => void;
  onCancel: () => void;
}) {
  const [label, setLabel] = useState("");
  const [icon, setIcon] = useState("");
  const [description, setDescription] = useState("");
  const labelRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    labelRef.current?.focus();
  }, []);

  const handleSubmit = () => {
    const trimmed = label.trim();
    if (!trimmed) return;
    onConfirm(parentId, trimmed, icon.trim() || undefined, description.trim() || undefined);
  };

  return (
    <div className="page-create-overlay" onClick={onCancel}>
      <div className="page-create-dialog" onClick={(e) => e.stopPropagation()}>
        <h4>{parentId ? "Add Child Page" : "Add Root Page"}</h4>
        <label>
          Label <span style={{ color: "var(--dc-red)" }}>*</span>
          <input
            ref={labelRef}
            type="text"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleSubmit();
              if (e.key === "Escape") onCancel();
            }}
            placeholder="Page name"
            maxLength={100}
          />
        </label>
        <label>
          Icon
          <input
            type="text"
            value={icon}
            onChange={(e) => setIcon(e.target.value)}
            placeholder="e.g. 📖"
            maxLength={10}
          />
        </label>
        <label>
          Description
          <input
            type="text"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleSubmit();
            }}
            placeholder="Short description"
            maxLength={100}
          />
        </label>
        <div className="page-create-actions">
          <button className="btn btn-secondary" onClick={onCancel}>Cancel</button>
          <button className="btn btn-primary" onClick={handleSubmit} disabled={!label.trim()}>Create</button>
        </div>
      </div>
    </div>
  );
}

// ── Main Component ──────────────────────────────────────────────────────

export default function PageTreeEditor({
  pages,
  currentPageId,
  onSelectPage,
  onAddPage,
  onDeletePage,
  onRenamePage,
  onMovePage,
  onUpdatePageMeta,
}: Props) {
  const [createDialog, setCreateDialog] = useState<{ parentId: string | null } | null>(null);

  const handleConfirm = (parentId: string | null, label: string, icon?: string, description?: string) => {
    onAddPage(parentId, label, icon, description);
    setCreateDialog(null);
  };

  return (
    <div className="palette-section">
      <h3>Page Tree</h3>
      <div className="page-tree">
        {pages.map((page, i) => (
          <PageItem
            key={page.id}
            page={page}
            depth={0}
            index={i}
            siblingCount={pages.length}
            currentPageId={currentPageId}
            onSelectPage={onSelectPage}
            onRequestAddPage={(parentId) => setCreateDialog({ parentId })}
            onDeletePage={onDeletePage}
            onRenamePage={onRenamePage}
            onMovePage={onMovePage}
            onUpdatePageMeta={onUpdatePageMeta}
          />
        ))}
      </div>
      <button
        className="btn btn-secondary"
        style={{ marginTop: 8, width: "100%", fontSize: 12 }}
        onClick={() => setCreateDialog({ parentId: null })}
      >
        + Add Root Page
      </button>

      {createDialog && (
        <CreatePageDialog
          parentId={createDialog.parentId}
          onConfirm={handleConfirm}
          onCancel={() => setCreateDialog(null)}
        />
      )}
    </div>
  );
}
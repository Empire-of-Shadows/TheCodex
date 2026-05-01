import { useState, useRef, useEffect } from "react";
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  useSensor,
  useSensors,
  useDraggable,
  useDroppable,
  type DragStartEvent,
  type DragEndEvent,
  type DragMoveEvent,
} from "@dnd-kit/core";
import type { GuidePage } from "../../api/types";
import type { PageDropPos } from "../../pages/BuilderPage";

interface Props {
  pages: GuidePage[];
  currentPageId: string | null;
  onSelectPage: (pageId: string) => void;
  onAddPage: (parentId: string | null, label: string, icon?: string, description?: string) => void;
  onDeletePage: (pageId: string) => void;
  onRenamePage: (pageId: string, label: string) => void;
  onMovePage: (pageId: string, dir: -1 | 1) => void;
  onMovePageTo: (pageId: string, targetId: string | null, pos: PageDropPos) => void;
  onUpdatePageMeta: (pageId: string, field: "description" | "icon", value: string) => void;
}

type HoverPos = "before" | "after" | "child";

function PageItem({
  page,
  depth,
  index,
  siblingCount,
  currentPageId,
  activeDragId,
  hoverState,
  collapsedIds,
  onToggleCollapse,
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
  activeDragId: string | null;
  hoverState: { id: string; pos: HoverPos } | null;
  collapsedIds: Set<string>;
  onToggleCollapse: (id: string) => void;
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
  const isDragging = activeDragId === page.id;
  const hasChildren = !!page.children?.length;
  const isCollapsed = collapsedIds.has(page.id);

  const draggable = useDraggable({ id: `page:${page.id}`, data: { pageId: page.id } });
  const droppable = useDroppable({ id: `pagedrop:${page.id}`, data: { pageId: page.id } });

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

  const showBefore = hoverState?.id === page.id && hoverState.pos === "before";
  const showAfter = hoverState?.id === page.id && hoverState.pos === "after";
  const showChild = hoverState?.id === page.id && hoverState.pos === "child";

  const setRowRef = (el: HTMLDivElement | null) => {
    draggable.setNodeRef(el);
    droppable.setNodeRef(el);
  };

  const classes = [
    "page-tree-item",
    isActive ? "active" : "",
    isDragging ? "dragging" : "",
    showChild ? "drop-target-child" : "",
  ].filter(Boolean).join(" ");

  return (
    <>
      {showBefore && <div className="page-drop-line" style={{ marginLeft: depth * 16 }} />}
      <div
        ref={setRowRef}
        className={classes}
        onClick={() => onSelectPage(page.id)}
        {...draggable.listeners}
        {...draggable.attributes}
        style={{ touchAction: "none" }}
      >
        {Array.from({ length: depth }).map((_, i) => (
          <span key={i} className="indent" />
        ))}
        {hasChildren ? (
          <button
            type="button"
            className="page-tree-chevron"
            title={isCollapsed ? "Expand" : "Collapse"}
            onClick={(e) => { e.stopPropagation(); onToggleCollapse(page.id); }}
            onPointerDown={(e) => e.stopPropagation()}
          >
            {isCollapsed ? "▶" : "▼"}
          </button>
        ) : (
          <span className="page-tree-chevron-spacer" />
        )}
        <span className="page-drag-handle" title="Drag to move">⋮⋮</span>
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
            onPointerDown={(e) => e.stopPropagation()}
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

        <div
          className="page-tree-actions"
          onPointerDown={(e) => e.stopPropagation()}
        >
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
      {showAfter && <div className="page-drop-line" style={{ marginLeft: depth * 16 }} />}

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

      {!isCollapsed && page.children?.map((child, i) => (
        <PageItem
          key={child.id}
          page={child}
          depth={depth + 1}
          index={i}
          siblingCount={page.children!.length}
          currentPageId={currentPageId}
          activeDragId={activeDragId}
          hoverState={hoverState}
          collapsedIds={collapsedIds}
          onToggleCollapse={onToggleCollapse}
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

// ── Root drop zone ──────────────────────────────────────────────────────

function RootDropZone({ active }: { active: boolean }) {
  const { setNodeRef, isOver } = useDroppable({ id: "pagedrop:__root__", data: { pageId: null } });
  return (
    <div
      ref={setNodeRef}
      className={`page-root-dropzone${active ? " active" : ""}${isOver ? " over" : ""}`}
    >
      Drop here to make root page
    </div>
  );
}

// ── Helpers ─────────────────────────────────────────────────────────────

function collectParentIds(pages: GuidePage[], out: string[] = []): string[] {
  for (const p of pages) {
    if (p.children?.length) {
      out.push(p.id);
      collectParentIds(p.children, out);
    }
  }
  return out;
}

function findPageFlat(pages: GuidePage[], id: string): GuidePage | null {
  for (const p of pages) {
    if (p.id === id) return p;
    if (p.children) {
      const r = findPageFlat(p.children, id);
      if (r) return r;
    }
  }
  return null;
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
  onMovePageTo,
  onUpdatePageMeta,
}: Props) {
  const [createDialog, setCreateDialog] = useState<{ parentId: string | null } | null>(null);
  const [activeDragId, setActiveDragId] = useState<string | null>(null);
  const [hoverState, setHoverState] = useState<{ id: string; pos: HoverPos } | null>(null);
  const [collapsedIds, setCollapsedIds] = useState<Set<string>>(new Set());

  const toggleCollapse = (id: string) => {
    setCollapsedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const allParentIds = collectParentIds(pages);
  const allCollapsed = allParentIds.length > 0 && allParentIds.every(id => collapsedIds.has(id));

  const onExpandCollapseAll = () => {
    setCollapsedIds(allCollapsed ? new Set() : new Set(allParentIds));
  };

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } })
  );

  const handleConfirm = (parentId: string | null, label: string, icon?: string, description?: string) => {
    onAddPage(parentId, label, icon, description);
    setCreateDialog(null);
  };

  const onDragStart = (e: DragStartEvent) => {
    const id = String(e.active.id);
    if (id.startsWith("page:")) {
      setActiveDragId(id.slice(5));
    }
  };

  const onDragMove = (e: DragMoveEvent) => {
    const over = e.over;
    if (!over || !activeDragId) {
      setHoverState(null);
      return;
    }
    const overData = over.data.current as { pageId: string | null } | undefined;
    const overPageId = overData?.pageId ?? null;
    if (overPageId === null) {
      setHoverState(null);
      return;
    }
    if (overPageId === activeDragId) {
      setHoverState(null);
      return;
    }

    // Compute pointer Y relative to over rect
    const rect = over.rect;
    const activeRect = e.active.rect.current.translated;
    const pointerY = activeRect ? activeRect.top + activeRect.height / 2 : rect.top + rect.height / 2;
    const rel = (pointerY - rect.top) / rect.height;

    let pos: HoverPos;
    if (rel < 0.25) pos = "before";
    else if (rel > 0.75) pos = "after";
    else pos = "child";

    setHoverState({ id: overPageId, pos });
  };

  const onDragEnd = (e: DragEndEvent) => {
    const draggedId = activeDragId;
    const finalHover = hoverState;
    setActiveDragId(null);
    setHoverState(null);

    if (!draggedId) return;
    const over = e.over;
    if (!over) return;
    const overData = over.data.current as { pageId: string | null } | undefined;
    const overPageId = overData?.pageId ?? null;

    if (overPageId === null) {
      onMovePageTo(draggedId, null, "root-end");
      return;
    }
    if (overPageId === draggedId) return;
    if (!finalHover) return;
    onMovePageTo(draggedId, finalHover.id, finalHover.pos);
  };

  const onDragCancel = () => {
    setActiveDragId(null);
    setHoverState(null);
  };

  const draggedPage = activeDragId ? findPageFlat(pages, activeDragId) : null;

  return (
    <div className="palette-section">
      <div className="page-tree-header">
        <h3>Page Tree</h3>
        <button
          type="button"
          className="btn btn-secondary"
          style={{ fontSize: 11, padding: "2px 8px" }}
          onClick={onExpandCollapseAll}
          disabled={allParentIds.length === 0}
          title={allCollapsed ? "Expand all" : "Collapse all"}
        >
          {allCollapsed ? "Expand all" : "Collapse all"}
        </button>
      </div>
      <DndContext
        sensors={sensors}
        onDragStart={onDragStart}
        onDragMove={onDragMove}
        onDragEnd={onDragEnd}
        onDragCancel={onDragCancel}
      >
        <div className="page-tree">
          {pages.map((page, i) => (
            <PageItem
              key={page.id}
              page={page}
              depth={0}
              index={i}
              siblingCount={pages.length}
              currentPageId={currentPageId}
              activeDragId={activeDragId}
              hoverState={hoverState}
              collapsedIds={collapsedIds}
              onToggleCollapse={toggleCollapse}
              onSelectPage={onSelectPage}
              onRequestAddPage={(parentId) => setCreateDialog({ parentId })}
              onDeletePage={onDeletePage}
              onRenamePage={onRenamePage}
              onMovePage={onMovePage}
              onUpdatePageMeta={onUpdatePageMeta}
            />
          ))}
        </div>
        <RootDropZone active={activeDragId !== null} />

        <DragOverlay dropAnimation={null}>
          {draggedPage ? (
            <div className="page-tree-item drag-overlay wiggling">
              <span className="page-drag-handle">⋮⋮</span>
              {draggedPage.icon && <span style={{ flexShrink: 0 }}>{draggedPage.icon}</span>}
              <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {draggedPage.label}
              </span>
            </div>
          ) : null}
        </DragOverlay>
      </DndContext>
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

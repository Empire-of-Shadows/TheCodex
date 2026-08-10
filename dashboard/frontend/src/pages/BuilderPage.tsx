import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import { arrayMove } from "@dnd-kit/sortable";
import { api } from "../api/client";
import type {
  BuilderMode,
  Channel,
  ComponentDef,
  ComponentType,
  Guild,
  GuideData,
  GuidePage,
  Role,
  SimulationAction,
  GreetingData,
  BoardData,
  BoardResponse,
} from "../api/types";
import { VALID_ACTIONS } from "../api/types";
import { validateGuideSchema } from "../validators/guideValidator";
import { validateGreetingSchema } from "../validators/greetingValidator";
import { validateBoardSchema } from "../validators/boardValidator";
import { checkNoDangerousContent } from "../validators/safeContent";
import ComponentPalette from "../components/builder/ComponentPalette";
import PageTreeEditor from "../components/builder/PageTreeEditor";
import ResponseListEditor, { BOARD_MAIN_ID } from "../components/builder/ResponseListEditor";
import Canvas from "../components/builder/Canvas";
import SimulationCanvas from "../components/builder/SimulationCanvas";
import PropertyPanel from "../components/builder/PropertyPanel";
import ValidationErrors from "../components/builder/ValidationErrors";
import DocsPanel from "../components/builder/DocsPanel";
import ConfirmDialog from "../components/ConfirmDialog";
import { formatError } from "../_engine/api/formatError";
import { useToast, ToastStack } from "../_engine/components/ToastStack";

// Import file-size ceilings - mirror the backend byte limits
// (guide_schema.py _MAX_GUIDE_BYTES / greeting_schema.py _MAX_GREETING_BYTES).
const MAX_GUIDE_BYTES = 256 * 1024;
const MAX_GREETING_BYTES = 64 * 1024;
const MAX_BOARD_BYTES = 128 * 1024;

let _nextId = 1;
function uid(): string {
  return `comp-${Date.now()}-${_nextId++}`;
}

function newComponent(type: ComponentType): ComponentDef {
  const _id = uid();
  switch (type) {
    case "text":
      return { _id, type, content: "New text" } as any;
    case "separator":
      return { _id, type };
    case "section":
      return {
        _id,
        type,
        content: [{ type: "text", content: "Section text" }],
        accessory: { type: "thumbnail", media: "member_avatar" },
      } as any;
    case "action_row":
      return {
        _id,
        type,
        buttons: [{ type: "button", style: "primary", label: "Button" }],
      } as any;
    case "container":
      return {
        _id,
        type,
        components: [{ _id: uid(), type: "text", content: "Inside container" }],
      } as any;
    case "media_gallery":
      return { _id, type, items: [{ media: "" }] } as any;
    default:
      return { _id, type };
  }
}

function addIds(components: any[]): ComponentDef[] {
  return (components || []).map((c: any) => {
    const _id = uid();
    const result = { ...c, _id };
    if (Array.isArray(c.components)) {
      result.components = addIds(c.components);
    }
    return result;
  });
}

function addIdsToPage(page: GuidePage): GuidePage {
  return {
    ...page,
    content: page.content ? { components: addIds(page.content.components) } : undefined,
    children: page.children?.map(addIdsToPage),
  };
}

// ── Page normalization (mirrors backend normalize_pages) ────────────────

function slugify(label: string): string {
  let slug = label.toLowerCase().trim();
  slug = slug.replace(/[^a-z0-9\s-]/g, "");
  slug = slug.replace(/[\s-]+/g, "-");
  slug = slug.replace(/^-|-$/g, "");
  return slug || "page";
}

function normalizePages(pages: GuidePage[]): GuidePage[] {
  const seenIds = new Set<string>();
  let counter = 0;

  function normalize(list: GuidePage[], orderOffset: number): GuidePage[] {
    return list.map((page, i) => {
      const result = { ...page };

      // Auto-generate ID from label if missing
      if (!result.id) {
        let slug = slugify(result.label || "page");
        const base = slug;
        while (seenIds.has(slug)) {
          counter++;
          slug = `${base}-${counter}`;
        }
        result.id = slug;
      }
      seenIds.add(result.id);

      // Auto-generate order if missing
      if (result.order === undefined) {
        result.order = orderOffset + i + 1;
      }

      // Recurse into children
      if (result.children && result.children.length > 0) {
        result.children = normalize(result.children, 0);
      }

      return result;
    });
  }

  return normalize(pages, 0);
}

// ── Page tree helpers ────────────────────────────────────────────────────

function findPage(pages: GuidePage[], id: string): GuidePage | null {
  for (const p of pages) {
    if (p.id === id) return p;
    if (p.children) {
      const found = findPage(p.children, id);
      if (found) return found;
    }
  }
  return null;
}

function updatePageInTree(pages: GuidePage[], id: string, updater: (p: GuidePage) => GuidePage): GuidePage[] {
  return pages.map((p) => {
    if (p.id === id) return updater(p);
    if (p.children) return { ...p, children: updatePageInTree(p.children, id, updater) };
    return p;
  });
}

function deletePageFromTree(pages: GuidePage[], id: string): GuidePage[] {
  return pages
    .filter((p) => p.id !== id)
    .map((p) => (p.children ? { ...p, children: deletePageFromTree(p.children, id) } : p));
}

function movePageInTree(pages: GuidePage[], id: string, dir: -1 | 1): GuidePage[] {
  const idx = pages.findIndex((p) => p.id === id);
  if (idx !== -1) {
    const newIdx = idx + dir;
    if (newIdx < 0 || newIdx >= pages.length) return pages;
    const copy = [...pages];
    [copy[idx], copy[newIdx]] = [copy[newIdx], copy[idx]];
    return copy;
  }
  return pages.map((p) =>
    p.children ? { ...p, children: movePageInTree(p.children, id, dir) } : p
  );
}

function clonePageWithNewIds(page: GuidePage, existingIds: Set<string>): GuidePage {
  function uniqueSlug(base: string): string {
    let slug = `${base}-copy`;
    if (!existingIds.has(slug)) {
      existingIds.add(slug);
      return slug;
    }
    let i = 2;
    while (existingIds.has(`${base}-copy-${i}`)) i++;
    const out = `${base}-copy-${i}`;
    existingIds.add(out);
    return out;
  }
  const newId = uniqueSlug(page.id);
  return {
    ...page,
    id: newId,
    order: undefined,
    content: page.content ? { components: addIds(page.content.components) } : undefined,
    children: page.children?.map((c) => clonePageWithNewIds(c, existingIds)),
  };
}

function collectAllIds(pages: GuidePage[], out: Set<string> = new Set()): Set<string> {
  for (const p of pages) {
    out.add(p.id);
    if (p.children) collectAllIds(p.children, out);
  }
  return out;
}

function insertAfterPage(pages: GuidePage[], targetId: string, node: GuidePage): GuidePage[] {
  const out: GuidePage[] = [];
  let inserted = false;
  for (const p of pages) {
    if (p.id === targetId) {
      out.push(p, node);
      inserted = true;
    } else if (p.children) {
      const childResult = insertAfterPage(p.children, targetId, node);
      if (childResult !== p.children) inserted = true;
      out.push({ ...p, children: childResult });
    } else {
      out.push(p);
    }
  }
  return inserted ? out : pages;
}

function addChildPage(pages: GuidePage[], parentId: string | null, child: GuidePage): GuidePage[] {
  if (parentId === null) return [...pages, child];
  return pages.map((p) => {
    if (p.id === parentId) {
      return { ...p, children: [...(p.children || []), child] };
    }
    if (p.children) return { ...p, children: addChildPage(p.children, parentId, child) };
    return p;
  });
}

// ── DnD reparenting helpers ──────────────────────────────────────────────

export type PageDropPos = "before" | "after" | "child" | "root-end";

function removePageFromTree(
  pages: GuidePage[],
  id: string
): { pages: GuidePage[]; removed: GuidePage | null } {
  let removed: GuidePage | null = null;
  const out: GuidePage[] = [];
  for (const p of pages) {
    if (p.id === id) {
      removed = p;
      continue;
    }
    if (p.children && p.children.length) {
      const r = removePageFromTree(p.children, id);
      if (r.removed) removed = r.removed;
      out.push({ ...p, children: r.pages });
    } else {
      out.push(p);
    }
  }
  return { pages: out, removed };
}

function insertPageRelative(
  pages: GuidePage[],
  targetId: string,
  pos: "before" | "after" | "child",
  node: GuidePage
): GuidePage[] {
  const out: GuidePage[] = [];
  for (const p of pages) {
    if (p.id === targetId) {
      if (pos === "before") {
        out.push(node, p);
      } else if (pos === "after") {
        out.push(p, node);
      } else {
        out.push({ ...p, children: [...(p.children || []), node] });
      }
    } else if (p.children && p.children.length) {
      out.push({ ...p, children: insertPageRelative(p.children, targetId, pos, node) });
    } else {
      out.push(p);
    }
  }
  return out;
}

function subtreeDepth(node: GuidePage): number {
  if (!node.children || node.children.length === 0) return 1;
  return 1 + Math.max(...node.children.map(subtreeDepth));
}

function depthOfId(pages: GuidePage[], id: string, d = 0): number | null {
  for (const p of pages) {
    if (p.id === id) return d;
    if (p.children) {
      const r = depthOfId(p.children, id, d + 1);
      if (r !== null) return r;
    }
  }
  return null;
}

const MAX_PAGE_DEPTH = 4;

function movePageInTreeTo(
  pages: GuidePage[],
  pageId: string,
  targetId: string | null,
  pos: PageDropPos
): GuidePage[] {
  if (pageId === targetId) return pages;

  // Block dropping into own subtree
  const node = findPage(pages, pageId);
  if (!node) return pages;
  if (targetId && findPage([node], targetId)) return pages;

  // Validate depth
  const nodeDepth = subtreeDepth(node);
  if (pos === "root-end" || targetId === null) {
    if (nodeDepth > MAX_PAGE_DEPTH) return pages;
  } else {
    const targetDepth = depthOfId(pages, targetId);
    if (targetDepth === null) return pages;
    const newRootDepth =
      pos === "child" ? targetDepth + 1 : targetDepth;
    if (newRootDepth + nodeDepth > MAX_PAGE_DEPTH) return pages;
  }

  const { pages: removedTree, removed } = removePageFromTree(pages, pageId);
  if (!removed) return pages;

  if (pos === "root-end" || targetId === null) {
    return [...removedTree, removed];
  }
  return insertPageRelative(removedTree, targetId, pos, removed);
}

// ── Local cache types ────────────────────────────────────────────────────

interface GuideCache {
  pages: GuidePage[];
  currentPageId: string | null;
  accentColor?: string;
}

interface GreetingCache {
  components: ComponentDef[];
  accentColor?: string;
}

/** A board response while it is being edited (components carry _ids). */
interface BoardResponseDraft {
  id: string;
  label?: string;
  accent_color?: string | number;
  components: ComponentDef[];
}

interface BoardCache {
  /** The static board message's own components. */
  main: ComponentDef[];
  responses: BoardResponseDraft[];
  /** BOARD_MAIN_ID, or the id of the response being edited. */
  currentId: string;
  accentColor?: string;
}

/** Fold the live editor components back into whichever board target is selected. */
function foldBoard(
  main: ComponentDef[],
  responses: BoardResponseDraft[],
  currentId: string,
  components: ComponentDef[],
): { main: ComponentDef[]; responses: BoardResponseDraft[] } {
  if (currentId === BOARD_MAIN_ID) {
    return { main: [...components], responses };
  }
  return {
    main,
    responses: responses.map((r) =>
      r.id === currentId ? { ...r, components: [...components] } : r,
    ),
  };
}

/** Every response id referenced by a button or select option, at any depth. */
function collectReferencedIds(components: ComponentDef[], out: Set<string> = new Set()): Set<string> {
  for (const comp of components || []) {
    const c = comp as any;
    if (c.action === "reply" && typeof c.target === "string") out.add(c.target);
    for (const btn of c.buttons || []) {
      if (btn.action === "reply" && typeof btn.target === "string") out.add(btn.target);
    }
    if (c.select) {
      for (const opt of c.select.options || []) {
        if (opt.action === "reply" && typeof opt.target === "string") out.add(opt.target);
      }
    }
    if (c.accessory?.action === "reply" && typeof c.accessory.target === "string") {
      out.add(c.accessory.target);
    }
    if (Array.isArray(c.components)) collectReferencedIds(c.components, out);
  }
  return out;
}

// ─────────────────────────────────────────────────────────────────────────

function parseMode(raw: string | null): BuilderMode {
  if (raw === "greeting" || raw === "board") return raw;
  return "guide";
}

export default function BuilderPage() {
  const { guildId } = useParams<{ guildId: string }>();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const initialMode: BuilderMode = parseMode(searchParams.get("mode"));

  const [mode, setMode] = useState<BuilderMode>(initialMode);
  const [components, setComponents] = useState<ComponentDef[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [pages, setPages] = useState<GuidePage[]>([]);
  const [currentPageId, setCurrentPageId] = useState<string | null>(null);
  const [accentColor, setAccentColor] = useState<string | undefined>();
  const [errors, setErrors] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const { toasts, push: pushToast, dismiss: dismissToast } = useToast();
  const [boardResponses, setBoardResponses] = useState<BoardResponseDraft[]>([]);
  const [boardMain, setBoardMain] = useState<ComponentDef[]>([]);
  const [boardCurrentId, setBoardCurrentId] = useState<string>(BOARD_MAIN_ID);
  const [boardPosted, setBoardPosted] = useState<{ channel_id: string | null } | null>(null);
  const [savedSigs, setSavedSigs] = useState<{ guide: string; greeting: string; board: string }>({
    guide: "",
    greeting: "",
    board: "",
  });
  const [loading, setLoading] = useState(true);
  const [activeDragId, setActiveDragId] = useState<string | null>(null);
  const [simulating, setSimulating] = useState(false);
  const [simPageId, setSimPageId] = useState<string | null>(null);
  const [simBreadcrumbs, setSimBreadcrumbs] = useState<string[]>([]);
  const [simResponseId, setSimResponseId] = useState<string | null>(null);
  const [showDocs, setShowDocs] = useState(false);
  const [pendingNav, setPendingNav] = useState<string | null>(null);
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [panelWidth, setPanelWidth] = useState(320);
  const [canvasWidth, setCanvasWidth] = useState(520);
  const [guild, setGuild] = useState<Guild | null>(null);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);

  // Local caches - hold full working state (with _ids) so toggling never hits DB
  const guideCacheRef = useRef<GuideCache>({ pages: [], currentPageId: null });
  const greetingCacheRef = useRef<GreetingCache>({ components: [] });
  const boardCacheRef = useRef<BoardCache>({ main: [], responses: [], currentId: BOARD_MAIN_ID });
  const fileInputRef = useRef<HTMLInputElement>(null);

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));

  // ── Panel resize ──────────────────────────────────────────────────────
  const resizing = useRef(false);

  const onResizeStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    resizing.current = true;
    const startX = e.clientX;
    const startW = panelWidth;

    const onMove = (ev: MouseEvent) => {
      if (!resizing.current) return;
      const delta = startX - ev.clientX;
      setPanelWidth(Math.min(700, Math.max(280, startW + delta)));
    };
    const onUp = () => {
      resizing.current = false;
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, [panelWidth]);

  // ── Canvas preview resize ──────────────────────────────────────────────
  const canvasResizing = useRef(false);

  const onCanvasResizeStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    canvasResizing.current = true;
    const startX = e.clientX;
    const startW = canvasWidth;

    const onMove = (ev: MouseEvent) => {
      if (!canvasResizing.current) return;
      const delta = ev.clientX - startX;
      setCanvasWidth(Math.min(800, Math.max(360, startW + delta)));
    };
    const onUp = () => {
      canvasResizing.current = false;
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, [canvasWidth]);

  // ── Load data (one DB call on mount) ───────────────────────────────────

  useEffect(() => {
    if (!guildId) return;
    setLoading(true);
    Promise.all([api.getGuide(guildId), api.getGreeting(guildId), api.getBoard(guildId).catch(() => ({ board_data: null, posted: null })), api.guilds(), api.getChannels(guildId).catch(() => []), api.getRoles(guildId).catch(() => [])])
      .then(([guideRes, greetingRes, boardRes, allGuilds, channelsRes, rolesRes]) => {
        setChannels(channelsRes);
        setRoles(rolesRes);
        setGuild(allGuilds.find((g) => g.id === guildId) ?? null);
        // Hydrate guide cache
        if (guideRes.guide_data) {
          const normalizedDbPages = normalizePages(guideRes.guide_data.pages);
          const hydratedPages = normalizedDbPages.map(addIdsToPage);
          const firstId = hydratedPages.length > 0 ? hydratedPages[0].id : null;
          guideCacheRef.current = {
            pages: hydratedPages,
            currentPageId: firstId,
            accentColor: guideRes.guide_data.accent_color as string | undefined,
          };
        }

        // Hydrate greeting cache
        if (greetingRes.greeting_data) {
          greetingCacheRef.current = {
            components: addIds(greetingRes.greeting_data.components || []),
            accentColor: greetingRes.greeting_data.accent_color as string | undefined,
          };
        }

        // Hydrate board cache
        if (boardRes.board_data) {
          boardCacheRef.current = {
            main: addIds(boardRes.board_data.components || []),
            responses: (boardRes.board_data.responses || []).map((r) => ({
              ...r,
              components: addIds(r.components || []),
            })),
            currentId: BOARD_MAIN_ID,
            accentColor: boardRes.board_data.accent_color as string | undefined,
          };
        }
        setBoardPosted(boardRes.posted);

        // Hydrate the guide page-tree state so the tree is ready when toggling modes
        const gc = guideCacheRef.current;
        setPages(gc.pages);
        setCurrentPageId(gc.currentPageId);
        // Hydrate the board state so its list is ready when toggling modes
        const bc = boardCacheRef.current;
        setBoardMain(bc.main);
        setBoardResponses(bc.responses);
        setBoardCurrentId(bc.currentId);
        // Load the requested mode into the active editor
        const wc = greetingCacheRef.current;
        if (initialMode === "greeting") {
          setComponents([...wc.components]);
          setAccentColor(wc.accentColor);
        } else if (initialMode === "board") {
          setComponents([...bc.main]);
          setAccentColor(bc.accentColor);
        } else {
          setAccentColor(gc.accentColor);
          if (gc.currentPageId) {
            const firstPage = findPage(gc.pages, gc.currentPageId);
            setComponents(firstPage?.content?.components ? [...firstPage.content.components] : []);
          }
        }
        // Seed saved signatures from loaded data so initial state is "clean"
        setSavedSigs({
          guide: JSON.stringify(buildGuideData(gc.pages, gc.accentColor)),
          greeting: JSON.stringify(buildGreetingData(wc.components, wc.accentColor)),
          board: JSON.stringify(buildBoardData(bc.main, bc.responses, bc.accentColor)),
        });
      })
      .catch(() => navigate("/dashboard"))
      .finally(() => setLoading(false));
  }, [guildId, navigate, initialMode]);

  // ── Snapshot current state into the active cache ───────────────────────

  const snapshotToCache = useCallback(() => {
    if (mode === "guide") {
      let p = pages;
      if (currentPageId) {
        p = updatePageInTree(p, currentPageId, (pg) => ({
          ...pg,
          content: { components: [...components] },
        }));
      }
      guideCacheRef.current = { pages: p, currentPageId, accentColor };
    } else if (mode === "board") {
      const folded = foldBoard(boardMain, boardResponses, boardCurrentId, components);
      boardCacheRef.current = { ...folded, currentId: boardCurrentId, accentColor };
    } else {
      greetingCacheRef.current = { components: [...components], accentColor };
    }
  }, [mode, pages, currentPageId, components, accentColor, boardMain, boardResponses, boardCurrentId]);

  // ── Mode switch (cache only, no DB) ────────────────────────────────────

  const switchMode = useCallback(
    (newMode: BuilderMode) => {
      if (newMode === mode) return;

      // Save current state into cache
      snapshotToCache();

      // Load target mode from cache
      if (newMode === "guide") {
        const gc = guideCacheRef.current;
        setPages(gc.pages);
        setCurrentPageId(gc.currentPageId);
        setAccentColor(gc.accentColor);
        if (gc.currentPageId) {
          const page = findPage(gc.pages, gc.currentPageId);
          setComponents(page?.content?.components ? [...page.content.components] : []);
        } else {
          setComponents([]);
        }
      } else if (newMode === "board") {
        const bc = boardCacheRef.current;
        setBoardMain(bc.main);
        setBoardResponses(bc.responses);
        setBoardCurrentId(bc.currentId);
        setAccentColor(bc.accentColor);
        if (bc.currentId === BOARD_MAIN_ID) {
          setComponents([...bc.main]);
        } else {
          const resp = bc.responses.find((r) => r.id === bc.currentId);
          setComponents(resp ? [...resp.components] : [...bc.main]);
          if (!resp) setBoardCurrentId(BOARD_MAIN_ID);
        }
      } else {
        const wc = greetingCacheRef.current;
        setComponents([...wc.components]);
        setAccentColor(wc.accentColor);
      }

      setSelectedId(null);
      setMode(newMode);
    },
    [mode, snapshotToCache]
  );

  // ── Board response actions ─────────────────────────────────────────────

  /** Switch which board target (message or response) the canvas is editing. */
  const selectBoardTarget = useCallback(
    (id: string) => {
      if (id === boardCurrentId) return;
      const folded = foldBoard(boardMain, boardResponses, boardCurrentId, components);
      setBoardMain(folded.main);
      setBoardResponses(folded.responses);

      if (id === BOARD_MAIN_ID) {
        setComponents([...folded.main]);
      } else {
        const resp = folded.responses.find((r) => r.id === id);
        setComponents(resp ? [...resp.components] : []);
      }
      setBoardCurrentId(id);
      setSelectedId(null);
    },
    [boardCurrentId, boardMain, boardResponses, components]
  );

  const addBoardResponse = useCallback(
    (id: string, label: string) => {
      const folded = foldBoard(boardMain, boardResponses, boardCurrentId, components);
      const created: BoardResponseDraft = {
        id,
        label,
        components: [{ _id: uid(), type: "text", content: `## ${label}` } as ComponentDef],
      };
      setBoardMain(folded.main);
      setBoardResponses([...folded.responses, created]);
      setBoardCurrentId(id);
      setComponents([...created.components]);
      setSelectedId(null);
    },
    [boardMain, boardResponses, boardCurrentId, components]
  );

  const deleteBoardResponse = useCallback(
    (id: string) => {
      const folded = foldBoard(boardMain, boardResponses, boardCurrentId, components);
      const remaining = folded.responses.filter((r) => r.id !== id);
      setBoardMain(folded.main);
      setBoardResponses(remaining);
      // Deleting the response being edited drops you back to the board message.
      if (boardCurrentId === id) {
        setBoardCurrentId(BOARD_MAIN_ID);
        setComponents([...folded.main]);
        setSelectedId(null);
      }
      // Any button still pointing here now fails validation, which is the point:
      // the error names the dangling reference instead of silently breaking later.
    },
    [boardMain, boardResponses, boardCurrentId, components]
  );

  const renameBoardResponse = useCallback((id: string, label: string) => {
    setBoardResponses((prev) => prev.map((r) => (r.id === id ? { ...r, label } : r)));
  }, []);

  /** Response ids something actually links to, so the list can flag orphans. */
  const boardUsedIds = useMemo(() => {
    if (mode !== "board") return new Set<string>();
    const folded = foldBoard(boardMain, boardResponses, boardCurrentId, components);
    const used = collectReferencedIds(folded.main);
    for (const resp of folded.responses) collectReferencedIds(resp.components, used);
    return used;
  }, [mode, boardMain, boardResponses, boardCurrentId, components]);

  // ── Page tree actions ──────────────────────────────────────────────────

  const selectPage = useCallback(
    (pageId: string) => {
      // Save current page components back into pages AND load target page atomically
      setPages((prev) => {
        let updated = prev;
        if (currentPageId) {
          updated = updatePageInTree(prev, currentPageId, (p) => ({
            ...p,
            content: { components: [...components] },
          }));
        }
        // Read target page from the updated tree (not stale closure)
        const targetPage = findPage(updated, pageId);
        setComponents(targetPage?.content?.components ? [...targetPage.content.components] : []);
        setCurrentPageId(pageId);
        setSelectedId(null);
        return updated;
      });
    },
    [currentPageId, components]
  );

  const addPage = useCallback(
    (parentId: string | null, label: string, icon?: string, description?: string) => {
      const id = `page-${Date.now()}`;
      const page: GuidePage = {
        id,
        label,
        ...(icon ? { icon } : {}),
        ...(description ? { description } : {}),
        content: { components: [] },
      };
      // Save current page components, add the new page, then select it
      setPages((prev) => {
        let updated = prev;
        if (currentPageId) {
          updated = updatePageInTree(prev, currentPageId, (p) => ({
            ...p,
            content: { components: [...components] },
          }));
        }
        const withNew = addChildPage(updated, parentId, page);
        setComponents(page.content!.components ? [...page.content!.components] : []);
        setCurrentPageId(id);
        setSelectedId(null);
        return withNew;
      });
    },
    [currentPageId, components]
  );

  const deletePage = useCallback(
    (pageId: string) => {
      setPages((prev) => {
        const newPages = deletePageFromTree(prev, pageId);
        if (currentPageId === pageId) {
          if (newPages.length > 0) {
            setCurrentPageId(newPages[0].id);
            setComponents(newPages[0].content?.components ? [...newPages[0].content.components] : []);
          } else {
            setCurrentPageId(null);
            setComponents([]);
          }
        }
        return newPages;
      });
    },
    [currentPageId]
  );

  const renamePage = useCallback(
    (pageId: string, label: string) => {
      setPages((prev) => updatePageInTree(prev, pageId, (p) => ({ ...p, label })));
    },
    []
  );

  const duplicatePage = useCallback(
    (pageId: string) => {
      setPages((prev) => {
        // Snapshot active page components into tree so duplicate captures latest edits
        let working = prev;
        if (currentPageId) {
          working = updatePageInTree(prev, currentPageId, (p) => ({
            ...p,
            content: { components: [...components] },
          }));
        }
        const original = findPage(working, pageId);
        if (!original) return prev;
        const subDepth = subtreeDepth(original);
        const ownDepth = depthOfId(working, pageId) ?? 0;
        if (ownDepth + subDepth > MAX_PAGE_DEPTH) {
          pushToast(`Cannot duplicate - exceeds max depth of ${MAX_PAGE_DEPTH}`, "error");
          return prev;
        }
        const existingIds = collectAllIds(working);
        const clone = clonePageWithNewIds(original, existingIds);
        clone.label = `${original.label} (copy)`;
        return insertAfterPage(working, pageId, clone);
      });
    },
    [currentPageId, components, pushToast]
  );

  const movePage = useCallback(
    (pageId: string, dir: -1 | 1) => {
      setPages((prev) => movePageInTree(prev, pageId, dir));
    },
    []
  );

  const movePageTo = useCallback(
    (pageId: string, targetId: string | null, pos: PageDropPos) => {
      setPages((prev) => movePageInTreeTo(prev, pageId, targetId, pos));
    },
    []
  );

  const updatePageMeta = useCallback(
    (pageId: string, field: "description" | "icon", value: string) => {
      setPages((prev) =>
        updatePageInTree(prev, pageId, (p) => ({ ...p, [field]: value || undefined }))
      );
    },
    []
  );

  // ── Validation (debounced) ─────────────────────────────────────────────

  useEffect(() => {
    const timer = setTimeout(() => {
      if (mode === "guide") {
        let pagesWithCurrent = pages;
        if (currentPageId) {
          pagesWithCurrent = updatePageInTree(pages, currentPageId, (p) => ({
            ...p,
            content: { components: [...components] },
          }));
        }
        const data = buildGuideData(pagesWithCurrent, accentColor);
        const r = validateGuideSchema(data);
        setErrors(r.valid ? [] : [r.error]);
      } else if (mode === "board") {
        // Validate the whole board, not just the target on screen, so a dangling
        // reply target shows up even while editing a different response.
        const folded = foldBoard(boardMain, boardResponses, boardCurrentId, components);
        const data = buildBoardData(folded.main, folded.responses, accentColor);
        const r = validateBoardSchema(data);
        setErrors(r.valid ? [] : [r.error]);
      } else {
        const data: GreetingData = { components: stripIds(components) as any };
        if (accentColor) data.accent_color = accentColor;
        const r = validateGreetingSchema(data);
        setErrors(r.valid ? [] : [r.error]);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [components, mode, pages, currentPageId, accentColor, boardMain, boardResponses, boardCurrentId]);

  // ── DnD handlers ───────────────────────────────────────────────────────

  const onDragStart = (event: DragStartEvent) => {
    setActiveDragId(event.active.id as string);
  };

  const onDragEnd = (event: DragEndEvent) => {
    setActiveDragId(null);
    const { active, over } = event;
    if (!over) return;

    // Block drops when guide mode has no page selected
    if (mode === "guide" && !currentPageId) return;

    const activeData = active.data.current;

    if (activeData?.fromPalette) {
      const type = activeData.componentType as ComponentType;
      const comp = newComponent(type);
      const overId = over.id as string;

      if (overId === "canvas") {
        setComponents((prev) => [...prev, comp]);
      } else {
        setComponents((prev) => {
          const idx = prev.findIndex((c) => c._id === overId);
          if (idx === -1) return [...prev, comp];
          const copy = [...prev];
          copy.splice(idx, 0, comp);
          return copy;
        });
      }
      setSelectedId(comp._id);
      return;
    }

    if (active.id !== over.id) {
      setComponents((prev) => {
        const oldIndex = prev.findIndex((c) => c._id === active.id);
        const newIndex = prev.findIndex((c) => c._id === over.id);
        if (oldIndex === -1 || newIndex === -1) return prev;
        return arrayMove(prev, oldIndex, newIndex);
      });
    }
  };

  // ── Component updates ──────────────────────────────────────────────────

  const updateComponent = useCallback(
    (updated: ComponentDef) => {
      setComponents((prev) => prev.map((c) => (c._id === updated._id ? updated : c)));
    },
    []
  );

  const deleteComponent = useCallback((id: string) => {
    setComponents((prev) => prev.filter((c) => c._id !== id));
    setSelectedId((prev) => (prev === id ? null : prev));
  }, []);

  const duplicateComponent = useCallback((id: string) => {
    setComponents((prev) => {
      const idx = prev.findIndex((c) => c._id === id);
      if (idx === -1) return prev;
      const clone = addIds([prev[idx]])[0];
      const copy = [...prev];
      copy.splice(idx + 1, 0, clone);
      setSelectedId(clone._id);
      return copy;
    });
  }, []);

  const selectedComponent = useMemo(
    () => components.find((c) => c._id === selectedId) || null,
    [components, selectedId]
  );

  // ── Simulation ────────────────────────────────────────────────────────

  const latestPages = useMemo(() => {
    if (mode !== "guide") return pages;
    if (!currentPageId) return pages;
    return updatePageInTree(pages, currentPageId, (p) => ({
      ...p,
      content: { components: [...components] },
    }));
  }, [mode, pages, currentPageId, components]);

  /** Board state with the live edits folded in, for the preview. */
  const latestBoard = useMemo(() => {
    if (mode !== "board") return { main: boardMain, responses: boardResponses };
    return foldBoard(boardMain, boardResponses, boardCurrentId, components);
  }, [mode, boardMain, boardResponses, boardCurrentId, components]);

  const toggleSimulation = useCallback(() => {
    if (!simulating) {
      snapshotToCache();
      setSimPageId(null);
      setSimBreadcrumbs([]);
      setSimResponseId(null);
    }
    setSimulating((prev) => !prev);
  }, [simulating, snapshotToCache]);

  const handleSimInteraction = useCallback(
    (action: SimulationAction) => {
      switch (action.type) {
        case "navigate":
          setSimBreadcrumbs((prev) => simPageId ? [...prev, simPageId] : prev);
          setSimPageId(action.target!);
          break;
        case "back": {
          const copy = [...simBreadcrumbs];
          setSimPageId(copy.pop() ?? null);
          setSimBreadcrumbs(copy);
          break;
        }
        case "home":
          setSimPageId(null);
          setSimBreadcrumbs([]);
          break;
        case "search":
          pushToast("Search requires the bot backend", "info");
          break;
        case "greeting_action": {
          const desc = VALID_ACTIONS[action.action!]?.description || action.action;
          pushToast(`Action: ${desc}`, "info");
          break;
        }
        case "channel": {
          const ch = channels.find((c) => c.id === action.target);
          pushToast(`Would link to channel #${ch?.name || action.target}`, "info");
          break;
        }
        case "role": {
          const r = roles.find((rl) => rl.id === action.target);
          pushToast(`Would give/remove role @${r?.name || action.target}`, "info");
          break;
        }
        case "board_reply":
          // Show the response the way a member sees it: a private reply below.
          setSimResponseId(action.target ?? null);
          break;
      }
    },
    [simPageId, simBreadcrumbs, channels, roles, pushToast]
  );

  // ── Import JSON ────────────────────────────────────────────────────────

  const handleImport = useCallback(
    (e: ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      const resetInput = () => {
        if (fileInputRef.current) fileInputRef.current.value = "";
      };
      if (!file) return;

      // The <input accept=".json"> filter only narrows the OS picker - a renamed
      // or drag-and-dropped file bypasses it. Gate on the extension so non-JSON
      // uploads (.exe/.svg/.html/.gz/…) are rejected up front.
      if (!/\.json$/i.test(file.name)) {
        pushToast("Only .json files can be imported.", "error");
        resetInput();
        return;
      }

      // Reject oversized files before reading them into memory - mirrors the
      // backend byte ceilings (guide 256 KB, board 128 KB, greeting 64 KB). This
      // is the primary guard against huge/deeply-nested "bomb" payloads.
      const maxBytes =
        mode === "guide" ? MAX_GUIDE_BYTES : mode === "board" ? MAX_BOARD_BYTES : MAX_GREETING_BYTES;
      if (file.size > maxBytes) {
        pushToast(`File is too large (max ${Math.floor(maxBytes / 1024)} KB for ${mode}).`, "error");
        resetInput();
        return;
      }

      const reader = new FileReader();
      reader.onload = () => {
        try {
          const data = JSON.parse(reader.result as string);

          // Reject prototype-pollution keys, unsafe HTML/script markup, and
          // invisible/bidi control characters on the raw payload before any
          // processing. The schema validators repeat this for the save path.
          const safe = checkNoDangerousContent(data);
          if (!safe.valid) {
            pushToast(`Import rejected - ${safe.error}`, "error");
            return;
          }

          if (mode === "guide") {
            if (!data.pages || !Array.isArray(data.pages)) {
              pushToast("Invalid guide JSON - expected { pages: [...] }", "error");
              return;
            }
            // Normalize (assign ids/order) then validate BEFORE touching editor
            // state - mirrors the backend order and reuses the shared validator.
            // The validator caps nesting depth, so a deep tree is rejected safely.
            const normalized = normalizePages(data.pages as GuidePage[]);
            const candidate: GuideData = { pages: normalized };
            if (data.accent_color !== undefined) candidate.accent_color = data.accent_color;
            const r = validateGuideSchema(candidate);
            if (!r.valid) {
              pushToast(`Import rejected - ${r.error}`, "error");
              return;
            }
            const imported = normalized.map((p: GuidePage) => addIdsToPage(p));
            setPages(imported);
            if (data.accent_color) setAccentColor(data.accent_color as string);
            if (imported.length > 0) {
              setCurrentPageId(imported[0].id);
              setComponents(imported[0].content?.components ? [...imported[0].content.components] : []);
            } else {
              setCurrentPageId(null);
              setComponents([]);
            }
            setSelectedId(null);
            pushToast(`Imported ${imported.length} pages`, "success");
          } else if (mode === "board") {
            if (!data.components || !Array.isArray(data.components)) {
              pushToast("Invalid board JSON - expected { components: [...] }", "error");
              return;
            }
            const candidate: BoardData = {
              components: data.components,
              responses: data.responses,
            };
            if (data.accent_color !== undefined) candidate.accent_color = data.accent_color;
            const r = validateBoardSchema(candidate);
            if (!r.valid) {
              pushToast(`Import rejected - ${r.error}`, "error");
              return;
            }
            const importedMain = addIds(data.components);
            const importedResponses: BoardResponseDraft[] = (
              (data.responses as BoardResponse[]) || []
            ).map((resp) => ({ ...resp, components: addIds(resp.components || []) }));
            setBoardMain(importedMain);
            setBoardResponses(importedResponses);
            setBoardCurrentId(BOARD_MAIN_ID);
            setComponents(importedMain);
            if (data.accent_color) setAccentColor(data.accent_color as string);
            setSelectedId(null);
            pushToast(
              `Imported the board and ${importedResponses.length} response(s)`,
              "success",
            );
          } else {
            if (!data.components || !Array.isArray(data.components)) {
              pushToast("Invalid greeting JSON - expected { components: [...] }", "error");
              return;
            }
            const candidate: GreetingData = { components: data.components };
            if (data.accent_color !== undefined) candidate.accent_color = data.accent_color;
            const r = validateGreetingSchema(candidate);
            if (!r.valid) {
              pushToast(`Import rejected - ${r.error}`, "error");
              return;
            }
            setComponents(addIds(data.components));
            if (data.accent_color) setAccentColor(data.accent_color as string);
            setSelectedId(null);
            pushToast(`Imported ${data.components.length} components`, "success");
          }
        } catch {
          pushToast("Failed to parse JSON file", "error");
        } finally {
          resetInput();
        }
      };
      reader.readAsText(file);
    },
    [mode, pushToast]
  );

  // ── Export JSON ────────────────────────────────────────────────────────

  const handleExport = useCallback(() => {
    let data: GuideData | GreetingData | BoardData;
    if (mode === "guide") {
      // Fold the currently-edited page's live components back into the tree
      // (same as save()) so unsaved edits to the active page are included.
      let pagesWithCurrent = pages;
      if (currentPageId) {
        pagesWithCurrent = updatePageInTree(pages, currentPageId, (p) => ({
          ...p,
          content: { components: [...components] },
        }));
      }
      data = buildGuideData(pagesWithCurrent, accentColor);
    } else if (mode === "board") {
      const folded = foldBoard(boardMain, boardResponses, boardCurrentId, components);
      data = buildBoardData(folded.main, folded.responses, accentColor);
    } else {
      data = buildGreetingData(components, accentColor);
    }

    const json = JSON.stringify(data, null, 2);
    const blob = new Blob([json], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const stamp = new Date().toISOString().slice(0, 10).replace(/-/g, "");
    // Filename uses fixed values only (no guild name / labels) to avoid injection.
    const filename = `codex-${mode}-${guildId ?? "guild"}-${stamp}.json`;
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    pushToast(`Exported ${mode} JSON`, "success");
  }, [mode, pages, currentPageId, components, accentColor, guildId, pushToast, boardMain, boardResponses, boardCurrentId]);

  // ── Dirty tracking ─────────────────────────────────────────────────────

  const currentGuideSig = useMemo(() => {
    if (loading) return savedSigs.guide;
    if (mode === "guide") {
      let p = pages;
      if (currentPageId) {
        p = updatePageInTree(pages, currentPageId, (pg) => ({
          ...pg,
          content: { components: [...components] },
        }));
      }
      return JSON.stringify(buildGuideData(p, accentColor));
    }
    const gc = guideCacheRef.current;
    return JSON.stringify(buildGuideData(gc.pages, gc.accentColor));
  }, [loading, mode, pages, currentPageId, components, accentColor, savedSigs.guide]);

  const currentGreetingSig = useMemo(() => {
    if (loading) return savedSigs.greeting;
    if (mode === "greeting") {
      return JSON.stringify(buildGreetingData(components, accentColor));
    }
    const wc = greetingCacheRef.current;
    return JSON.stringify(buildGreetingData(wc.components, wc.accentColor));
  }, [loading, mode, components, accentColor, savedSigs.greeting]);

  const currentBoardSig = useMemo(() => {
    if (loading) return savedSigs.board;
    if (mode === "board") {
      const folded = foldBoard(boardMain, boardResponses, boardCurrentId, components);
      return JSON.stringify(buildBoardData(folded.main, folded.responses, accentColor));
    }
    const bc = boardCacheRef.current;
    return JSON.stringify(buildBoardData(bc.main, bc.responses, bc.accentColor));
  }, [loading, mode, components, accentColor, boardMain, boardResponses, boardCurrentId, savedSigs.board]);

  const dirty =
    !loading &&
    (currentGuideSig !== savedSigs.guide ||
      currentGreetingSig !== savedSigs.greeting ||
      currentBoardSig !== savedSigs.board);

  useEffect(() => {
    if (!dirty) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);

  const navigateAway = useCallback(
    (path: string) => {
      if (dirty) {
        setPendingNav(path);
        return;
      }
      navigate(path);
    },
    [dirty, navigate]
  );

  // ── Save (DB write + update cache) ─────────────────────────────────────

  const save = async () => {
    if (!guildId) return;
    setSaving(true);
    setSaveState("saving");
    try {
      if (mode === "guide") {
        let pagesWithCurrent = pages;
        if (currentPageId) {
          pagesWithCurrent = updatePageInTree(pages, currentPageId, (p) => ({
            ...p,
            content: { components: [...components] },
          }));
        }
        const data = buildGuideData(pagesWithCurrent, accentColor);
        const res = await api.putGuide(guildId, data);
        // Update cache with server-normalized data (auto-generated IDs etc.)
        if (res.guide_data) {
          const hydratedPages = res.guide_data.pages.map(addIdsToPage);
          guideCacheRef.current = {
            pages: hydratedPages,
            currentPageId,
            accentColor: res.guide_data.accent_color as string | undefined,
          };
          setPages(hydratedPages);
          if (currentPageId) {
            const page = findPage(hydratedPages, currentPageId);
            setComponents(page?.content?.components ? [...page.content.components] : []);
          }
        }
        setSavedSigs((prev) => ({ ...prev, guide: currentGuideSig }));
        pushToast("Guide saved!", "success");
      } else if (mode === "board") {
        const folded = foldBoard(boardMain, boardResponses, boardCurrentId, components);
        const data = buildBoardData(folded.main, folded.responses, accentColor);
        await api.putBoard(guildId, data);
        setBoardMain(folded.main);
        setBoardResponses(folded.responses);
        boardCacheRef.current = {
          main: folded.main,
          responses: folded.responses,
          currentId: boardCurrentId,
          accentColor,
        };
        setSavedSigs((prev) => ({ ...prev, board: currentBoardSig }));
        pushToast(
          boardPosted
            ? "Board saved! Update the posted message from /admin panel -> Info Board -> Post / Update Board."
            : "Board saved! Put it up from /admin panel -> Info Board -> Post / Update Board.",
          "success",
        );
      } else {
        const data = buildGreetingData(components, accentColor);
        await api.putGreeting(guildId, data);
        // Update greeting cache with current state
        greetingCacheRef.current = { components: [...components], accentColor };
        setSavedSigs((prev) => ({ ...prev, greeting: currentGreetingSig }));
        pushToast("Greeting saved!", "success");
      }
      setSaveState("saved");
      setTimeout(() => setSaveState((s) => (s === "saved" ? "idle" : s)), 1500);
    } catch (err: unknown) {
      console.error("Save failed", err);
      pushToast(formatError(err, "Save failed"), "error");
      setSaveState("error");
      setTimeout(() => setSaveState((s) => (s === "error" ? "idle" : s)), 3000);
    } finally {
      setSaving(false);
    }
  };

  // ── Keyboard shortcuts ─────────────────────────────────────────────────

  useEffect(() => {
    const isEditableTarget = (el: EventTarget | null): boolean => {
      if (!(el instanceof HTMLElement)) return false;
      const tag = el.tagName;
      return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || el.isContentEditable;
    };

    const onKey = (e: KeyboardEvent) => {
      const mod = e.ctrlKey || e.metaKey;
      // Ctrl/Cmd+S - save (always intercept)
      if (mod && (e.key === "s" || e.key === "S")) {
        e.preventDefault();
        if (!saving && errors.length === 0 && dirty) save();
        return;
      }
      // Skip remaining shortcuts when typing in form fields
      if (isEditableTarget(e.target)) return;
      if (simulating) return;

      if (mod && (e.key === "d" || e.key === "D")) {
        if (selectedId) {
          e.preventDefault();
          duplicateComponent(selectedId);
        }
        return;
      }
      if (e.key === "Delete" || e.key === "Backspace") {
        if (selectedId) {
          e.preventDefault();
          deleteComponent(selectedId);
        }
        return;
      }
      if (e.key === "Escape") {
        if (selectedId) {
          e.preventDefault();
          setSelectedId(null);
        }
      }
    };

    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [saving, errors.length, dirty, selectedId, simulating, duplicateComponent, deleteComponent]);

  // ── Render ─────────────────────────────────────────────────────────────

  if (loading) return <div className="loading">Loading builder...</div>;

  return (
    <div className="app-layout app-layout--builder">
      <header className="app-header">
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <button className="btn btn-secondary" onClick={() => navigateAway("/dashboard")} style={{ fontSize: 12 }}>
            ← Back
          </button>
          {guild && (
            <div className="builder-guild-badge">
              <div className="guild-icon" style={{ width: 28, height: 28, fontSize: 13 }}>
                {guild.icon ? (
                  <img src={`https://cdn.discordapp.com/icons/${guild.id}/${guild.icon}.png?size=64`} alt="" />
                ) : (
                  guild.name[0]
                )}
              </div>
              <span>{guild.name}</span>
            </div>
          )}
          <h1>Component Builder</h1>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div className="mode-toggle">
            <button className={mode === "guide" ? "active" : ""} onClick={() => switchMode("guide")}>
              Guide
            </button>
            <button className={mode === "greeting" ? "active" : ""} onClick={() => switchMode("greeting")}>
              Greeting
            </button>
            <button className={mode === "board" ? "active" : ""} onClick={() => switchMode("board")}>
              Board
            </button>
          </div>
          <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--dc-text-muted)" }}>
            Accent
            <input
              type="color"
              value={accentColor || "#5865f2"}
              onChange={(e) => setAccentColor(e.target.value)}
              style={{ width: 28, height: 28, border: "none", background: "none", cursor: "pointer" }}
            />
          </label>
          <input
            ref={fileInputRef}
            type="file"
            accept=".json"
            style={{ display: "none" }}
            onChange={handleImport}
          />
          <button className="btn btn-secondary" onClick={() => fileInputRef.current?.click()} style={{ fontSize: 12 }}>
            Import JSON
          </button>
          <button className="btn btn-secondary" onClick={handleExport} style={{ fontSize: 12 }}>
            Export JSON
          </button>
          {dirty && (
            <span className="dirty-badge" role="status" aria-live="polite">
              Unsaved changes
            </span>
          )}
          <button
            className={`btn btn-success save-btn save-btn--${saveState}`}
            onClick={save}
            disabled={saving || errors.length > 0 || !dirty}
            title="Save (Ctrl+S)"
          >
            {saveState === "saving"
              ? "Saving…"
              : saveState === "saved"
                ? "Saved ✓"
                : saveState === "error"
                  ? "Retry"
                  : dirty
                    ? "Save"
                    : "Saved"}
          </button>
        </div>
      </header>

      <DndContext sensors={sensors} onDragStart={onDragStart} onDragEnd={onDragEnd}>
        <div
          className={`builder-layout${simulating ? " simulating" : ""}`}
          style={{ "--panel-width": `${panelWidth}px` } as React.CSSProperties}
        >
          {/* Left sidebar */}
          {!simulating && (
            <div className="builder-sidebar">
              <ComponentPalette />
              {mode === "guide" && (
                <PageTreeEditor
                  pages={pages}
                  currentPageId={currentPageId}
                  storageKey={guildId ? `pageTree:collapsed:${guildId}` : undefined}
                  onSelectPage={selectPage}
                  onAddPage={addPage}
                  onDeletePage={deletePage}
                  onDuplicatePage={duplicatePage}
                  onRenamePage={renamePage}
                  onMovePage={movePage}
                  onMovePageTo={movePageTo}
                  onUpdatePageMeta={updatePageMeta}
                />
              )}
              {mode === "board" && (
                <ResponseListEditor
                  responses={boardResponses}
                  currentId={boardCurrentId}
                  usedIds={boardUsedIds}
                  onSelect={selectBoardTarget}
                  onAdd={addBoardResponse}
                  onDelete={deleteBoardResponse}
                  onRename={renameBoardResponse}
                />
              )}
            </div>
          )}

          {/* Center canvas */}
          <div className="builder-canvas-area">
            <div className="builder-toolbar">
              <span style={{ fontSize: 13, color: "var(--dc-text-muted)" }}>
                {simulating
                  ? <>Preview Mode {<span className="sim-badge">LIVE</span>}</>
                  : mode === "guide"
                    ? `Page: ${findPage(pages, currentPageId || "")?.label || "None"}`
                    : mode === "board"
                      ? boardCurrentId === BOARD_MAIN_ID
                        ? "Board message"
                        : `Response: ${boardResponses.find((r) => r.id === boardCurrentId)?.label || boardCurrentId}`
                      : "Greeting Message"}
              </span>
              {!simulating && mode === "board" && (
                <span style={{ fontSize: 12, color: "var(--dc-text-muted)" }}>
                  {boardPosted
                    ? "Posted - update it in Info Board -> Post / Update Board"
                    : "Not posted - post it from Info Board -> Post / Update Board"}
                </span>
              )}
              <button
                className={`btn ${simulating ? "btn-secondary" : "btn-primary"}`}
                onClick={toggleSimulation}
                style={{ fontSize: 12, marginLeft: "auto" }}
              >
                {simulating ? "✏️ Edit" : "▶ Preview"}
              </button>
              {!simulating && (
                <button
                  className={`btn ${showDocs ? "btn-primary" : "btn-secondary"}`}
                  onClick={() => setShowDocs((v) => !v)}
                  style={{ fontSize: 12 }}
                >
                  Docs
                </button>
              )}
              {!simulating && (
                <span style={{ fontSize: 12, color: "var(--dc-text-muted)" }}>
                  {components.length}/10 components
                </span>
              )}
            </div>
            <div
              className="builder-canvas"
              style={{ "--canvas-preview-width": `${canvasWidth}px` } as React.CSSProperties}
            >
              <div className="canvas-preview-container">
                {simulating ? (
                  <SimulationCanvas
                    mode={mode}
                    pages={latestPages}
                    simulationPageId={simPageId}
                    accentColor={accentColor || "#5865f2"}
                    components={components}
                    onInteract={handleSimInteraction}
                    boardMain={latestBoard.main}
                    boardResponses={latestBoard.responses}
                    openResponseId={simResponseId}
                    onCloseResponse={() => setSimResponseId(null)}
                  />
                ) : (
                  <Canvas
                    components={components}
                    selectedId={selectedId}
                    onSelect={setSelectedId}
                    onDelete={deleteComponent}
                    emptyMessage={mode === "guide" && pages.length === 0 ? "Create a page first using the left sidebar" : undefined}
                  />
                )}
                <div className="canvas-resize-handle" onMouseDown={onCanvasResizeStart} />
              </div>
            </div>
          </div>

          {/* Resize handle */}
          <div className="builder-resize-handle" onMouseDown={onResizeStart} />

          {/* Right panel */}
          <div className="builder-panel">
            {simulating ? (
              <div style={{ padding: 16, color: "var(--dc-text-muted)", fontSize: 13, lineHeight: 1.5 }}>
                <h3 style={{ fontSize: 12, textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.02em", marginBottom: 8, color: "var(--dc-text-muted)" }}>
                  Preview Mode
                </h3>
                <p>Interact with the preview to test navigation. Click buttons and select options to simulate the Discord experience.</p>
                <p style={{ marginTop: 8 }}>Click <strong>Edit</strong> to return to the builder.</p>
              </div>
            ) : showDocs ? (
              <DocsPanel mode={mode} />
            ) : (
              <>
                <PropertyPanel
                  component={selectedComponent}
                  mode={mode}
                  pages={pages}
                  channels={channels}
                  roles={roles}
                  boardResponses={boardResponses}
                  onChange={updateComponent}
                />
                <ValidationErrors errors={errors} />
              </>
            )}
          </div>
        </div>

        <DragOverlay>
          {activeDragId && activeDragId.startsWith("palette-") ? (
            <div className="palette-item" style={{ opacity: 0.8 }}>
              {activeDragId.replace("palette-", "")}
            </div>
          ) : null}
        </DragOverlay>
      </DndContext>

      <ToastStack toasts={toasts} onDismiss={dismissToast} />

      <ConfirmDialog
        open={pendingNav !== null}
        title="Unsaved changes"
        message="You have unsaved changes. Leave this page anyway?"
        confirmLabel="Leave"
        cancelLabel="Stay"
        destructive
        onConfirm={() => {
          const path = pendingNav;
          setPendingNav(null);
          if (path) navigate(path);
        }}
        onCancel={() => setPendingNav(null)}
      />
    </div>
  );
}

// ── Helpers ──────────────────────────────────────────────────────────────

function buildGuideData(pages: GuidePage[], accentColor?: string): GuideData {
  function cleanPage(page: GuidePage): any {
    const { content, children, ...rest } = page;
    const result: any = { ...rest };
    if (content?.components) {
      result.content = { components: stripIds(content.components) };
    }
    if (children && children.length > 0) {
      result.children = children.map(cleanPage);
    }
    return result;
  }
  const result: GuideData = { pages: pages.map(cleanPage) };
  if (accentColor) result.accent_color = accentColor;
  return result;
}

function buildBoardData(
  main: ComponentDef[],
  responses: BoardResponseDraft[],
  accentColor?: string,
): BoardData {
  const data: BoardData = { components: stripIds(main) as any };
  if (accentColor) data.accent_color = accentColor;
  if (responses.length > 0) {
    data.responses = responses.map((r) => {
      const out: BoardResponse = { id: r.id, components: stripIds(r.components) as any };
      if (r.label) out.label = r.label;
      if (r.accent_color !== undefined) out.accent_color = r.accent_color;
      return out;
    });
  }
  return data;
}

function buildGreetingData(components: ComponentDef[], accentColor?: string): GreetingData {
  const data: GreetingData = { components: stripIds(components) as any };
  if (accentColor) data.accent_color = accentColor;
  return data;
}

function stripIds(components: ComponentDef[]): any[] {
  return components.map((c) => {
    const { _id, ...rest } = c;
    if ("components" in rest && Array.isArray((rest as any).components)) {
      (rest as any).components = stripIds((rest as any).components);
    }
    return rest;
  });
}

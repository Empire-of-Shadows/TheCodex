import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
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
  WelcomeData,
} from "../api/types";
import { VALID_ACTIONS } from "../api/types";
import { validateGuideSchema } from "../validators/guideValidator";
import { validateWelcomeSchema } from "../validators/welcomeValidator";
import ComponentPalette from "../components/builder/ComponentPalette";
import PageTreeEditor from "../components/builder/PageTreeEditor";
import Canvas from "../components/builder/Canvas";
import SimulationCanvas from "../components/builder/SimulationCanvas";
import PropertyPanel from "../components/builder/PropertyPanel";
import ValidationErrors from "../components/builder/ValidationErrors";
import DocsPanel from "../components/builder/DocsPanel";

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

interface WelcomeCache {
  components: ComponentDef[];
  accentColor?: string;
}

// ─────────────────────────────────────────────────────────────────────────

export default function BuilderPage() {
  const { guildId } = useParams<{ guildId: string }>();
  const navigate = useNavigate();

  const [mode, setMode] = useState<BuilderMode>("guide");
  const [components, setComponents] = useState<ComponentDef[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [pages, setPages] = useState<GuidePage[]>([]);
  const [currentPageId, setCurrentPageId] = useState<string | null>(null);
  const [accentColor, setAccentColor] = useState<string | undefined>();
  const [errors, setErrors] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<{ msg: string; type: "success" | "error" | "info" } | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeDragId, setActiveDragId] = useState<string | null>(null);
  const [simulating, setSimulating] = useState(false);
  const [simPageId, setSimPageId] = useState<string | null>(null);
  const [simBreadcrumbs, setSimBreadcrumbs] = useState<string[]>([]);
  const [showDocs, setShowDocs] = useState(false);
  const [panelWidth, setPanelWidth] = useState(320);
  const [canvasWidth, setCanvasWidth] = useState(520);
  const [guild, setGuild] = useState<Guild | null>(null);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);

  // Local caches — hold full working state (with _ids) so toggling never hits DB
  const guideCacheRef = useRef<GuideCache>({ pages: [], currentPageId: null });
  const welcomeCacheRef = useRef<WelcomeCache>({ components: [] });
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
    Promise.all([api.getGuide(guildId), api.getWelcome(guildId), api.guilds(), api.getChannels(guildId).catch(() => []), api.getRoles(guildId).catch(() => [])])
      .then(([guideRes, welcomeRes, allGuilds, channelsRes, rolesRes]) => {
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

        // Hydrate welcome cache
        if (welcomeRes.welcome_data) {
          welcomeCacheRef.current = {
            components: addIds(welcomeRes.welcome_data.components || []),
            accentColor: welcomeRes.welcome_data.accent_color as string | undefined,
          };
        }

        // Load guide mode into active state (default mode)
        const gc = guideCacheRef.current;
        setPages(gc.pages);
        setCurrentPageId(gc.currentPageId);
        setAccentColor(gc.accentColor);
        if (gc.currentPageId) {
          const firstPage = findPage(gc.pages, gc.currentPageId);
          setComponents(firstPage?.content?.components ? [...firstPage.content.components] : []);
        }
      })
      .catch(() => navigate("/dashboard"))
      .finally(() => setLoading(false));
  }, [guildId, navigate]);

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
    } else {
      welcomeCacheRef.current = { components: [...components], accentColor };
    }
  }, [mode, pages, currentPageId, components, accentColor]);

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
      } else {
        const wc = welcomeCacheRef.current;
        setComponents([...wc.components]);
        setAccentColor(wc.accentColor);
      }

      setSelectedId(null);
      setMode(newMode);
    },
    [mode, snapshotToCache]
  );

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
      } else {
        const data: WelcomeData = { components: stripIds(components) as any };
        if (accentColor) data.accent_color = accentColor;
        const r = validateWelcomeSchema(data);
        setErrors(r.valid ? [] : [r.error]);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [components, mode, pages, currentPageId, accentColor]);

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

  const toggleSimulation = useCallback(() => {
    if (!simulating) {
      snapshotToCache();
      setSimPageId(null);
      setSimBreadcrumbs([]);
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
          setToast({ msg: "Search requires the bot backend", type: "info" as any });
          setTimeout(() => setToast(null), 3000);
          break;
        case "welcome_action": {
          const desc = VALID_ACTIONS[action.action!]?.description || action.action;
          setToast({ msg: `Action: ${desc}`, type: "info" as any });
          setTimeout(() => setToast(null), 3000);
          break;
        }
        case "channel": {
          const ch = channels.find((c) => c.id === action.target);
          setToast({ msg: `Would link to channel #${ch?.name || action.target}`, type: "info" as any });
          setTimeout(() => setToast(null), 3000);
          break;
        }
        case "role": {
          const r = roles.find((rl) => rl.id === action.target);
          setToast({ msg: `Would give/remove role @${r?.name || action.target}`, type: "info" as any });
          setTimeout(() => setToast(null), 3000);
          break;
        }
      }
    },
    [simPageId, simBreadcrumbs, channels, roles]
  );

  // ── Import JSON ────────────────────────────────────────────────────────

  const handleImport = useCallback(
    (e: ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = () => {
        try {
          const data = JSON.parse(reader.result as string);

          if (mode === "guide") {
            if (data.pages && Array.isArray(data.pages)) {
              const normalized = normalizePages(data.pages as GuidePage[]);
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
              setToast({ msg: `Imported ${imported.length} pages`, type: "success" });
            } else {
              setToast({ msg: "Invalid guide JSON — expected { pages: [...] }", type: "error" });
            }
          } else {
            if (data.components && Array.isArray(data.components)) {
              setComponents(addIds(data.components));
              if (data.accent_color) setAccentColor(data.accent_color as string);
              setSelectedId(null);
              setToast({ msg: `Imported ${data.components.length} components`, type: "success" });
            } else {
              setToast({ msg: "Invalid welcome JSON — expected { components: [...] }", type: "error" });
            }
          }
        } catch {
          setToast({ msg: "Failed to parse JSON file", type: "error" });
        }
        if (fileInputRef.current) fileInputRef.current.value = "";
        setTimeout(() => setToast(null), 3000);
      };
      reader.readAsText(file);
    },
    [mode]
  );

  // ── Save (DB write + update cache) ─────────────────────────────────────

  const save = async () => {
    if (!guildId) return;
    setSaving(true);
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
        setToast({ msg: "Guide saved!", type: "success" });
      } else {
        const data: WelcomeData = { components: stripIds(components) as any };
        if (accentColor) data.accent_color = accentColor;
        await api.putWelcome(guildId, data);
        // Update welcome cache with current state
        welcomeCacheRef.current = { components: [...components], accentColor };
        setToast({ msg: "Welcome saved!", type: "success" });
      }
    } catch (err: any) {
      setToast({ msg: err.message || "Save failed", type: "error" });
    } finally {
      setSaving(false);
      setTimeout(() => setToast(null), 3000);
    }
  };

  // ── Render ─────────────────────────────────────────────────────────────

  if (loading) return <div className="loading">Loading builder...</div>;

  return (
    <div className="app-layout app-layout--builder">
      <header className="app-header">
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <button className="btn btn-secondary" onClick={() => navigate("/dashboard")} style={{ fontSize: 12 }}>
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
            <button className={mode === "welcome" ? "active" : ""} onClick={() => switchMode("welcome")}>
              Welcome
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
          <button className="btn btn-success" onClick={save} disabled={saving || errors.length > 0}>
            {saving ? "Saving..." : "Save"}
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
                  onSelectPage={selectPage}
                  onAddPage={addPage}
                  onDeletePage={deletePage}
                  onRenamePage={renamePage}
                  onMovePage={movePage}
                  onMovePageTo={movePageTo}
                  onUpdatePageMeta={updatePageMeta}
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
                    : "Welcome Message"}
              </span>
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

      {toast && <div className={`toast ${toast.type}`}>{toast.msg}</div>}
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

function stripIds(components: ComponentDef[]): any[] {
  return components.map((c) => {
    const { _id, ...rest } = c;
    if ("components" in rest && Array.isArray((rest as any).components)) {
      (rest as any).components = stripIds((rest as any).components);
    }
    return rest;
  });
}

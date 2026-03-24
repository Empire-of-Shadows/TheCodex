import type {
  BuilderMode,
  ComponentDef,
  GuidePage,
  SimulationAction,
} from "../../api/types";
import DiscordPreview from "../preview/DiscordPreview";
import SelectPreview from "../preview/SelectPreview";
import MessageChrome from "../preview/MessageChrome";
import { GuideRootMenu, GuideBreadcrumb, GuideNavRow } from "../preview/GuideChrome";

interface Props {
  mode: BuilderMode;
  pages: GuidePage[];
  simulationPageId: string | null;
  accentColor: string;
  components: ComponentDef[];
  onInteract: (action: SimulationAction) => void;
}

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

function getBreadcrumbLabels(pages: GuidePage[], targetId: string): string[] {
  function walk(list: GuidePage[], path: string[]): string[] | null {
    for (const p of list) {
      if (p.id === targetId) return [...path, p.label];
      if (p.children) {
        const found = walk(p.children, [...path, p.label]);
        if (found) return found;
      }
    }
    return null;
  }
  return walk(pages, ["Guide"]) || ["Guide"];
}

export default function SimulationCanvas({
  mode,
  pages,
  simulationPageId,
  accentColor,
  components,
  onInteract,
}: Props) {
  if (mode === "guide") {
    return (
      <MessageChrome>
        <div className="discord-preview">
          <div className="canvas-drop-zone">
            {simulationPageId === null ? (
              <GuideRootMenu pages={pages} accentColor={accentColor} onInteract={onInteract} />
            ) : (
              <GuidePageView
                pages={pages}
                pageId={simulationPageId}
                accentColor={accentColor}
                onInteract={onInteract}
              />
            )}
          </div>
        </div>
      </MessageChrome>
    );
  }

  // Welcome mode
  return (
    <MessageChrome>
      <div className="discord-preview">
        <div className="canvas-drop-zone">
          {components.length === 0 ? (
            <div className="canvas-empty">No components to preview</div>
          ) : (
            components.map((comp, i) => (
              <DiscordPreview key={comp._id || i} component={comp} onInteract={onInteract} />
            ))
          )}
        </div>
      </div>
    </MessageChrome>
  );
}

// ── Guide page sub-view ─────────────────────────────────────────────────

function GuidePageView({
  pages,
  pageId,
  accentColor,
  onInteract,
}: {
  pages: GuidePage[];
  pageId: string;
  accentColor: string;
  onInteract: (action: SimulationAction) => void;
}) {
  const page = findPage(pages, pageId);
  if (!page) {
    return <div className="canvas-empty">Page not found</div>;
  }

  const breadcrumbs = getBreadcrumbLabels(pages, pageId);
  const pageComponents = page.content?.components || [];
  const children = page.children || [];

  // Build children select if page has sub-pages
  const childrenSelect = children.length > 0 ? {
    placeholder: "Select a topic...",
    options: children.map((c) => ({
      label: c.label,
      description: c.description,
      emoji: c.icon,
      action: "navigate" as const,
      target: c.id,
    })),
  } : null;

  return (
    <>
      {/* Page content */}
      {pageComponents.map((comp, i) => (
        <DiscordPreview key={i} component={comp} onInteract={onInteract} />
      ))}

      {/* Children dropdown */}
      {childrenSelect && (
        <SelectPreview select={childrenSelect} onInteract={onInteract} />
      )}

      {/* Breadcrumb + Nav row */}
      <GuideBreadcrumb labels={breadcrumbs} />
      <GuideNavRow isRoot={false} onInteract={onInteract} />
    </>
  );
}

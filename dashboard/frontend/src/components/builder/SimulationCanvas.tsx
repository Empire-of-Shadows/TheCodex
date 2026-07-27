import type {
  BoardResponse,
  BuilderMode,
  ComponentDef,
  GuidePage,
  SimulationAction,
} from "../../api/types";
import DiscordPreview from "../preview/DiscordPreview";
import SelectPreview from "../preview/SelectPreview";
import MessageChrome from "../preview/MessageChrome";
import { GuideBreadcrumb, GuideNavRow } from "../preview/GuideChrome";

interface Props {
  mode: BuilderMode;
  pages: GuidePage[];
  simulationPageId: string | null;
  accentColor: string;
  components: ComponentDef[];
  onInteract: (action: SimulationAction) => void;
  /** Board mode: the whole board message, regardless of which target is being edited. */
  boardMain?: ComponentDef[];
  boardResponses?: BoardResponse[];
  /** Board mode: the response currently "opened" by a click, if any. */
  openResponseId?: string | null;
  onCloseResponse?: () => void;
}

// The Home page is the top page of the tree (lowest `order`). A bare mention,
// the Home button, and unmatched searches all land here - mirrors the bot.
function homePageId(pages: GuidePage[]): string | null {
  if (pages.length === 0) return null;
  return [...pages].sort((a, b) => (a.order ?? 999) - (b.order ?? 999))[0].id;
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
  boardMain = [],
  boardResponses = [],
  openResponseId = null,
  onCloseResponse,
}: Props) {
  if (mode === "guide") {
    // A null simulation page means "Home" - resolve it to the top page.
    const activePageId = simulationPageId ?? homePageId(pages);
    return (
      <MessageChrome>
        <div className="discord-preview">
          <div className="canvas-drop-zone">
            {activePageId === null ? (
              <div className="canvas-empty">This guide doesn't have any pages yet.</div>
            ) : (
              <GuidePageView
                pages={pages}
                pageId={activePageId}
                accentColor={accentColor}
                onInteract={onInteract}
              />
            )}
          </div>
        </div>
      </MessageChrome>
    );
  }

  if (mode === "board") {
    // Always preview the board message itself, even while a response is being
    // edited - that is what members actually see in the channel.
    const openResponse = openResponseId
      ? boardResponses.find((r) => r.id === openResponseId)
      : null;

    return (
      <>
        <MessageChrome>
          <div className="discord-preview">
            <div className="canvas-drop-zone">
              {boardMain.length === 0 ? (
                <div className="canvas-empty">The board message has no components yet</div>
              ) : (
                boardMain.map((comp, i) => (
                  <DiscordPreview key={comp._id || i} component={comp} onInteract={onInteract} />
                ))
              )}
            </div>
          </div>
        </MessageChrome>

        {openResponseId && (
          <div style={{ marginTop: 12 }}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                fontSize: 11,
                color: "var(--dc-text-muted)",
                marginBottom: 4,
              }}
            >
              <span>Only you can see this</span>
              <button
                className="btn btn-secondary"
                style={{ fontSize: 10, padding: "1px 6px" }}
                onClick={onCloseResponse}
              >
                Dismiss
              </button>
            </div>
            <MessageChrome>
              <div className="discord-preview">
                <div className="canvas-drop-zone">
                  {!openResponse ? (
                    <div className="canvas-empty">
                      No response named "{openResponseId}" - the button points at nothing.
                    </div>
                  ) : openResponse.components.length === 0 ? (
                    <div className="canvas-empty">This response is empty</div>
                  ) : (
                    openResponse.components.map((comp, i) => (
                      <DiscordPreview
                        key={comp._id || i}
                        component={comp}
                        onInteract={onInteract}
                      />
                    ))
                  )}
                </div>
              </div>
            </MessageChrome>
          </div>
        )}
      </>
    );
  }

  // Greeting mode
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
  const isHome = pageId === homePageId(pages);

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

  // On the Home page, auto-list the other top-level sections (matches the bot).
  // The Home page itself is excluded, identified by id (its label may vary).
  const otherSections = isHome
    ? [...pages].filter((p) => p.id !== pageId).sort((a, b) => (a.order ?? 999) - (b.order ?? 999))
    : [];
  const sectionsSelect = otherSections.length > 0 ? {
    placeholder: "Jump to a section...",
    options: otherSections.map((p) => ({
      label: p.label,
      description: p.description,
      emoji: p.icon,
      action: "navigate" as const,
      target: p.id,
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

      {/* Top-level sections (Home page only) */}
      {sectionsSelect && (
        <SelectPreview select={sectionsSelect} onInteract={onInteract} />
      )}

      {/* Breadcrumb + Nav row. The Home page (top of the tree) is the root -
          it hides the Back/Home buttons, matching the bot. */}
      <GuideBreadcrumb labels={breadcrumbs} />
      <GuideNavRow isRoot={isHome} onInteract={onInteract} />
    </>
  );
}

import type { GuidePage, SimulationAction } from "../../api/types";
import SelectPreview from "./SelectPreview";
import ButtonPreview from "./ButtonPreview";

// ── Root menu (shown when no page is selected) ──────────────────────────

interface RootMenuProps {
  pages: GuidePage[];
  accentColor: string;
  onInteract: (action: SimulationAction) => void;
}

export function GuideRootMenu({ pages, accentColor, onInteract }: RootMenuProps) {
  const selectDef = {
    placeholder: "Select a topic...",
    options: pages.map((p) => ({
      label: p.label,
      description: p.description,
      emoji: p.icon,
      action: "navigate" as const,
      target: p.id,
    })),
  };

  return (
    <>
      {/* Header container */}
      <div className="dc-container">
        <div className="dc-container-bar" style={{ background: accentColor }} />
        <div className="dc-container-body">
          <div className="dc-text">
            <h2>📖 Server Guide</h2>
          </div>
          <div className="dc-text">Select a topic below to get started.</div>
        </div>
      </div>

      {/* Page select */}
      <SelectPreview select={selectDef} onInteract={onInteract} />

      {/* Nav row with search only */}
      <div className="dc-action-row">
        <ButtonPreview
          button={{ type: "button", style: "primary", label: "Search", emoji: "🔍", action: "search" }}
          onInteract={onInteract}
        />
      </div>
    </>
  );
}

// ── Breadcrumb trail ────────────────────────────────────────────────────

interface BreadcrumbProps {
  labels: string[];
}

export function GuideBreadcrumb({ labels }: BreadcrumbProps) {
  return (
    <div className="dc-breadcrumb">
      {labels.join(" › ")}
    </div>
  );
}

// ── Navigation row (Back / Home / Search) ───────────────────────────────

interface NavRowProps {
  isRoot: boolean;
  onInteract: (action: SimulationAction) => void;
}

export function GuideNavRow({ isRoot, onInteract }: NavRowProps) {
  return (
    <div className="dc-action-row">
      {!isRoot && (
        <>
          <ButtonPreview
            button={{ type: "button", style: "secondary", label: "Back", emoji: "◀", action: "back" }}
            onInteract={onInteract}
          />
          <ButtonPreview
            button={{ type: "button", style: "secondary", label: "Main Menu", emoji: "🏠", action: "home" }}
            onInteract={onInteract}
          />
        </>
      )}
      <ButtonPreview
        button={{ type: "button", style: "primary", label: "Search", emoji: "🔍", action: "search" }}
        onInteract={onInteract}
      />
    </div>
  );
}

import type { SimulationAction } from "../../api/types";
import ButtonPreview from "./ButtonPreview";

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
            button={{ type: "button", style: "secondary", label: "Home", emoji: "🏠", action: "home" }}
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

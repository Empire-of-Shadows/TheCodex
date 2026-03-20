import type { ContainerComponent, SimulationAction } from "../../api/types";
import DiscordPreview from "./DiscordPreview";

interface Props {
  comp: ContainerComponent;
  onInteract?: (action: SimulationAction) => void;
}

export default function ContainerPreview({ comp, onInteract }: Props) {
  let barColor = "#4e5058";
  if (comp.accent_color) {
    barColor = typeof comp.accent_color === "string"
      ? comp.accent_color
      : `#${comp.accent_color.toString(16).padStart(6, "0")}`;
  }
  return (
    <div className="dc-container">
      <div className="dc-container-bar" style={{ background: barColor }} />
      <div className="dc-container-body">
        {(comp.components || []).map((child, i) => (
          <DiscordPreview key={i} component={child} onInteract={onInteract} />
        ))}
      </div>
    </div>
  );
}

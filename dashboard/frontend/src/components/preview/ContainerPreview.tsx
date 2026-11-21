import { useContext } from "react";
import type { ContainerComponent, SimulationAction } from "../../api/types";
import DiscordPreview from "./DiscordPreview";
import { InheritedAccentContext } from "./accentContext";

interface Props {
  comp: ContainerComponent;
  onInteract?: (action: SimulationAction) => void;
}

export default function ContainerPreview({ comp, onInteract }: Props) {
  const inherited = useContext(InheritedAccentContext);
  const accent = comp.accent_color ?? inherited;
  let barColor = "#4e5058";
  if (accent !== undefined && accent !== null) {
    barColor = typeof accent === "string"
      ? accent
      : `#${accent.toString(16).padStart(6, "0")}`;
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

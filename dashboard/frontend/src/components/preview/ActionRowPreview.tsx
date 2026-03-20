import type { ActionRowComponent, SimulationAction } from "../../api/types";
import ButtonPreview from "./ButtonPreview";
import SelectPreview from "./SelectPreview";

interface Props {
  comp: ActionRowComponent;
  onInteract?: (action: SimulationAction) => void;
}

export default function ActionRowPreview({ comp, onInteract }: Props) {
  if (comp.select) {
    return <SelectPreview select={comp.select} onInteract={onInteract} />;
  }
  return (
    <div className="dc-action-row">
      {(comp.buttons || []).map((btn, i) => (
        <ButtonPreview key={i} button={btn} onInteract={onInteract} />
      ))}
    </div>
  );
}

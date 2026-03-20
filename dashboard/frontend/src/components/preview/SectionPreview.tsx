import type { SectionComponent, SimulationAction } from "../../api/types";
import TextPreview from "./TextPreview";
import ButtonPreview from "./ButtonPreview";

interface Props {
  comp: SectionComponent;
  onInteract?: (action: SimulationAction) => void;
}

export default function SectionPreview({ comp, onInteract }: Props) {
  return (
    <div className="dc-section">
      <div className="dc-section-content">
        {(comp.content || []).map((text, i) => (
          <TextPreview key={i} content={text.content} />
        ))}
      </div>
      <div className="dc-section-accessory">
        {comp.accessory?.type === "thumbnail" ? (
          <div className="dc-thumbnail">Avatar</div>
        ) : comp.accessory?.type === "button" ? (
          <ButtonPreview button={comp.accessory} onInteract={onInteract} />
        ) : null}
      </div>
    </div>
  );
}

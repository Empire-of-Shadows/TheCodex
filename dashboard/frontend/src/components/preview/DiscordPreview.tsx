import type { ComponentDef, SimulationAction } from "../../api/types";
import TextPreview from "./TextPreview";
import SeparatorPreview from "./SeparatorPreview";
import SectionPreview from "./SectionPreview";
import ActionRowPreview from "./ActionRowPreview";
import ContainerPreview from "./ContainerPreview";
import MediaGalleryPreview from "./MediaGalleryPreview";

interface Props {
  component: ComponentDef;
  onInteract?: (action: SimulationAction) => void;
}

export default function DiscordPreview({ component, onInteract }: Props) {
  switch (component.type) {
    case "text":
      return <TextPreview content={(component as any).content || ""} />;
    case "separator":
      return <SeparatorPreview />;
    case "section":
      return <SectionPreview comp={component as any} onInteract={onInteract} />;
    case "action_row":
      return <ActionRowPreview comp={component as any} onInteract={onInteract} />;
    case "container":
      return <ContainerPreview comp={component as any} onInteract={onInteract} />;
    case "media_gallery":
      return <MediaGalleryPreview comp={component as any} />;
    default:
      return <div style={{ color: "var(--dc-text-muted)", fontSize: 12 }}>Unknown: {component.type}</div>;
  }
}

import { useDraggable } from "@dnd-kit/core";
import type { ComponentType } from "../../api/types";

interface PaletteItemDef {
  type: ComponentType;
  label: string;
  icon: string;
}

const ITEMS: PaletteItemDef[] = [
  { type: "text", label: "Text", icon: "T" },
  { type: "separator", label: "Separator", icon: "―" },
  { type: "section", label: "Section", icon: "☰" },
  { type: "action_row", label: "Action Row", icon: "▣" },
  { type: "container", label: "Container", icon: "☐" },
  { type: "media_gallery", label: "Media Gallery", icon: "🖼" },
];

function DraggablePaletteItem({ item }: { item: PaletteItemDef }) {
  const { attributes, listeners, setNodeRef, isDragging } = useDraggable({
    id: `palette-${item.type}`,
    data: { fromPalette: true, componentType: item.type },
  });

  return (
    <div
      ref={setNodeRef}
      className="palette-item"
      style={{ opacity: isDragging ? 0.5 : 1 }}
      {...listeners}
      {...attributes}
    >
      <span className="icon">{item.icon}</span>
      {item.label}
    </div>
  );
}

export default function ComponentPalette() {
  return (
    <div className="palette-section">
      <h3>Components</h3>
      {ITEMS.map((item) => (
        <DraggablePaletteItem key={item.type} item={item} />
      ))}
    </div>
  );
}

import { useDroppable } from "@dnd-kit/core";
import { SortableContext, verticalListSortingStrategy } from "@dnd-kit/sortable";
import type { ComponentDef } from "../../api/types";
import ComponentWrapper from "./ComponentWrapper";

interface Props {
  components: ComponentDef[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onDelete: (id: string) => void;
  emptyMessage?: string;
}

export default function Canvas({ components, selectedId, onSelect, onDelete, emptyMessage }: Props) {
  const { setNodeRef } = useDroppable({ id: "canvas" });

  return (
    <div className="discord-preview" onClick={() => onSelect(null)}>
      <div ref={setNodeRef} className="canvas-drop-zone">
        {components.length === 0 ? (
          <div className="canvas-empty">{emptyMessage || "Drop components here"}</div>
        ) : (
          <SortableContext items={components.map((c) => c._id)} strategy={verticalListSortingStrategy}>
            {components.map((comp) => (
              <ComponentWrapper
                key={comp._id}
                component={comp}
                isSelected={selectedId === comp._id}
                onSelect={() => onSelect(comp._id)}
                onDelete={() => onDelete(comp._id)}
              />
            ))}
          </SortableContext>
        )}
      </div>
    </div>
  );
}

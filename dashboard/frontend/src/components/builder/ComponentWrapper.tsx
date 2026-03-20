import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import type { ComponentDef } from "../../api/types";
import DiscordPreview from "../preview/DiscordPreview";

interface Props {
  component: ComponentDef;
  isSelected: boolean;
  onSelect: () => void;
  onDelete: () => void;
}

export default function ComponentWrapper({ component, isSelected, onSelect, onDelete }: Props) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: component._id,
  });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.4 : 1,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`component-wrapper ${isSelected ? "selected" : ""}`}
      onClick={(e) => {
        e.stopPropagation();
        onSelect();
      }}
    >
      <span className="drag-handle" {...attributes} {...listeners}>
        ⠿
      </span>
      <button
        className="delete-btn"
        onClick={(e) => {
          e.stopPropagation();
          onDelete();
        }}
      >
        ×
      </button>
      <DiscordPreview component={component} />
    </div>
  );
}

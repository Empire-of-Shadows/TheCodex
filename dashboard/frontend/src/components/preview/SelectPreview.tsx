import { useState } from "react";
import type { SelectDef, SimulationAction } from "../../api/types";

interface Props {
  select: SelectDef;
  onInteract?: (action: SimulationAction) => void;
}

export default function SelectPreview({ select, onInteract }: Props) {
  const [isOpen, setIsOpen] = useState(false);
  const interactive = !!onInteract;

  const handleToggle = () => {
    if (!interactive) return;
    setIsOpen((prev) => !prev);
  };

  const handleOptionClick = (option: (typeof select.options)[0]) => {
    setIsOpen(false);
    if (!onInteract) return;
    if (option.action && option.target) {
      const actionType = option.action as SimulationAction["type"];
      if (actionType === "navigate" || actionType === "channel" || actionType === "role") {
        onInteract({ type: actionType, target: option.target });
      }
    }
  };

  return (
    <div className="dc-select-wrapper">
      <div
        className={`dc-select${interactive ? " interactive" : ""}`}
        onClick={handleToggle}
      >
        {select.placeholder || "Make a selection"}
      </div>

      {isOpen && (
        <>
          <div className="dc-select-backdrop" onClick={() => setIsOpen(false)} />
          <div className="dc-select-dropdown">
            {(select.options || []).map((opt, i) => (
              <div
                key={i}
                className="dc-select-option"
                onClick={() => handleOptionClick(opt)}
              >
                {opt.emoji && <span className="dc-select-option-emoji">{opt.emoji}</span>}
                <div className="dc-select-option-text">
                  <span className="dc-select-option-label">{opt.label}</span>
                  {opt.description && (
                    <span className="dc-select-option-desc">{opt.description}</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

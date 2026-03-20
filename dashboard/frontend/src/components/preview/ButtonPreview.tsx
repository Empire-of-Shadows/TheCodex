import type { ButtonDef, SimulationAction } from "../../api/types";
import { VALID_ACTIONS } from "../../api/types";

interface Props {
  button: ButtonDef;
  onInteract?: (action: SimulationAction) => void;
}

export default function ButtonPreview({ button, onInteract }: Props) {
  const interactive = !!onInteract;

  const handleClick = () => {
    if (!onInteract) return;

    if (button.action === "navigate" && button.target) {
      onInteract({ type: "navigate", target: button.target });
    } else if (button.action === "channel" && button.target) {
      onInteract({ type: "channel", target: button.target });
    } else if (button.action === "role" && button.target) {
      onInteract({ type: "role", target: button.target });
    } else if (button.style === "link" && button.url) {
      window.open(button.url, "_blank");
    } else if (button.action && button.action in VALID_ACTIONS) {
      onInteract({ type: "welcome_action", action: button.action });
    } else if (button.action) {
      onInteract({ type: button.action as SimulationAction["type"] });
    }
  };

  return (
    <div
      className={`dc-button ${button.style || "secondary"}${interactive ? " interactive" : ""}`}
      onClick={interactive ? handleClick : undefined}
    >
      {button.emoji && <span>{button.emoji}</span>}
      {button.label || "Button"}
      {button.style === "link" && <span className="link-icon">↗</span>}
    </div>
  );
}

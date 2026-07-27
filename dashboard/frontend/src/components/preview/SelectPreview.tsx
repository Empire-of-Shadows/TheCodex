import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import type { SelectDef, SimulationAction } from "../../api/types";

interface Props {
  select: SelectDef;
  onInteract?: (action: SimulationAction) => void;
}

export default function SelectPreview({ select, onInteract }: Props) {
  const [isOpen, setIsOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const interactive = !!onInteract;
  const options = select.options || [];
  const listboxId = useId();
  const wrapperRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    function onDocClick(e: MouseEvent) {
      if (!wrapperRef.current?.contains(e.target as Node)) setIsOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [isOpen]);

  function close() {
    setIsOpen(false);
    triggerRef.current?.focus();
  }

  function commit(option: (typeof options)[number]) {
    setIsOpen(false);
    triggerRef.current?.focus();
    if (!onInteract) return;
    if (option.action && option.target) {
      // Board's "reply" maps to the board_reply simulation action; the rest
      // share their name with the simulation action type.
      if (option.action === "reply") {
        onInteract({ type: "board_reply", target: option.target });
        return;
      }
      const actionType = option.action as SimulationAction["type"];
      if (actionType === "navigate" || actionType === "channel" || actionType === "role") {
        onInteract({ type: actionType, target: option.target });
      }
    }
  }

  function onTriggerKey(e: KeyboardEvent<HTMLDivElement>) {
    if (!interactive) return;
    if (e.key === "Enter" || e.key === " " || e.key === "ArrowDown") {
      e.preventDefault();
      setIsOpen(true);
      setActiveIndex(0);
    } else if (e.key === "Escape" && isOpen) {
      e.preventDefault();
      close();
    } else if (e.key === "ArrowUp" && !isOpen) {
      e.preventDefault();
      setIsOpen(true);
      setActiveIndex(Math.max(0, options.length - 1));
    }
  }

  function onListKey(e: KeyboardEvent<HTMLDivElement>) {
    if (!options.length) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => (i + 1) % options.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => (i - 1 + options.length) % options.length);
    } else if (e.key === "Home") {
      e.preventDefault();
      setActiveIndex(0);
    } else if (e.key === "End") {
      e.preventDefault();
      setActiveIndex(options.length - 1);
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      commit(options[activeIndex]);
    } else if (e.key === "Escape" || e.key === "Tab") {
      if (e.key === "Escape") e.preventDefault();
      close();
    }
  }

  const activeOptionId = options.length ? `${listboxId}-opt-${activeIndex}` : undefined;

  return (
    <div className="dc-select-wrapper" ref={wrapperRef}>
      <div
        ref={triggerRef}
        className={`dc-select${interactive ? " interactive" : ""}`}
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-controls={isOpen ? listboxId : undefined}
        aria-activedescendant={isOpen ? activeOptionId : undefined}
        tabIndex={interactive ? 0 : -1}
        onClick={() => interactive && setIsOpen((p) => !p)}
        onKeyDown={onTriggerKey}
      >
        {select.placeholder || "Make a selection"}
      </div>

      {isOpen && (
        <>
          <div className="dc-select-backdrop" onClick={() => setIsOpen(false)} />
          <div
            id={listboxId}
            className="dc-select-dropdown"
            role="listbox"
            tabIndex={-1}
            onKeyDown={onListKey}
            ref={(el) => el?.focus()}
          >
            {options.map((opt, i) => (
              <div
                key={i}
                id={`${listboxId}-opt-${i}`}
                role="option"
                aria-selected={i === activeIndex}
                className={`dc-select-option${i === activeIndex ? " is-active" : ""}`}
                onMouseEnter={() => setActiveIndex(i)}
                onClick={() => commit(opt)}
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

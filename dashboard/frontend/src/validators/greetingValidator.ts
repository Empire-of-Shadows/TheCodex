/**
 * Greeting schema validator - port of Features/NewMembers/greeting_schema.py
 */

import {
  validateAccentColor,
  validateComponentsList,
  validateStringSelect,
  type ActionValidator,
  type ValidationResult,
} from "./componentValidator";
import { checkNoDangerousContent } from "./safeContent";
import { VALID_ACTIONS } from "../api/types";

const VALID_BUTTON_STYLES = new Set(["primary", "secondary", "success", "danger", "link"]);
const actionNames = Object.keys(VALID_ACTIONS);

export function validateGreetingSchema(data: unknown): ValidationResult {
  if (typeof data !== "object" || data === null) {
    return { valid: false, error: "Top-level value must be a JSON object." };
  }
  const d = data as Record<string, unknown>;

  if ("accent_color" in d) {
    const r = validateAccentColor(d.accent_color);
    if (!r.valid) return r;
  }

  if (!("components" in d)) {
    return { valid: false, error: 'Missing required field: "components".' };
  }

  const r = validateComponentsList(d.components, validateGreetingButton, validateGreetingSelect);
  if (!r.valid) return r;

  // Content-safety scan runs last so structural errors keep their specific messages.
  return checkNoDangerousContent(data);
}

const validateGreetingButton: ActionValidator = (comp, prefix) => {
  const style = comp.style as string;
  if (!VALID_BUTTON_STYLES.has(style)) {
    return { valid: false, error: `${prefix} - style "${style}" is invalid.` };
  }
  if (typeof comp.label !== "string" || !comp.label) {
    return { valid: false, error: `${prefix} - label must be a non-empty string.` };
  }
  if ((comp.label as string).length > 80) {
    return { valid: false, error: `${prefix} - label exceeds 80 characters.` };
  }
  if (style === "link") {
    if (typeof comp.url !== "string" || !(comp.url as string).startsWith("https://")) {
      return { valid: false, error: `${prefix} - url is required for link buttons and must start with https://.` };
    }
    if ("action" in comp) return { valid: false, error: `${prefix} - link buttons must not have "action".` };
  } else {
    const action = comp.action as string;
    if (typeof action !== "string" || !action) {
      return { valid: false, error: `${prefix} - action is required for non-link buttons.` };
    }
    if (!(action in VALID_ACTIONS)) {
      return { valid: false, error: `${prefix} - action "${action}" is not valid. Valid: ${actionNames.sort().join(", ")}.` };
    }
    if ("url" in comp) return { valid: false, error: `${prefix} - non-link buttons must not have "url".` };
  }
  return { valid: true, error: "" };
};

const validateGreetingSelect: ActionValidator = (comp, prefix) => {
  const optionValidator: ActionValidator = (opt, pfx) => {
    if (typeof opt.label !== "string" || !opt.label) return { valid: false, error: `${pfx} - label must be a non-empty string.` };
    if ((opt.label as string).length > 100) return { valid: false, error: `${pfx} - label exceeds 100 characters.` };
    const action = opt.action as string;
    if (typeof action !== "string" || !action) return { valid: false, error: `${pfx} - action is required.` };
    if (!(action in VALID_ACTIONS)) return { valid: false, error: `${pfx} - action "${action}" is not valid.` };
    if (opt.description !== undefined && opt.description !== null) {
      if (typeof opt.description !== "string") return { valid: false, error: `${pfx} - description must be a string.` };
      if ((opt.description as string).length > 100) return { valid: false, error: `${pfx} - description exceeds 100 characters.` };
    }
    return { valid: true, error: "" };
  };
  return validateStringSelect(comp, prefix, optionValidator);
};

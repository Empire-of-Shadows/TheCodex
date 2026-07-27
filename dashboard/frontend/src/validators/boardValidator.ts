/**
 * Info board schema validator - port of Features/Board/board_schema.py
 *
 * Kept in step with the Python validator: the same rules run client-side for
 * live feedback and server-side as the authority on save.
 */

import {
  validateAccentColor,
  validateComponentsList,
  validateStringSelect,
  type ActionValidator,
  type ValidationResult,
} from "./componentValidator";
import { checkNoDangerousContent } from "./safeContent";
import { BOARD_ACTIONS } from "../api/types";

const VALID_BUTTON_STYLES = new Set(["primary", "secondary", "success", "danger", "link"]);
const ALLOWED_TOP_LEVEL = new Set(["accent_color", "components", "responses"]);
const ALLOWED_RESPONSE_KEYS = new Set(["id", "label", "accent_color", "components"]);

const MAX_RESPONSES = 25;
const MAX_CUSTOM_ID = 100;

// Mirrors _RESPONSE_ID_RE in board_schema.py.
const RESPONSE_ID_RE = /^[a-z0-9][a-z0-9_-]{0,47}$/;

const actionNames = Object.keys(BOARD_ACTIONS).sort().join(", ");

/** Mirrors board_actions.encode_custom_id so length checks measure the real string. */
function encodeCustomId(action: string, target: string): string {
  if (action === "reply") return `b:r:${target}`;
  return `b:${action}:${target}`;
}

export function validateBoardSchema(data: unknown): ValidationResult {
  if (typeof data !== "object" || data === null) {
    return { valid: false, error: "Top-level value must be a JSON object." };
  }
  const d = data as Record<string, unknown>;

  const unknown = Object.keys(d).filter((k) => !ALLOWED_TOP_LEVEL.has(k));
  if (unknown.length) {
    return { valid: false, error: `Unknown top-level field(s): ${unknown.sort().join(", ")}.` };
  }

  if ("accent_color" in d) {
    const r = validateAccentColor(d.accent_color);
    if (!r.valid) return r;
  }

  if (!("components" in d)) {
    return { valid: false, error: 'Missing required field: "components".' };
  }

  // Collect response ids first so the board's own buttons can be checked against them.
  const collected = collectResponseIds(d.responses);
  if (!collected.result.valid) return collected.result;
  const ids = collected.ids;

  const r = validateComponentsList(
    d.components,
    makeButtonValidator(ids),
    makeSelectValidator(ids),
  );
  if (!r.valid) return r;

  // Each response is a components layout in its own right.
  const responses = (d.responses as Record<string, unknown>[] | undefined) ?? [];
  for (let i = 0; i < responses.length; i++) {
    const resp = responses[i];
    const label = resp.id ? `Response "${resp.id}"` : `Response #${i + 1}`;
    const rr = validateComponentsList(
      resp.components,
      makeButtonValidator(ids),
      makeSelectValidator(ids),
    );
    if (!rr.valid) return { valid: false, error: `${label} -> ${rr.error}` };
  }

  // Content-safety scan runs last so structural errors keep their specific messages.
  return checkNoDangerousContent(data);
}

function collectResponseIds(responses: unknown): { result: ValidationResult; ids: Set<string> } {
  const ok = { result: { valid: true, error: "" } as ValidationResult, ids: new Set<string>() };
  const fail = (error: string) => ({ result: { valid: false, error }, ids: new Set<string>() });

  if (responses === undefined || responses === null) return ok;
  if (!Array.isArray(responses)) return fail('"responses" must be an array.');
  if (responses.length > MAX_RESPONSES) {
    return fail(`responses has ${responses.length} items; max is ${MAX_RESPONSES}.`);
  }

  const ids = new Set<string>();
  for (let i = 0; i < responses.length; i++) {
    const resp = responses[i];
    const prefix = `Response #${i + 1}`;
    if (typeof resp !== "object" || resp === null || Array.isArray(resp)) {
      return fail(`${prefix} - must be an object.`);
    }
    const r = resp as Record<string, unknown>;

    const unknown = Object.keys(r).filter((k) => !ALLOWED_RESPONSE_KEYS.has(k));
    if (unknown.length) return fail(`${prefix} - unknown field(s): ${unknown.sort().join(", ")}.`);

    const rid = r.id;
    if (typeof rid !== "string" || !rid) return fail(`${prefix} - id must be a non-empty string.`);
    if (!RESPONSE_ID_RE.test(rid)) {
      return fail(
        `${prefix} - id "${rid}" is invalid. Use lowercase letters, digits, hyphens and ` +
          `underscores, starting with a letter or digit, max 48 characters.`,
      );
    }
    if (ids.has(rid)) return fail(`${prefix} - duplicate response id "${rid}".`);

    const encoded = encodeCustomId("reply", rid);
    if (encoded.length > MAX_CUSTOM_ID) {
      return fail(
        `${prefix} - id "${rid}" makes a custom_id of ${encoded.length} characters; ` +
          `max is ${MAX_CUSTOM_ID}.`,
      );
    }

    if (r.label !== undefined && r.label !== null) {
      if (typeof r.label !== "string") return fail(`${prefix} - label must be a string.`);
      if (r.label.length > 100) return fail(`${prefix} - label exceeds 100 characters.`);
    }

    if ("accent_color" in r) {
      const ac = validateAccentColor(r.accent_color);
      if (!ac.valid) return fail(`${prefix} - ${ac.error}`);
    }

    if (!("components" in r)) {
      return fail(`${prefix} - missing required field: "components".`);
    }

    ids.add(rid);
  }

  return { result: { valid: true, error: "" }, ids };
}

function makeButtonValidator(ids: Set<string>): ActionValidator {
  return (comp, prefix) => {
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
        return {
          valid: false,
          error: `${prefix} - url is required for link buttons and must start with https://.`,
        };
      }
      for (const forbidden of ["action", "target", "custom_id"]) {
        if (forbidden in comp) {
          return { valid: false, error: `${prefix} - link buttons must not have "${forbidden}".` };
        }
      }
      return { valid: true, error: "" };
    }

    if ("url" in comp) {
      return { valid: false, error: `${prefix} - non-link buttons must not have "url".` };
    }
    return validateActionTarget(comp, prefix, ids);
  };
}

function makeSelectValidator(ids: Set<string>): ActionValidator {
  return (comp, prefix) => {
    const optionValidator: ActionValidator = (opt, pfx) => {
      if (typeof opt.label !== "string" || !opt.label) {
        return { valid: false, error: `${pfx} - label must be a non-empty string.` };
      }
      if ((opt.label as string).length > 100) {
        return { valid: false, error: `${pfx} - label exceeds 100 characters.` };
      }
      if (opt.description !== undefined && opt.description !== null) {
        if (typeof opt.description !== "string") {
          return { valid: false, error: `${pfx} - description must be a string.` };
        }
        if ((opt.description as string).length > 100) {
          return { valid: false, error: `${pfx} - description exceeds 100 characters.` };
        }
      }
      return validateActionTarget(opt, pfx, ids);
    };
    return validateStringSelect(comp, prefix, optionValidator);
  };
}

function validateActionTarget(
  comp: Record<string, unknown>,
  prefix: string,
  ids: Set<string>,
): ValidationResult {
  const action = comp.action as string;
  if (typeof action !== "string" || !action) {
    return { valid: false, error: `${prefix} - action is required. Valid actions: ${actionNames}.` };
  }
  if (!(action in BOARD_ACTIONS)) {
    return {
      valid: false,
      error: `${prefix} - action "${action}" is not a valid action. Valid actions: ${actionNames}.`,
    };
  }

  const target = comp.target as string;
  if (typeof target !== "string" || !target) {
    return { valid: false, error: `${prefix} - target is required for the "${action}" action.` };
  }

  if (action === "reply") {
    if (!ids.has(target)) {
      const known = ids.size ? [...ids].sort().join(", ") : "none defined";
      return {
        valid: false,
        error: `${prefix} - points at response "${target}", which does not exist. Known responses: ${known}.`,
      };
    }
  } else if (!/^\d+$/.test(target)) {
    return {
      valid: false,
      error: `${prefix} - target for the "${action}" action must be a Discord ID (digits only).`,
    };
  }

  const encoded = encodeCustomId(action, target);
  if (encoded.length > MAX_CUSTOM_ID) {
    return { valid: false, error: `${prefix} - encoded custom_id exceeds ${MAX_CUSTOM_ID} characters.` };
  }

  return { valid: true, error: "" };
}

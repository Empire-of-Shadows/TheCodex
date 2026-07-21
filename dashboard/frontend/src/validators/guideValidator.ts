/**
 * Guide schema validator - port of Features/Guide/guide_schema.py
 *
 * Error messages use human-readable paths:
 *   Page "Getting Started" → Action Row #1 → Button "Click Here" - target is required for navigate buttons.
 */

import {
  validateAccentColor,
  validateComponentsList,
  validateStringSelect,
  truncLabel,
  type ActionValidator,
  type ValidationResult,
} from "./componentValidator";
import { checkNoDangerousContent } from "./safeContent";

const OK: ValidationResult = { valid: true, error: "" };
const MAX_LABEL = 100;
const MAX_DESCRIPTION = 100;
const MAX_DEPTH = 5;
const VALID_BUTTON_STYLES = new Set(["primary", "secondary", "success", "danger", "link"]);
const VALID_GUIDE_ACTIONS = new Set(["navigate", "channel", "role"]);

function pageLabel(page: unknown, idx: number): string {
  if (typeof page === "object" && page !== null) {
    const label = (page as Record<string, unknown>).label;
    if (typeof label === "string" && label) return `Page "${truncLabel(label)}"`;
  }
  return `Page #${idx + 1}`;
}

export function validateGuideSchema(data: unknown): ValidationResult {
  if (typeof data !== "object" || data === null) {
    return { valid: false, error: "Top-level value must be a JSON object." };
  }
  const d = data as Record<string, unknown>;

  if ("accent_color" in d) {
    const r = validateAccentColor(d.accent_color);
    if (!r.valid) return r;
  }

  if (!("pages" in d)) {
    return { valid: false, error: 'Missing required field: "pages".' };
  }
  const pages = d.pages;
  if (!Array.isArray(pages) || pages.length === 0) {
    return { valid: false, error: '"pages" must be a non-empty array.' };
  }

  const allIds = new Set<string>();
  const navigateTargets: string[] = [];

  const r = validatePages(pages, "", allIds, navigateTargets, 0);
  if (!r.valid) return r;

  for (const target of navigateTargets) {
    if (!allIds.has(target)) {
      return { valid: false, error: `Navigate action targets page "${target}" which does not exist.` };
    }
  }

  // Content-safety scan runs last so structural errors keep their specific messages.
  const safe = checkNoDangerousContent(data);
  if (!safe.valid) return safe;

  return OK;
}

function validatePages(
  pages: unknown[],
  prefix: string,
  allIds: Set<string>,
  navigateTargets: string[],
  depth: number
): ValidationResult {
  if (depth > MAX_DEPTH) {
    const ctx = prefix || "Pages";
    return { valid: false, error: `${ctx} - page nesting exceeds maximum depth of ${MAX_DEPTH}.` };
  }
  for (let i = 0; i < pages.length; i++) {
    const pageName = pageLabel(pages[i], i);
    const pagePrefix = prefix ? `${prefix} → ${pageName}` : pageName;
    const r = validatePage(pages[i], pagePrefix, allIds, navigateTargets, depth);
    if (!r.valid) return r;
  }
  return OK;
}

function validatePage(
  page: unknown,
  prefix: string,
  allIds: Set<string>,
  navigateTargets: string[],
  depth: number
): ValidationResult {
  if (typeof page !== "object" || page === null) {
    return { valid: false, error: `${prefix} - must be an object.` };
  }
  const p = page as Record<string, unknown>;

  // label
  if (typeof p.label !== "string" || !p.label) {
    return { valid: false, error: `${prefix} - label must be a non-empty string.` };
  }
  if ((p.label as string).length > MAX_LABEL) {
    return { valid: false, error: `${prefix} - label exceeds ${MAX_LABEL} characters.` };
  }

  // id
  if (p.id !== undefined && p.id !== null) {
    if (typeof p.id !== "string" || !p.id) {
      return { valid: false, error: `${prefix} - id must be a non-empty string.` };
    }
    if ((p.id as string).length > 100) {
      return { valid: false, error: `${prefix} - id exceeds 100 characters.` };
    }
    if (allIds.has(p.id as string)) {
      return { valid: false, error: `${prefix} - id "${p.id}" is duplicated.` };
    }
    allIds.add(p.id as string);
  }

  // description
  if (p.description !== undefined && p.description !== null) {
    if (typeof p.description !== "string") {
      return { valid: false, error: `${prefix} - description must be a string.` };
    }
    if ((p.description as string).length > MAX_DESCRIPTION) {
      return { valid: false, error: `${prefix} - description exceeds ${MAX_DESCRIPTION} characters.` };
    }
  }

  // icon
  if (p.icon !== undefined && p.icon !== null && typeof p.icon !== "string") {
    return { valid: false, error: `${prefix} - icon must be a string.` };
  }

  // order
  if (p.order !== undefined && p.order !== null && typeof p.order !== "number") {
    return { valid: false, error: `${prefix} - order must be an integer.` };
  }

  // content
  if (p.content !== undefined && p.content !== null) {
    if (typeof p.content !== "object") {
      return { valid: false, error: `${prefix} - content must be an object.` };
    }
    const content = p.content as Record<string, unknown>;
    if (content.components !== undefined) {
      const actionVal: ActionValidator = (comp, pfx) => validateGuideButton(comp, pfx, navigateTargets);
      const selectVal: ActionValidator = (comp, pfx) => validateGuideSelect(comp, pfx, navigateTargets);
      const r = validateComponentsList(content.components, actionVal, selectVal);
      if (!r.valid) return { valid: false, error: `${prefix} → ${r.error}` };
    }
  }

  // children
  if (p.children !== undefined && p.children !== null) {
    if (!Array.isArray(p.children)) {
      return { valid: false, error: `${prefix} - children must be an array.` };
    }
    if (p.children.length > 25) {
      return { valid: false, error: `${prefix} - children has ${p.children.length} items; max is 25.` };
    }
    const r = validatePages(p.children, prefix, allIds, navigateTargets, depth + 1);
    if (!r.valid) return r;
  }

  // Must have content or children
  if (p.content === undefined && p.children === undefined) {
    return { valid: false, error: `${prefix} - must have "content", "children", or both.` };
  }

  return OK;
}

function validateGuideButton(
  comp: Record<string, unknown>,
  prefix: string,
  navigateTargets: string[]
): ValidationResult {
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
  } else {
    if (typeof comp.action !== "string" || !comp.action) {
      return { valid: false, error: `${prefix} - action is required for non-link buttons.` };
    }
    if (!VALID_GUIDE_ACTIONS.has(comp.action as string)) {
      return { valid: false, error: `${prefix} - action "${comp.action}" is not valid. Guide buttons support: channel, navigate, role.` };
    }
    if (typeof comp.target !== "string" || !comp.target) {
      return { valid: false, error: `${prefix} - target is required for ${comp.action} buttons.` };
    }
    if (comp.action === "navigate") {
      navigateTargets.push(comp.target as string);
    }
  }
  return OK;
}

function validateGuideSelect(
  comp: Record<string, unknown>,
  prefix: string,
  navigateTargets: string[]
): ValidationResult {
  const optionValidator: ActionValidator = (opt, pfx) => {
    if (typeof opt !== "object" || opt === null) return { valid: false, error: `${pfx} - must be an object.` };
    if (typeof opt.label !== "string" || !opt.label) return { valid: false, error: `${pfx} - label must be a non-empty string.` };
    if ((opt.label as string).length > 100) return { valid: false, error: `${pfx} - label exceeds 100 characters.` };
    if (typeof opt.action !== "string" || !opt.action || !VALID_GUIDE_ACTIONS.has(opt.action as string)) {
      return { valid: false, error: `${pfx} - action "${opt.action}" is not valid. Guide select options support: channel, navigate, role.` };
    }
    if (typeof opt.target !== "string" || !opt.target) return { valid: false, error: `${pfx} - target is required for ${opt.action} options.` };
    if (opt.action === "navigate") {
      navigateTargets.push(opt.target as string);
    }
    if (opt.description !== undefined && opt.description !== null) {
      if (typeof opt.description !== "string") return { valid: false, error: `${pfx} - description must be a string.` };
      if ((opt.description as string).length > 100) return { valid: false, error: `${pfx} - description exceeds 100 characters.` };
    }
    if (opt.emoji !== undefined && opt.emoji !== null && typeof opt.emoji !== "string") {
      return { valid: false, error: `${pfx} - emoji must be a string.` };
    }
    return { valid: true, error: "" };
  };
  return validateStringSelect(comp, prefix, optionValidator);
}

/**
 * Client-side component validators - port of utils/component_validators.py
 *
 * Error messages use human-readable paths:
 *   - Arrow (→) separates path segments: "Container #1 → Text #2"
 *   - Dash (-) separates path from error: "Button #1 - label must be a non-empty string."
 */

export interface ValidationResult {
  valid: boolean;
  error: string;
}

const OK: ValidationResult = { valid: true, error: "" };

const VALID_BUTTON_STYLES = new Set(["primary", "secondary", "success", "danger", "link"]);
const VALID_TOP_LEVEL_TYPES = new Set(["separator", "text", "section", "action_row", "container", "media_gallery"]);
const ACCENT_COLOR_RE = /^#[0-9A-Fa-f]{6}$/;

export type ActionValidator = (comp: Record<string, unknown>, prefix: string) => ValidationResult;

const TYPE_LABELS: Record<string, string> = {
  text: "Text",
  section: "Section",
  action_row: "Action Row",
  container: "Container",
  media_gallery: "Gallery",
  separator: "Separator",
};

export function truncLabel(label: string, maxLen = 30): string {
  if (label.length <= maxLen) return label;
  return label.slice(0, maxLen - 3) + "...";
}

function componentLabel(comp: unknown, idx: number): string {
  if (typeof comp !== "object" || comp === null) return `Component #${idx + 1}`;
  const c = comp as Record<string, unknown>;
  const compType = (c.type as string) || "";
  const typeName = TYPE_LABELS[compType] ?? (compType ? compType.charAt(0).toUpperCase() + compType.slice(1) : "Component");
  return `${typeName} #${idx + 1}`;
}

function buttonLabel(btn: unknown, idx: number): string {
  if (typeof btn === "object" && btn !== null) {
    const label = (btn as Record<string, unknown>).label;
    if (typeof label === "string" && label) return `Button "${truncLabel(label)}"`;
  }
  return `Button #${idx + 1}`;
}

function optionLabel(opt: unknown, idx: number): string {
  if (typeof opt === "object" && opt !== null) {
    const label = (opt as Record<string, unknown>).label;
    if (typeof label === "string" && label) return `Option "${truncLabel(label)}"`;
  }
  return `Option #${idx + 1}`;
}

export function validateAccentColor(value: unknown): ValidationResult {
  if (typeof value === "number") {
    if (value >= 0 && value <= 16777215) return OK;
    return { valid: false, error: `accent_color integer ${value} is out of range (0-16777215).` };
  }
  if (typeof value === "string") {
    if (ACCENT_COLOR_RE.test(value)) return OK;
    return { valid: false, error: `accent_color string "${value}" must be in #RRGGBB format.` };
  }
  return { valid: false, error: "accent_color must be a hex string (#RRGGBB) or an integer." };
}

export function validateText(comp: Record<string, unknown>, prefix: string): ValidationResult {
  const content = comp.content;
  if (typeof content !== "string" || !content) {
    return { valid: false, error: `${prefix} - content must be a non-empty string.` };
  }
  if (content.length > 4000) {
    return { valid: false, error: `${prefix} - content exceeds 4000 characters.` };
  }
  return OK;
}

export function validateThumbnail(comp: Record<string, unknown>, prefix: string): ValidationResult {
  const media = comp.media;
  if (typeof media !== "string" || !media) {
    return { valid: false, error: `${prefix} - media must be a non-empty string.` };
  }
  if (media !== "member_avatar") {
    return { valid: false, error: `${prefix} - media must be "member_avatar".` };
  }
  return OK;
}

function validateButtonStructure(comp: Record<string, unknown>, prefix: string): ValidationResult {
  const style = comp.style as string;
  if (!VALID_BUTTON_STYLES.has(style)) {
    return { valid: false, error: `${prefix} - style "${style}" is invalid. Valid: ${[...VALID_BUTTON_STYLES].sort().join(", ")}.` };
  }
  const label = comp.label;
  if (typeof label !== "string" || !label) {
    return { valid: false, error: `${prefix} - label must be a non-empty string.` };
  }
  if (label.length > 80) {
    return { valid: false, error: `${prefix} - label exceeds 80 characters.` };
  }
  if (style === "link") {
    const url = comp.url;
    if (typeof url !== "string" || !url.startsWith("https://")) {
      return { valid: false, error: `${prefix} - url is required for link buttons and must start with https://.` };
    }
  }
  return OK;
}

function validateSelectOptionStructure(opt: unknown, prefix: string): ValidationResult {
  if (typeof opt !== "object" || opt === null) {
    return { valid: false, error: `${prefix} - must be an object.` };
  }
  const o = opt as Record<string, unknown>;
  const label = o.label;
  if (typeof label !== "string" || !label) {
    return { valid: false, error: `${prefix} - label must be a non-empty string.` };
  }
  if (label.length > 100) {
    return { valid: false, error: `${prefix} - label exceeds 100 characters.` };
  }
  if (o.description !== undefined && o.description !== null) {
    if (typeof o.description !== "string") return { valid: false, error: `${prefix} - description must be a string.` };
    if ((o.description as string).length > 100) return { valid: false, error: `${prefix} - description exceeds 100 characters.` };
  }
  if (o.emoji !== undefined && o.emoji !== null && typeof o.emoji !== "string") {
    return { valid: false, error: `${prefix} - emoji must be a string.` };
  }
  return OK;
}

export function validateStringSelect(
  comp: unknown,
  prefix: string,
  optionValidator?: ActionValidator
): ValidationResult {
  if (typeof comp !== "object" || comp === null) {
    return { valid: false, error: `${prefix} - must be an object.` };
  }
  const c = comp as Record<string, unknown>;
  if (c.placeholder !== undefined && c.placeholder !== null) {
    if (typeof c.placeholder !== "string") return { valid: false, error: `${prefix} - placeholder must be a string.` };
    if ((c.placeholder as string).length > 150) return { valid: false, error: `${prefix} - placeholder exceeds 150 characters.` };
  }
  const options = c.options;
  if (!Array.isArray(options) || options.length === 0) {
    return { valid: false, error: `${prefix} - options must be a non-empty array.` };
  }
  if (options.length > 25) {
    return { valid: false, error: `${prefix} - options has ${options.length} items; max is 25.` };
  }
  for (let i = 0; i < options.length; i++) {
    const optPfx = `${prefix} → ${optionLabel(options[i], i)}`;
    const r = optionValidator
      ? optionValidator(options[i] as Record<string, unknown>, optPfx)
      : validateSelectOptionStructure(options[i], optPfx);
    if (!r.valid) return r;
  }
  for (const field of ["min_values", "max_values"] as const) {
    const val = c[field];
    if (val !== undefined && val !== null) {
      if (typeof val !== "number" || val < 1 || val > 25) {
        return { valid: false, error: `${prefix} - ${field} must be an integer between 1 and 25.` };
      }
    }
  }
  return OK;
}

export function validateSection(
  comp: Record<string, unknown>,
  prefix: string,
  actionValidator?: ActionValidator
): ValidationResult {
  const content = comp.content;
  if (!Array.isArray(content) || content.length === 0) {
    return { valid: false, error: `${prefix} - content must be a non-empty array.` };
  }
  if (content.length > 3) {
    return { valid: false, error: `${prefix} - content has ${content.length} items; max is 3.` };
  }
  for (let i = 0; i < content.length; i++) {
    const item = content[i] as Record<string, unknown>;
    const itemPrefix = `${prefix} → Text #${i + 1}`;
    if (typeof item !== "object" || item === null || item.type !== "text") {
      return { valid: false, error: `${itemPrefix} - must be a text component.` };
    }
    const r = validateText(item, itemPrefix);
    if (!r.valid) return r;
  }
  const accessory = comp.accessory;
  if (accessory === undefined || accessory === null) {
    return { valid: false, error: `${prefix} - accessory is required.` };
  }
  if (typeof accessory !== "object") {
    return { valid: false, error: `${prefix} → Accessory - must be an object.` };
  }
  const acc = accessory as Record<string, unknown>;
  const accPrefix = `${prefix} → Accessory`;
  if (acc.type === "thumbnail") return validateThumbnail(acc, accPrefix);
  if (acc.type === "button") {
    return actionValidator
      ? actionValidator(acc, accPrefix)
      : validateButtonStructure(acc, accPrefix);
  }
  return { valid: false, error: `${accPrefix} - type "${acc.type}" is invalid; must be "thumbnail" or "button".` };
}

export function validateActionRow(
  comp: Record<string, unknown>,
  prefix: string,
  actionValidator?: ActionValidator,
  selectValidator?: ActionValidator
): ValidationResult {
  const hasButtons = "buttons" in comp;
  const hasSelect = "select" in comp;
  if (hasButtons && hasSelect) {
    return { valid: false, error: `${prefix} - cannot have both "buttons" and "select".` };
  }
  if (!hasButtons && !hasSelect) {
    return { valid: false, error: `${prefix} - must have either "buttons" or "select".` };
  }
  if (hasSelect) {
    const selectPrefix = `${prefix} → Select menu`;
    return selectValidator
      ? selectValidator(comp.select as Record<string, unknown>, selectPrefix)
      : validateStringSelect(comp.select, selectPrefix);
  }
  const buttons = comp.buttons;
  if (!Array.isArray(buttons) || buttons.length === 0) {
    return { valid: false, error: `${prefix} - buttons must be a non-empty array.` };
  }
  if (buttons.length > 5) {
    return { valid: false, error: `${prefix} - buttons has ${buttons.length} items; max is 5.` };
  }
  for (let i = 0; i < buttons.length; i++) {
    const btnPfx = `${prefix} → ${buttonLabel(buttons[i], i)}`;
    const r = actionValidator
      ? actionValidator(buttons[i] as Record<string, unknown>, btnPfx)
      : validateButtonStructure(buttons[i] as Record<string, unknown>, btnPfx);
    if (!r.valid) return r;
  }
  return OK;
}

export function validateMediaGallery(comp: Record<string, unknown>, prefix: string): ValidationResult {
  const items = comp.items;
  if (!Array.isArray(items) || items.length === 0) {
    return { valid: false, error: `${prefix} - items must be a non-empty array.` };
  }
  if (items.length > 10) {
    return { valid: false, error: `${prefix} - items has ${items.length} items; max is 10.` };
  }
  for (let i = 0; i < items.length; i++) {
    const item = items[i] as Record<string, unknown>;
    const itemPrefix = `${prefix} → Image #${i + 1}`;
    if (typeof item !== "object" || item === null) {
      return { valid: false, error: `${itemPrefix} - must be an object.` };
    }
    if (typeof item.media !== "string" || !(item.media as string).startsWith("https://")) {
      return { valid: false, error: `${itemPrefix} - media must be an https:// URL.` };
    }
    if (item.description !== undefined && item.description !== null) {
      if (typeof item.description !== "string") return { valid: false, error: `${itemPrefix} - description must be a string.` };
      if ((item.description as string).length > 256) return { valid: false, error: `${itemPrefix} - description exceeds 256 characters.` };
    }
    if ("spoiler" in item && typeof item.spoiler !== "boolean") {
      return { valid: false, error: `${itemPrefix} - spoiler must be a boolean.` };
    }
  }
  return OK;
}

export function validateContainer(
  comp: Record<string, unknown>,
  prefix: string,
  actionValidator?: ActionValidator,
  selectValidator?: ActionValidator
): ValidationResult {
  if ("accent_color" in comp) {
    const r = validateAccentColor(comp.accent_color);
    if (!r.valid) return { valid: false, error: `${prefix} - ${r.error}` };
  }
  if ("spoiler" in comp && typeof comp.spoiler !== "boolean") {
    return { valid: false, error: `${prefix} - spoiler must be a boolean.` };
  }
  const components = comp.components;
  if (!Array.isArray(components) || components.length === 0) {
    return { valid: false, error: `${prefix} - components must be a non-empty array.` };
  }
  if (components.length > 10) {
    return { valid: false, error: `${prefix} - components has ${components.length} items; max is 10.` };
  }
  const allowed = new Set(["separator", "text", "section", "action_row", "media_gallery"]);
  for (let i = 0; i < components.length; i++) {
    const child = components[i] as Record<string, unknown>;
    const childPrefix = `${prefix} → ${componentLabel(child, i)}`;
    if (typeof child !== "object" || child === null) {
      return { valid: false, error: `${childPrefix} - must be an object.` };
    }
    if (!allowed.has(child.type as string)) {
      return { valid: false, error: `${childPrefix} - type "${child.type}" is invalid inside a container.` };
    }
    if (child.type === "separator") continue;
    const r = validateChildComponent(child, child.type as string, childPrefix, actionValidator, selectValidator);
    if (!r.valid) return r;
  }
  return OK;
}

function validateChildComponent(
  comp: Record<string, unknown>,
  compType: string,
  prefix: string,
  actionValidator?: ActionValidator,
  selectValidator?: ActionValidator
): ValidationResult {
  switch (compType) {
    case "text": return validateText(comp, prefix);
    case "section": return validateSection(comp, prefix, actionValidator);
    case "action_row": return validateActionRow(comp, prefix, actionValidator, selectValidator);
    case "container": return validateContainer(comp, prefix, actionValidator, selectValidator);
    case "media_gallery": return validateMediaGallery(comp, prefix);
    default: return OK;
  }
}

export function validateTopLevelComponent(
  comp: unknown,
  idx: number,
  actionValidator?: ActionValidator,
  selectValidator?: ActionValidator
): ValidationResult {
  const prefix = componentLabel(comp, idx);
  if (typeof comp !== "object" || comp === null) {
    return { valid: false, error: `${prefix} - must be an object.` };
  }
  const c = comp as Record<string, unknown>;
  if (!VALID_TOP_LEVEL_TYPES.has(c.type as string)) {
    return { valid: false, error: `${prefix} - type "${c.type}" is invalid.` };
  }
  if (c.type === "separator") return OK;
  return validateChildComponent(c, c.type as string, prefix, actionValidator, selectValidator);
}

export function validateComponentsList(
  components: unknown,
  actionValidator?: ActionValidator,
  selectValidator?: ActionValidator,
  maxItems = 10
): ValidationResult {
  if (!Array.isArray(components) || components.length === 0) {
    return { valid: false, error: "components must be a non-empty array." };
  }
  if (components.length > maxItems) {
    return { valid: false, error: `components has ${components.length} items; max is ${maxItems}.` };
  }
  for (let i = 0; i < components.length; i++) {
    const r = validateTopLevelComponent(components[i], i, actionValidator, selectValidator);
    if (!r.valid) return r;
  }
  return OK;
}

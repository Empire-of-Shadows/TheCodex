/**
 * Content-safety scan - shared guard against payloads that pass the structural
 * schema but are "not what we intend to be uploaded".
 *
 * Mirror of utils/safe_content.py (keep the two in sync). Applied to every guide
 * and welcome payload AFTER structural validation, on both the import path and the
 * builder's save path.
 *
 * Rejects:
 *   - Prototype-pollution keys anywhere in the object tree (__proto__/constructor/prototype).
 *   - Unsafe HTML / script markup in any string (<script>, <img onerror=…>, <svg onload=…>, …).
 *     The tag list deliberately omits short names that collide with Discord mention
 *     syntax (<@id>, <#id>, <:emoji:>, <a:emoji:>, </cmd:id>, <t:ts>), and allows
 *     ordinary markdown / mentions / non-Latin scripts.
 *   - Invisible / bidirectional control characters used for spoofing (Trojan Source).
 */

import type { ValidationResult } from "./componentValidator";

const OK: ValidationResult = { valid: true, error: "" };

const DANGEROUS_KEYS = new Set(["__proto__", "constructor", "prototype"]);

// Invisible / bidi control chars. Deliberately EXCLUDES U+200C/U+200D (ZWNJ/ZWJ) -
// those are required by emoji sequences and scripts like Persian and Indic.
// U+00AD soft hyphen, U+200B ZWSP, U+200E/F LRM/RLM, U+202A-E bidi embeds/overrides,
// U+2060 word joiner, U+2066-9 bidi isolates, U+FEFF ZWNBSP/BOM.
const INVISIBLE_CTRL = /[\u00AD\u200B\u200E\u200F\u202A-\u202E\u2060\u2066-\u2069\uFEFF]/;

// Unsafe HTML tags (opening or closing). Multi-character, non-colliding names only.
const UNSAFE_HTML_TAG =
  /<\s*\/?\s*(?:script|style|iframe|object|embed|svg|img|link|meta|base|video|audio|source|math|template|xml|noscript|frame|frameset|applet)\b/i;
// Inline event handlers: onerror=, onload=, onclick=, onmouseover=, …
const EVENT_HANDLER = /(?:^|[\s/;])on[a-z]{3,}\s*=/i;
// Dangerous URL schemes.
const DANGEROUS_SCHEME = /(?:javascript|vbscript)\s*:|data\s*:\s*text\/html/i;

/** Check a single string value for unsafe markup / control characters. */
export function checkSafeString(value: string, path: string): ValidationResult {
  if (INVISIBLE_CTRL.test(value)) {
    return { valid: false, error: `${path} contains a disallowed invisible or bidirectional control character.` };
  }
  if (UNSAFE_HTML_TAG.test(value) || EVENT_HANDLER.test(value) || DANGEROUS_SCHEME.test(value)) {
    return { valid: false, error: `${path} contains disallowed HTML or script markup.` };
  }
  return OK;
}

/**
 * Recursively scan a parsed JSON value. Returns the first violation found, or OK.
 * `path` builds a human-readable location (e.g. `pages[0].content.components[1].content`).
 */
export function checkNoDangerousContent(value: unknown, path = "value"): ValidationResult {
  if (typeof value === "string") {
    return checkSafeString(value, path);
  }
  if (Array.isArray(value)) {
    for (let i = 0; i < value.length; i++) {
      const r = checkNoDangerousContent(value[i], `${path}[${i}]`);
      if (!r.valid) return r;
    }
    return OK;
  }
  if (value !== null && typeof value === "object") {
    for (const key of Object.keys(value as Record<string, unknown>)) {
      if (DANGEROUS_KEYS.has(key)) {
        return { valid: false, error: `${path} contains a disallowed property name "${key}".` };
      }
      const childPath = path === "value" ? key : `${path}.${key}`;
      const r = checkNoDangerousContent((value as Record<string, unknown>)[key], childPath);
      if (!r.valid) return r;
    }
  }
  return OK;
}

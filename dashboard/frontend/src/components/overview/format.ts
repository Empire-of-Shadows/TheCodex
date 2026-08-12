/**
 * Codex-specific formatting.
 *
 * The generic half of this module (date, count, relative-time and Discord-link
 * helpers) moved to the shared engine at `_engine/format.ts` on 2026-08-12.
 * What stays here is the part that knows about codex's own domain: its question
 * formats and its suggestion statuses.
 */

/** Human name for a question format key. */
export function formatQuestionKind(kind: string): string {
  if (kind === "wyr") return "Would You Rather";
  if (kind === "poll") return "Question with answers";
  if (kind === "open") return "Open-ended";
  return kind;
}

/** Colour for a suggestion status dot. Always shipped beside the status word. */
export function statusColour(status: string): string {
  const key = status.toLowerCase();
  if (key === "implemented") return "var(--success)";
  if (key === "approved") return "var(--text-accent)";
  if (key === "pending") return "var(--warning)";
  if (key === "rejected" || key === "declined") return "var(--danger)";
  return "var(--text-muted)";
}

/** Status order the dashboard shows first; anything else follows as returned. */
export const STATUS_ORDER = ["Pending", "Approved", "Implemented", "Rejected"];

export function orderedStatuses(byStatus: Record<string, number>): [string, number][] {
  const known = STATUS_ORDER.filter((s) => s in byStatus).map(
    (s) => [s, byStatus[s]] as [string, number],
  );
  const rest = Object.entries(byStatus).filter(([s]) => !STATUS_ORDER.includes(s));
  return [...known, ...rest];
}

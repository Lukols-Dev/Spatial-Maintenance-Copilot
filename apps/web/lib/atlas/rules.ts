// What the service accepts in a field, checked as the reader types, so a form
// says what is wrong next to its button instead of after a round trip. Each
// problem is a fact in a few words; the service stays the judge.

/** The service's rule for view set names and asset ids: one safe path segment. */
export const NAME_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;
const NAME_LENGTH = 64;

/** Why `name` cannot name a view set or an atlas file, or null when it can. */
export function nameProblem(name: string, label: string): string | null {
  if (name === "") return `${label} missing`;
  if (name.length > NAME_LENGTH) return `${label} over ${NAME_LENGTH} characters`;
  if (!/^[A-Za-z0-9]/.test(name)) return `${label} needs a letter or digit first`;
  if (!NAME_PATTERN.test(name)) return `${label} has characters other than A–Z a–z 0–9 . _ -`;
  return null;
}

export interface NumberRule {
  /** Whole numbers only. */
  integer?: boolean;
  /** The value must be greater than this. */
  above?: number;
  /** The value must be at least this. */
  min?: number;
  max?: number;
  /** Written after the value in a problem, e.g. "mm". */
  unit?: string;
}

export type ReadNumber = { value: number } | { problem: string };

/** The number typed in a field, or what keeps it from being one the service takes. */
export function readNumber(text: string, label: string, rule: NumberRule = {}): ReadNumber {
  const typed = text.trim();
  if (typed === "") return { problem: `${label} missing` };
  const value = Number(typed);
  if (!Number.isFinite(value)) return { problem: `${label} not a number` };
  const shown = `${label} ${typed}${rule.unit ? ` ${rule.unit}` : ""}`;
  if (rule.integer && !Number.isInteger(value)) return { problem: `${shown}, needs a whole number` };
  if (rule.min !== undefined && rule.max !== undefined && (value < rule.min || value > rule.max)) {
    return { problem: `${shown}, needs ${rule.min} to ${rule.max}` };
  }
  if (rule.above !== undefined && value <= rule.above) return { problem: `${shown}, needs > ${rule.above}` };
  if (rule.min !== undefined && value < rule.min) return { problem: `${shown}, needs ≥ ${rule.min}` };
  if (rule.max !== undefined && value > rule.max) return { problem: `${shown}, needs ≤ ${rule.max}` };
  return { value };
}

// Numbers, sizes and times as the Atlas page writes them. Fixed decimals keep
// the columns of a table aligned; a negative value has a true minus sign, and
// a rounded value never reads as "−0.0".

const MINUS = "−";

/** value with exactly `digits` decimals. */
export function fixed(value: number, digits: number): string {
  const text = Math.abs(value).toFixed(digits);
  return value < 0 && Number(text) !== 0 ? `${MINUS}${text}` : text;
}

/**
 * A caliper value: to the micrometre the service stores, without trailing
 * zeros past the hundredths (25.04, 25.00, 33.367).
 */
export function caliper(value: number): string {
  return fixed(value, 3).replace(/(\.\d\d\d*?)0+$/, "$1");
}

/** "+0.16 %": the sign always shown, so a size above nominal reads differently from one below. */
export function signedPercent(value: number, digits = 2): string {
  const text = fixed(value, digits);
  return `${value > 0 && Number(text) !== 0 ? "+" : ""}${text} %`;
}

/** "1 image", "3 images". */
export function count(value: number, one: string, many = `${one}s`): string {
  return `${value} ${value === 1 ? one : many}`;
}

/** "245.3 MB", in decimal megabytes as file managers show them. */
export function megabytes(bytes: number): string {
  return `${fixed(bytes / 1e6, 1)} MB`;
}

function pad(value: number): string {
  return String(value).padStart(2, "0");
}

/** An ISO 8601 time as "2026-10-06 14:25" in the reader's time zone; the input as it is if it is not a time. */
export function localTime(iso: string): string {
  const time = new Date(iso);
  if (Number.isNaN(time.getTime())) return iso;
  const date = `${time.getFullYear()}-${pad(time.getMonth() + 1)}-${pad(time.getDate())}`;
  return `${date} ${pad(time.getHours())}:${pad(time.getMinutes())}`;
}

/** "1080×1920" */
export function size(width: number | null, height: number | null): string {
  return width === null || height === null ? "size unknown" : `${width}×${height}`;
}

/** The first letter in upper case: the service writes its reasons in lower case. */
export function sentence(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

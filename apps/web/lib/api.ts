// HTTP access to the perception service. Every call goes through here, so a
// failure reads the same wherever the page shows it: the service's own words
// when it answered, a plain fact when it did not.

const DEFAULT_API_URL = "http://localhost:8000";
const DEFAULT_TIMEOUT_MS = 15_000;

/** Without trailing slashes, so a value written as "https://api.example.com/" still reaches /health. */
export const API_URL = (process.env.NEXT_PUBLIC_API_URL?.trim() || DEFAULT_API_URL).replace(/\/+$/, "");

/** A call that failed. status is the HTTP status, or null when no answer came at all. */
export class ApiError extends Error {
  readonly status: number | null;

  constructor(status: number | null, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export type ApiInit = RequestInit & { timeoutMs?: number };

function unreachable(): ApiError {
  return new ApiError(null, `Cannot reach the perception service at ${API_URL}`);
}

function timedOut(timeoutMs: number): ApiError {
  return new ApiError(null, `No answer within ${timeoutMs / 1000} s`);
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return undefined;
  }
}

/** One entry of FastAPI's 422 list: the field, then what is wrong with it. */
function issueText(issue: unknown): string | null {
  if (!isObject(issue) || typeof issue.msg !== "string") return null;
  // Pydantic prefixes the message of a model validator with the exception type.
  const message = issue.msg.replace(/^Value error, /, "");
  // The first element of loc names the part of the request (body, path, query).
  const where = (Array.isArray(issue.loc) ? issue.loc.slice(1) : [])
    .map((part, index) => (typeof part === "number" ? `[${part}]` : `${index > 0 ? "." : ""}${String(part)}`))
    .join("");
  return where ? `${where}: ${message}` : message;
}

/** The service's explanation of an error: FastAPI's "detail", a string or a validation list. */
function failure(status: number, statusText: string, text: string): ApiError {
  const body = parseJson(text);
  const detail = isObject(body) ? body.detail : undefined;
  if (typeof detail === "string" && detail.trim()) return new ApiError(status, detail);
  if (Array.isArray(detail)) {
    const issues = detail.map(issueText).filter((issue): issue is string => issue !== null);
    if (issues.length > 0) return new ApiError(status, issues.join("; "));
  }
  return new ApiError(status, statusText ? `HTTP ${status} ${statusText}` : `HTTP ${status}`);
}

function notJson(url: string, status: number): ApiError {
  return new ApiError(status, `The answer from ${url} is not JSON`);
}

/**
 * fetch() for a URL of the perception service, with a time limit that also
 * covers reading the body. Resolves with what read() makes of a 2xx answer and
 * rejects with an ApiError otherwise. A caller's own abort rejects with the
 * signal's reason, as fetch does, so it can be told apart from a failure.
 */
export async function apiFetch<T>(url: string, init: ApiInit, read: (response: Response) => Promise<T>): Promise<T> {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, signal, ...rest } = init;
  const timeout = AbortSignal.timeout(timeoutMs);
  try {
    const response = await fetch(url, { ...rest, signal: signal ? AbortSignal.any([signal, timeout]) : timeout });
    if (!response.ok) throw failure(response.status, response.statusText, await response.text());
    return await read(response);
  } catch (error) {
    if (error instanceof ApiError || signal?.aborted) throw error;
    throw timeout.aborted ? timedOut(timeoutMs) : unreachable();
  }
}

/** A JSON call to the perception service; path starts with "/". */
export function apiJson<T>(path: string, init: ApiInit = {}): Promise<T> {
  const url = `${API_URL}${path}`;
  return apiFetch(url, init, async (response) => {
    const body = parseJson(await response.text());
    if (body === undefined) throw notJson(url, response.status);
    return body as T;
  });
}

/**
 * POST a form and read the JSON answer, reporting the upload's progress as a
 * fraction, which fetch cannot do. Fails like apiJson.
 */
export function apiUpload<T>(
  path: string,
  form: FormData,
  options: { timeoutMs?: number; onProgress?: (fraction: number) => void } = {},
): Promise<T> {
  const { timeoutMs = DEFAULT_TIMEOUT_MS, onProgress } = options;
  const url = `${API_URL}${path}`;
  return new Promise<T>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", url);
    xhr.timeout = timeoutMs;
    if (onProgress) {
      // An upload listener makes the browser ask the service first (a CORS
      // preflight), so it is only added when someone wants the progress.
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable && event.total > 0) onProgress(event.loaded / event.total);
      };
      xhr.upload.onload = () => onProgress(1);
    }
    xhr.onload = () => {
      if (xhr.status < 200 || xhr.status >= 300) {
        reject(failure(xhr.status, xhr.statusText, xhr.responseText));
        return;
      }
      const body = parseJson(xhr.responseText);
      if (body === undefined) reject(notJson(url, xhr.status));
      else resolve(body as T);
    };
    xhr.onerror = () => reject(unreachable());
    xhr.ontimeout = () => reject(timedOut(timeoutMs));
    xhr.send(form);
  });
}

/** What went wrong, in words for the page, whatever was thrown. */
export function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message || error.name;
  return String(error);
}

/** Where the service serves one image of a view set. */
export function imageUrl(set: string, file: string): string {
  return `${API_URL}/view-sets/${encodeURIComponent(set)}/images/${encodeURIComponent(file)}`;
}

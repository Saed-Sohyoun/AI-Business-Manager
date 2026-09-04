/**
 * Central HTTP client for owner APIs.
 *
 * Prefer cookie session + CSRF. VITE_OWNER_API_KEY is an emergency/dev
 * fallback only — never require it for live session auth.
 */

const DEFAULT_TIMEOUT_MS = 30_000;
const CSRF_STORAGE_KEY = "bos_csrf";
const MUTATING = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export class ApiClientError extends Error {
  /**
   * @param {string} message
   * @param {{ status?: number, code?: string, details?: Record<string, unknown>, requestId?: string|null }} [meta]
   */
  constructor(message, meta = {}) {
    super(message);
    this.name = "ApiClientError";
    this.status = meta.status ?? 0;
    this.code = meta.code ?? "client_error";
    this.details = meta.details ?? {};
    this.requestId = meta.requestId ?? null;
  }
}

export function getApiBaseUrl() {
  const raw = import.meta.env.VITE_API_BASE_URL || "/api/v1";
  return String(raw).replace(/\/$/, "");
}

export function hasOwnerApiKeyConfigured() {
  const key = import.meta.env.VITE_OWNER_API_KEY;
  return Boolean(key && String(key).trim());
}

export function getStoredCsrfToken() {
  try {
    return sessionStorage.getItem(CSRF_STORAGE_KEY) || "";
  } catch {
    return "";
  }
}

export function setStoredCsrfToken(token) {
  try {
    if (token) sessionStorage.setItem(CSRF_STORAGE_KEY, String(token));
    else sessionStorage.removeItem(CSRF_STORAGE_KEY);
  } catch {
    /* ignore */
  }
}

export function clearStoredCsrfToken() {
  setStoredCsrfToken("");
}

export function getOwnerAuthHeaders() {
  const headers = {};
  const key = import.meta.env.VITE_OWNER_API_KEY;
  if (key && String(key).trim()) {
    headers["X-Owner-API-Key"] = String(key).trim();
  }
  const resolver = import.meta.env.VITE_OWNER_RESOLVER || "owner";
  headers["X-Owner-Resolver"] = String(resolver).trim();
  return headers;
}

/**
 * @param {string} path
 * @param {{
 *   method?: string,
 *   body?: unknown,
 *   timeoutMs?: number,
 *   headers?: Record<string, string>,
 *   signal?: AbortSignal,
 * }} [options]
 */
export async function apiRequest(path, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const url = `${getApiBaseUrl()}${path.startsWith("/") ? path : `/${path}`}`;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  const onExternalAbort = () => controller.abort();
  if (options.signal) {
    if (options.signal.aborted) controller.abort();
    else options.signal.addEventListener("abort", onExternalAbort, { once: true });
  }

  const headers = {
    Accept: "application/json",
    "Content-Type": "application/json",
    ...getOwnerAuthHeaders(),
    ...(options.headers || {}),
  };

  if (MUTATING.has(method)) {
    const csrf = getStoredCsrfToken();
    if (csrf) headers["X-CSRF-Token"] = csrf;
  }

  try {
    const response = await fetch(url, {
      method,
      credentials: "include",
      signal: controller.signal,
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });

    const requestId = response.headers.get("X-Request-ID");
    let payload = null;
    const text = await response.text();
    if (text) {
      try {
        payload = JSON.parse(text);
      } catch {
        throw new ApiClientError("Invalid JSON response", {
          status: response.status,
          code: "invalid_json",
          requestId,
        });
      }
    }

    if (!response.ok) {
      if (response.status === 401) {
        clearStoredCsrfToken();
      }
      const err = payload?.error || {};
      throw new ApiClientError(err.message || `HTTP ${response.status}`, {
        status: response.status,
        code: err.code || "http_error",
        details: err.details || {},
        requestId: err.request_id || requestId,
      });
    }

    return payload?.data !== undefined ? payload.data : payload;
  } catch (err) {
    if (err instanceof ApiClientError) throw err;
    if (err?.name === "AbortError") {
      throw new ApiClientError("Request timed out", { code: "timeout" });
    }
    throw new ApiClientError(err?.message || "Network error", { code: "network_error" });
  } finally {
    clearTimeout(timer);
    if (options.signal) {
      options.signal.removeEventListener("abort", onExternalAbort);
    }
  }
}

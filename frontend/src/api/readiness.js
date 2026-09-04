/**
 * Read-only pilot readiness helpers for the owner UI.
 * Mapping only — never unlocks production or exposes secrets.
 */

const FAILING_STATUSES = new Set([
  "fail",
  "failed",
  "not_ready",
  "blocked",
  "error",
  "unset",
  "missing",
  "false",
  "no",
]);

/**
 * @param {unknown} checks
 * @returns {Array<{ name?: string, status?: string, ok?: boolean, passed?: boolean }>}
 */
function normalizeChecks(checks) {
  if (!checks) return [];
  if (Array.isArray(checks)) return checks.filter((c) => c && typeof c === "object");
  if (typeof checks === "object") {
    return Object.entries(checks).map(([name, value]) => {
      if (value && typeof value === "object") {
        return { name, ...value };
      }
      if (typeof value === "boolean") {
        return { name, ok: value, status: value ? "pass" : "fail" };
      }
      return { name, status: String(value) };
    });
  }
  return [];
}

/**
 * @param {{ name?: string, status?: string, state?: string, result?: string, ok?: boolean, passed?: boolean }} check
 */
export function isFailingCheck(check) {
  if (!check || typeof check !== "object") return true;
  if (typeof check.ok === "boolean") return !check.ok;
  if (typeof check.passed === "boolean") return !check.passed;
  const st = String(check.status || check.state || check.result || "").toLowerCase();
  if (!st) return false;
  return FAILING_STATUSES.has(st);
}

/**
 * Summarize GET /owner/readiness for a restrained badge.
 *
 * @param {unknown} payload
 * @returns {{
 *   overall: "READY_FOR_PILOT" | "NOT_READY",
 *   ready: boolean,
 *   label: string,
 *   failingCount: number,
 *   variant: "success" | "warning",
 * } | null}
 */
export function summarizeReadiness(payload) {
  if (!payload || typeof payload !== "object") return null;

  const raw = String(payload.overall || "").toUpperCase();
  if (!raw) return null;

  const ready = raw === "READY_FOR_PILOT";
  const overall = ready ? "READY_FOR_PILOT" : "NOT_READY";

  let failingCount = 0;
  if (typeof payload.failing_count === "number") {
    failingCount = Math.max(0, payload.failing_count);
  } else if (typeof payload.failed_checks === "number") {
    failingCount = Math.max(0, payload.failed_checks);
  } else {
    failingCount = normalizeChecks(payload.checks).filter(isFailingCheck).length;
  }

  if (ready) failingCount = 0;

  return {
    overall,
    ready,
    label: overall,
    failingCount,
    variant: ready ? "success" : "warning",
  };
}

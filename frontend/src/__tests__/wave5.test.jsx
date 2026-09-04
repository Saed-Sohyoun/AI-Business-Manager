/**
 * Wave 5 — readiness mapping and related error humanization.
 */

import { describe, expect, it } from "vitest";
import { humanizeApiError } from "../api/errors.js";
import { ApiClientError, hasOwnerApiKeyConfigured } from "../api/client.js";
import { isFailingCheck, summarizeReadiness } from "../api/readiness.js";
import * as ownerApi from "../api/owner.js";

describe("Wave 5 readiness mapping", () => {
  it("maps READY_FOR_PILOT with zero failing checks", () => {
    const summary = summarizeReadiness({
      overall: "READY_FOR_PILOT",
      checks: [
        { name: "database", status: "pass" },
        { name: "n8n", status: "pass" },
      ],
    });
    expect(summary).toEqual({
      overall: "READY_FOR_PILOT",
      ready: true,
      label: "READY_FOR_PILOT",
      failingCount: 0,
      variant: "success",
    });
  });

  it("maps NOT_READY and counts failing checks from an array", () => {
    const summary = summarizeReadiness({
      overall: "NOT_READY",
      checks: [
        { name: "database", status: "pass" },
        { name: "concurrency", status: "blocked" },
        { name: "backup_status", ok: false },
        { name: "n8n", status: "unset" },
      ],
    });
    expect(summary?.ready).toBe(false);
    expect(summary?.label).toBe("NOT_READY");
    expect(summary?.failingCount).toBe(3);
    expect(summary?.variant).toBe("warning");
  });

  it("counts failing checks from an object map", () => {
    const summary = summarizeReadiness({
      overall: "NOT_READY",
      checks: {
        database: { status: "pass" },
        production_locked: true,
        concurrency_suite: "unset",
        n8n: false,
      },
    });
    expect(summary?.failingCount).toBe(2);
  });

  it("treats unknown overall as NOT_READY without inventing unlock", () => {
    const summary = summarizeReadiness({ overall: "DEGRADED", checks: [] });
    expect(summary?.overall).toBe("NOT_READY");
    expect(summary?.ready).toBe(false);
  });

  it("isFailingCheck recognizes common fail states", () => {
    expect(isFailingCheck({ status: "pass" })).toBe(false);
    expect(isFailingCheck({ status: "fail" })).toBe(true);
    expect(isFailingCheck({ ok: true })).toBe(false);
    expect(isFailingCheck({ passed: false })).toBe(true);
  });

  it("returns null for empty payload", () => {
    expect(summarizeReadiness(null)).toBeNull();
    expect(summarizeReadiness({})).toBeNull();
  });
});

describe("Wave 5 readiness-related errors", () => {
  it("humanizes NOT_READY and NICHE_NOT_APPROVED without secrets", () => {
    const notReady = humanizeApiError(
      new ApiClientError("not ready", {
        status: 403,
        code: "forbidden",
        details: { code: "NOT_READY" },
      }),
    );
    expect(notReady.title).toMatch(/not ready/i);
    expect(JSON.stringify(notReady)).not.toMatch(/api[_-]?key|secret|password/i);

    const niche = humanizeApiError(
      new ApiClientError("niche", {
        status: 422,
        code: "validation_error",
        details: { code: "NICHE_NOT_APPROVED" },
      }),
    );
    expect(niche.title).toMatch(/niche/i);
  });
});

describe("Wave 5 owner API helpers", () => {
  it("exports readiness and pilot helpers", () => {
    expect(typeof ownerApi.getReadiness).toBe("function");
    expect(typeof ownerApi.getPilotStatus).toBe("function");
    expect(typeof ownerApi.getPilotExperiment).toBe("function");
  });

  it("does not require VITE_OWNER_API_KEY for session path", () => {
    // Emergency key is optional; session auth uses cookies + CSRF.
    expect(typeof hasOwnerApiKeyConfigured).toBe("function");
    expect(hasOwnerApiKeyConfigured()).toBe(false);
  });
});

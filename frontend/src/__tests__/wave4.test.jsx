/**
 * Wave 4 — error mapping and session-auth client helpers.
 */

import { describe, expect, it, beforeEach, afterEach } from "vitest";
import { humanizeApiError } from "../api/errors.js";
import {
  ApiClientError,
  clearStoredCsrfToken,
  getStoredCsrfToken,
  setStoredCsrfToken,
} from "../api/client.js";

describe("Wave 4 error mapping", () => {
  it("maps CIRCUIT_OPEN from details.code", () => {
    const err = new ApiClientError("Search provider circuit open", {
      status: 503,
      code: "service_unavailable",
      details: { code: "CIRCUIT_OPEN" },
    });
    const h = humanizeApiError(err);
    expect(h.title).toBe("A provider is temporarily unavailable");
    expect(h.description).toMatch(/circuit/i);
    expect(h.code).toBe("CIRCUIT_OPEN");
  });

  it("maps SYSTEM_PAUSED and AUTH_REQUIRED", () => {
    expect(
      humanizeApiError(
        new ApiClientError("paused", {
          status: 403,
          code: "forbidden",
          details: { code: "SYSTEM_PAUSED" },
        }),
      ).title,
    ).toMatch(/paused/i);

    expect(
      humanizeApiError(
        new ApiClientError("auth", {
          status: 401,
          code: "unauthorized",
          details: { code: "AUTH_REQUIRED" },
        }),
      ).title,
    ).toMatch(/sign-in/i);
  });
});

describe("CSRF sessionStorage helpers", () => {
  beforeEach(() => {
    sessionStorage.clear();
  });
  afterEach(() => {
    sessionStorage.clear();
  });

  it("stores and clears bos_csrf", () => {
    setStoredCsrfToken("tok-abc");
    expect(getStoredCsrfToken()).toBe("tok-abc");
    expect(sessionStorage.getItem("bos_csrf")).toBe("tok-abc");
    clearStoredCsrfToken();
    expect(getStoredCsrfToken()).toBe("");
  });
});

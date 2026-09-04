/**
 * Human-readable error mapping for owner UI.
 * Internal codes stay in Advanced details only.
 */

import { ApiClientError } from "./client.js";

/** @type {Record<string, { title: string, description: string }>} */
const DETAIL_CODE_MESSAGES = {
  SYSTEM_PAUSED: {
    title: "Operations are paused",
    description:
      "Resume AI operations in System controls before starting new work. Your data has not been changed.",
  },
  SAFE_MODE_ACTIVE: {
    title: "Safe Mode is active",
    description:
      "External actions are restricted until Safe Mode is cleared. Your data has not been changed.",
  },
  CIRCUIT_OPEN: {
    title: "A provider is temporarily unavailable",
    description:
      "The system opened a protective circuit. Wait a moment and try again — committed work was kept.",
  },
  LIMIT_REACHED: {
    title: "Daily limit reached",
    description:
      "Pilot limits cap how much work can run today. Try again tomorrow or review limits in settings.",
  },
  RATE_LIMITED: {
    title: "Too many requests",
    description: "Please wait a moment and try again. Your data has not been changed.",
  },
  AUTH_REQUIRED: {
    title: "Sign-in required",
    description: "Sign in to continue, or check your local owner credentials.",
  },
  BUDGET_EXCEEDED: {
    title: "Budget limit reached",
    description:
      "Spending is paused until the daily budget resets or is adjusted. Your data has not been changed.",
  },
  NOT_READY: {
    title: "Not ready for pilot",
    description:
      "One or more readiness checks failed. Review System controls — nothing has been unlocked.",
  },
  PILOT_NOT_READY: {
    title: "Not ready for pilot",
    description:
      "Pilot launch prerequisites are incomplete. Production remains locked.",
  },
  READINESS_UNAVAILABLE: {
    title: "Readiness check unavailable",
    description: "Could not load readiness status. Try again in a moment.",
  },
  EXPERIMENT_NOT_FOUND: {
    title: "No pilot experiment",
    description: "There is no active pilot experiment configuration yet.",
  },
  NICHE_NOT_APPROVED: {
    title: "Niche not approved",
    description:
      "Owner approval of the selected niche is required before the experiment can activate.",
  },
  EXPERIMENT_NICHE_REQUIRED: {
    title: "Niche not approved",
    description:
      "Owner approval of the selected niche is required before the experiment can activate.",
  },
};

/**
 * @param {unknown} err
 * @returns {{ title: string, description: string, code?: string, status?: number }}
 */
export function humanizeApiError(err) {
  if (!(err instanceof ApiClientError) && !(err && typeof err === "object")) {
    return {
      title: "Something went wrong",
      description: "Your data has not been changed. Try again in a moment.",
    };
  }

  const status = err.status ?? 0;
  const code = err.code || "";
  const detailCode =
    (err.details && typeof err.details === "object" && err.details.code
      ? String(err.details.code)
      : "") ||
    (DETAIL_CODE_MESSAGES[code] ? code : "");

  if (detailCode && DETAIL_CODE_MESSAGES[detailCode]) {
    const mapped = DETAIL_CODE_MESSAGES[detailCode];
    return {
      title: mapped.title,
      description: mapped.description,
      code: detailCode || code,
      status,
    };
  }

  if (status === 401 || code === "unauthorized" || code === "AUTH_REQUIRED") {
    return {
      title: "Sign-in required",
      description: "Sign in to continue, or check your local owner credentials.",
      code,
      status,
    };
  }
  if (status === 403 || code === "forbidden") {
    return {
      title: "Action not allowed",
      description:
        err.message ||
        "This action is blocked by system controls, Safe Mode, or your permissions. Your data has not been changed.",
      code,
      status,
    };
  }
  if (status === 404 || code === "not_found") {
    return {
      title: "Not found",
      description: "That item is no longer available. It may have expired or been resolved.",
      code,
      status,
    };
  }
  if (status === 409 || code === "conflict") {
    return {
      title: "Already decided",
      description:
        err.message ||
        "This item changed before your action completed. Refresh to see the current status.",
      code,
      status,
    };
  }
  if (status === 422 || code === "validation_error") {
    return {
      title: "Cannot complete this action",
      description: err.message || "The request was not valid (for example, an expired approval).",
      code,
      status,
    };
  }
  if (status === 429 || code === "rate_limit" || code === "RATE_LIMITED") {
    return {
      title: "Too many requests",
      description: "Please wait a moment and try again.",
      code,
      status,
    };
  }
  if (status === 503) {
    return {
      title: "Temporarily unavailable",
      description: "The service is busy. We'll be ready shortly — try again.",
      code,
      status,
    };
  }
  if (code === "timeout") {
    return {
      title: "Request timed out",
      description: "The server took too long to respond. Your data has not been changed.",
      code,
      status,
    };
  }
  if (code === "network_error" || status === 0) {
    return {
      title: "Connection problem",
      description: "We could not reach the server. Check your connection and try again.",
      code,
      status,
    };
  }

  return {
    title: "We couldn't complete that",
    description: err.message || "Your data has not been changed.",
    code,
    status,
  };
}

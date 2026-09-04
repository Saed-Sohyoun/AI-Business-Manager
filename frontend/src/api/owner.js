/**
 * Owner control-plane API client.
 */

import { apiRequest } from "./client.js";

function querySuffix(params = {}) {
  const q = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") return;
    q.set(key, String(value));
  });
  const s = q.toString();
  return s ? `?${s}` : "";
}

// ——— Auth ———

export function login(body, options = {}) {
  return apiRequest("/owner/auth/login", { method: "POST", body, ...options });
}

export function logout(options = {}) {
  return apiRequest("/owner/auth/logout", { method: "POST", body: {}, ...options });
}

export function getMe(options = {}) {
  return apiRequest("/owner/auth/me", options);
}

// ——— Approvals ———

export function listApprovals(params = {}, options = {}) {
  return apiRequest(`/owner/approvals${querySuffix(params)}`, options);
}

export function getApproval(approvalId, options = {}) {
  return apiRequest(`/owner/approvals/${approvalId}`, options);
}

export function approveApproval(approvalId, body = {}, options = {}) {
  return apiRequest(`/owner/approvals/${approvalId}/approve`, {
    method: "POST",
    body,
    ...options,
  });
}

export function rejectApproval(approvalId, body = {}, options = {}) {
  return apiRequest(`/owner/approvals/${approvalId}/reject`, {
    method: "POST",
    body,
    ...options,
  });
}

export function cancelApproval(approvalId, body = {}, options = {}) {
  return apiRequest(`/owner/approvals/${approvalId}/cancel`, {
    method: "POST",
    body,
    ...options,
  });
}

// ——— Readiness / pilot (Wave 5 — read-only; does not unlock production) ———

export function getReadiness(options = {}) {
  return apiRequest("/owner/readiness", options);
}

export function getPilotStatus(options = {}) {
  return apiRequest("/owner/pilot/status", options);
}

export function getPilotExperiment(options = {}) {
  return apiRequest("/owner/pilot/experiment", options);
}

// ——— System ———

export function getSystemStatus(options = {}) {
  return apiRequest("/owner/system/status", options);
}

export function pauseAll(body = {}, options = {}) {
  return apiRequest("/owner/system/pause-all", { method: "POST", body, ...options });
}

export function pauseOutbound(body = {}, options = {}) {
  return apiRequest("/owner/system/pause-outbound", { method: "POST", body, ...options });
}

export function resumeOutbound(body = {}, options = {}) {
  return apiRequest("/owner/system/resume-outbound", { method: "POST", body, ...options });
}

export function pauseSpending(body = {}, options = {}) {
  return apiRequest("/owner/system/pause-spending", { method: "POST", body, ...options });
}

export function resumeSpending(body = {}, options = {}) {
  return apiRequest("/owner/system/resume-spending", { method: "POST", body, ...options });
}

export function pauseAi(body = {}, options = {}) {
  return apiRequest("/owner/system/pause-ai", { method: "POST", body, ...options });
}

export function resumeAi(body = {}, options = {}) {
  return apiRequest("/owner/system/resume-ai", { method: "POST", body, ...options });
}

export function pauseBrowser(body = {}, options = {}) {
  return apiRequest("/owner/system/pause-browser", { method: "POST", body, ...options });
}

export function resumeBrowser(body = {}, options = {}) {
  return apiRequest("/owner/system/resume-browser", { method: "POST", body, ...options });
}

export function clearSafeMode(body = {}, options = {}) {
  return apiRequest("/owner/system/clear-safe-mode", { method: "POST", body, ...options });
}

export function enterSafeMode(body = {}, options = {}) {
  return apiRequest("/owner/system/enter-safe-mode", { method: "POST", body, ...options });
}

// ——— Dashboard / work / alerts ———

export function getDashboardSummary(options = {}) {
  return apiRequest("/owner/dashboard/summary", options);
}

export function getActiveWork(params = {}, options = {}) {
  return apiRequest(`/owner/work/active${querySuffix(params)}`, options);
}

export function listAlerts(params = {}, options = {}) {
  return apiRequest(`/owner/alerts${querySuffix(params)}`, options);
}

export function listSecurityEvents(params = {}, options = {}) {
  return apiRequest(`/owner/security-events${querySuffix(params)}`, options);
}

// ——— Commands / executions ———

export function findOpportunities(body = {}, options = {}) {
  return apiRequest("/owner/commands/find-opportunities", {
    method: "POST",
    body,
    ...options,
  });
}

export function getExecution(executionId, options = {}) {
  return apiRequest(`/owner/executions/${executionId}`, options);
}

export function listExecutions(params = {}, options = {}) {
  return apiRequest(`/owner/executions${querySuffix(params)}`, options);
}

export function cancelExecution(executionId, body = {}, options = {}) {
  return apiRequest(`/owner/executions/${executionId}/cancel`, {
    method: "POST",
    body,
    ...options,
  });
}

// ——— Catalogs ———

export function listOpportunities(params = {}, options = {}) {
  return apiRequest(`/owner/opportunities${querySuffix(params)}`, options);
}

export function getOpportunity(opportunityId, options = {}) {
  return apiRequest(`/owner/opportunities/${opportunityId}`, options);
}

export function listCustomers(params = {}, options = {}) {
  return apiRequest(`/owner/customers${querySuffix(params)}`, options);
}

export function getCustomer(customerId, options = {}) {
  return apiRequest(`/owner/customers/${customerId}`, options);
}

export function listReports(params = {}, options = {}) {
  return apiRequest(`/owner/reports${querySuffix(params)}`, options);
}

export function getReport(reportId, options = {}) {
  return apiRequest(`/owner/reports/${reportId}`, options);
}

export function generateReport(body = {}, options = {}) {
  return apiRequest("/owner/reports/generate", {
    method: "POST",
    body,
    ...options,
  });
}

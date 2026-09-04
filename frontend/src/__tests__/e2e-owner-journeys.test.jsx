/**
 * Lightweight E2E-style owner journey tests (mocked API).
 * Full browser E2E against a running backend is deferred to Wave 4 tooling.
 */

import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { DataModeProvider } from "../context/DataModeContext.jsx";
import { ToastProvider } from "../hooks/useToast.jsx";
import { OverviewPage } from "../pages/OverviewPage.jsx";
import { ApprovalsPage } from "../pages/ApprovalsPage.jsx";
import { SystemControlsPage } from "../pages/SystemControlsPage.jsx";
import * as ownerApi from "../api/owner.js";

vi.mock("../api/owner.js", () => ({
  getDashboardSummary: vi.fn(),
  getActiveWork: vi.fn(),
  listAlerts: vi.fn(),
  getSystemStatus: vi.fn(),
  getReadiness: vi.fn().mockResolvedValue(null),
  listApprovals: vi.fn(),
  approveApproval: vi.fn(),
  rejectApproval: vi.fn(),
  pauseOutbound: vi.fn(),
  resumeOutbound: vi.fn(),
  pauseAll: vi.fn(),
  pauseAi: vi.fn(),
  resumeAi: vi.fn(),
  pauseSpending: vi.fn(),
  resumeSpending: vi.fn(),
  pauseBrowser: vi.fn(),
  resumeBrowser: vi.fn(),
  clearSafeMode: vi.fn(),
}));

function app(initial = "/") {
  localStorage.setItem("bos.dataMode", "live");
  return render(
    <ToastProvider>
      <DataModeProvider>
        <MemoryRouter initialEntries={[initial]}>
          <Routes>
            <Route path="/" element={<OverviewPage />} />
            <Route path="/approvals" element={<ApprovalsPage />} />
            <Route path="/settings/system" element={<SystemControlsPage />} />
          </Routes>
        </MemoryRouter>
      </DataModeProvider>
    </ToastProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

describe("Owner journey: overview → approve", () => {
  it("shows pending attention then confirms approval", async () => {
    const user = userEvent.setup();
    ownerApi.getDashboardSummary.mockResolvedValue({
      current_goal: { title: "Grow pipeline", progress: 2, target: 10, unit: "tasks" },
      money: { revenue: "100.00", costs: "20.00", profit: "80.00", currency: "EUR" },
      pipeline: { companies: 5, qualified_leads: 2, opportunities: 1, customers: 0 },
      attention: { pending_approvals: 1, urgent_alerts: 0, blocked_work: 0 },
      team_activity: { researching: 1, auditing: 0, drafting: 0, delivering: 0, waiting: 0 },
      recent_activity: [{ title: "research: discover (succeeded)", at: new Date().toISOString() }],
    });
    ownerApi.getActiveWork.mockResolvedValue({ items: [] });
    ownerApi.listAlerts.mockResolvedValue({ items: [] });
    ownerApi.getSystemStatus.mockResolvedValue({
      system_mode: "normal",
      ai_operations: true,
      outbound: true,
      spending: true,
      browser_automation: true,
      pilot_mode: true,
      production_locked: true,
      pending_approvals: 1,
    });

    app("/");
    await waitFor(() => expect(screen.getByText("Grow pipeline")).toBeInTheDocument());
    expect(screen.getByText("1 decision needs your attention.")).toBeInTheDocument();

    const approval = {
      id: "ap-1",
      title: "Send outreach email",
      summary: "Email Acme",
      why: "Qualified",
      risk: "yellow",
      reversibility: "Review carefully",
      status: "pending",
      recommended_action: "Approve",
      advanced_details: {},
    };
    ownerApi.listApprovals.mockResolvedValue([approval]);
    ownerApi.approveApproval.mockResolvedValue({ ...approval, status: "approved" });

    app("/approvals");
    await waitFor(() => expect(screen.getByText("Send outreach email")).toBeInTheDocument());
    await user.click(screen.getAllByRole("button", { name: "Approve" })[0]);
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(ownerApi.approveApproval).toHaveBeenCalled());
  });
});

describe("Safety journey: pause outbound", () => {
  it("pauses outbound via confirmed control", async () => {
    const user = userEvent.setup();
    ownerApi.getSystemStatus.mockResolvedValue({
      system_mode: "normal",
      ai_operations: true,
      outbound: true,
      spending: true,
      browser_automation: true,
      pilot_mode: true,
      production_locked: true,
      pending_approvals: 0,
      active_runs: 0,
      current_budget_usage: "0",
      budget_limit: "3",
      currency: "EUR",
    });
    ownerApi.pauseOutbound.mockResolvedValue({});

    app("/settings/system");
    await waitFor(() => expect(screen.getByText("Outbound")).toBeInTheDocument());
    const pauseButtons = screen.getAllByRole("button", { name: "Pause" });
    await user.click(pauseButtons[1]); // outbound row
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Pause outbound" }));
    await waitFor(() => expect(ownerApi.pauseOutbound).toHaveBeenCalled());
  });
});

import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { DataModeProvider } from "../context/DataModeContext.jsx";
import { ToastProvider } from "../hooks/useToast.jsx";
import { OverviewPage } from "../pages/OverviewPage.jsx";
import { ApprovalsPage } from "../pages/ApprovalsPage.jsx";
import { SystemControlsPage } from "../pages/SystemControlsPage.jsx";
import { humanizeApiError } from "../api/errors.js";
import { ApiClientError } from "../api/client.js";
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
  pauseAll: vi.fn(),
  pauseOutbound: vi.fn(),
  resumeOutbound: vi.fn(),
  pauseAi: vi.fn(),
  resumeAi: vi.fn(),
  pauseSpending: vi.fn(),
  resumeSpending: vi.fn(),
  pauseBrowser: vi.fn(),
  resumeBrowser: vi.fn(),
  clearSafeMode: vi.fn(),
}));

function wrap(ui, { mode = "live" } = {}) {
  localStorage.setItem("bos.dataMode", mode === "live" ? "live" : "demo");
  return render(
    <ToastProvider>
      <DataModeProvider>
        <MemoryRouter>{ui}</MemoryRouter>
      </DataModeProvider>
    </ToastProvider>,
  );
}

const emptySummary = {
  current_goal: { title: "No active goal", progress: 0, target: 0, unit: "tasks" },
  money: { revenue: "0.00", costs: "0.00", profit: "0.00", currency: "EUR" },
  pipeline: { companies: 0, qualified_leads: 0, opportunities: 0, customers: 0 },
  attention: { pending_approvals: 0, urgent_alerts: 0, blocked_work: 0 },
  team_activity: { researching: 0, auditing: 0, drafting: 0, delivering: 0, waiting: 0 },
  recent_activity: [],
};

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

describe("humanizeApiError", () => {
  it("maps 401 without leaking secrets", () => {
    const err = new ApiClientError("Invalid owner credentials", {
      status: 401,
      code: "unauthorized",
    });
    const h = humanizeApiError(err);
    expect(h.title).toMatch(/sign-in/i);
    expect(JSON.stringify(h)).not.toMatch(/api[_-]?key|secret/i);
  });

  it("maps CIRCUIT_OPEN detail code", () => {
    const err = new ApiClientError("Provider unavailable", {
      status: 503,
      code: "service_unavailable",
      details: { code: "CIRCUIT_OPEN", provider: "tavily" },
    });
    const h = humanizeApiError(err);
    expect(h.title).toMatch(/temporarily unavailable/i);
    expect(h.description).toMatch(/circuit/i);
    expect(h.code).toBe("CIRCUIT_OPEN");
  });
});

describe("Overview live", () => {
  it("renders live summary", async () => {
    ownerApi.getDashboardSummary.mockResolvedValue(emptySummary);
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
      pending_approvals: 0,
    });

    wrap(<OverviewPage />, { mode: "live" });
    await waitFor(() => expect(screen.getByText("Current goal")).toBeInTheDocument());
    expect(screen.getByText("No active goal")).toBeInTheDocument();
    expect(screen.getByText("Revenue")).toBeInTheDocument();
  });

  it("shows error state and never demo metrics on failure", async () => {
    ownerApi.getDashboardSummary.mockRejectedValue(
      new ApiClientError("boom", { status: 503, code: "http_error" }),
    );
    ownerApi.getActiveWork.mockRejectedValue(new ApiClientError("boom", { status: 503 }));
    ownerApi.listAlerts.mockRejectedValue(new ApiClientError("boom", { status: 503 }));
    ownerApi.getSystemStatus.mockRejectedValue(new ApiClientError("boom", { status: 503 }));

    wrap(<OverviewPage />, { mode: "live" });
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(screen.queryByText(/Sample data for product walkthrough/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Berlin/i)).not.toBeInTheDocument();
  });

  it("demo mode shows sample data label", async () => {
    wrap(<OverviewPage />, { mode: "demo" });
    expect(await screen.findByText(/Sample data for product walkthrough/i)).toBeInTheDocument();
  });
});

describe("Approvals", () => {
  it("loads pending approvals and approves via API", async () => {
    const user = userEvent.setup();
    const approval = {
      id: "a1",
      title: "Send outreach email",
      summary: "Contact Acme",
      why: "Strong fit",
      affected_party: "ops@acme.example",
      risk: "yellow",
      reversibility: "Partially reversible",
      expires_at: null,
      status: "pending",
      recommended_action: "Approve",
      advanced_details: {},
    };
    ownerApi.listApprovals.mockResolvedValue([approval]);
    ownerApi.approveApproval.mockResolvedValue({ ...approval, status: "approved" });

    wrap(<ApprovalsPage />, { mode: "live" });
    await waitFor(() => expect(screen.getByText("Send outreach email")).toBeInTheDocument());

    const approveButtons = screen.getAllByRole("button", { name: "Approve" });
    await user.click(approveButtons[0]);
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Approve" }));

    await waitFor(() =>
      expect(ownerApi.approveApproval).toHaveBeenCalledWith("a1", expect.any(Object)),
    );
  });

  it("shows live error without demo fallback", async () => {
    ownerApi.listApprovals.mockRejectedValue(new ApiClientError("nope", { status: 401 }));
    wrap(<ApprovalsPage />, { mode: "live" });
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(screen.queryByText(/Sample decisions only/i)).not.toBeInTheDocument();
  });
});

describe("System controls", () => {
  it("requires live mode", async () => {
    wrap(<SystemControlsPage />, { mode: "demo" });
    expect(await screen.findByText(/System controls need live mode/i)).toBeInTheDocument();
  });

  it("can pause all with confirmation", async () => {
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
    ownerApi.pauseAll.mockResolvedValue({});

    wrap(<SystemControlsPage />, { mode: "live" });
    await waitFor(() => expect(screen.getByText("Pause all")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Pause all" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/Pause all AI activity/i)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Pause all" }));
    await waitFor(() => expect(ownerApi.pauseAll).toHaveBeenCalled());
  });
});

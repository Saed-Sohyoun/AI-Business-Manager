import { useCallback, useState } from "react";
import {
  Badge,
  Button,
  ConfirmationDialog,
  EmptyState,
  LiveError,
  Skeleton,
} from "../components";
import { useDataMode } from "../context/DataModeContext";
import { useAsyncResource } from "../hooks/useAsyncResource";
import { useToast } from "../hooks/useToast";
import * as ownerApi from "../api/owner.js";
import { humanizeApiError } from "../api/errors.js";
import { summarizeReadiness } from "../api/readiness.js";

function SwitchRow({ label, on, description, onPause, onResume, busy, disableResume }) {
  return (
    <div className="control-row">
      <div>
        <div className="control-row__label">{label}</div>
        {description ? <div className="control-row__desc">{description}</div> : null}
      </div>
      <div className="control-row__actions">
        <Badge variant={on ? "success" : "danger"}>{on ? "On" : "Off"}</Badge>
        {on ? (
          <Button size="sm" variant="secondary" disabled={busy} onClick={onPause}>
            Pause
          </Button>
        ) : (
          <Button
            size="sm"
            variant="secondary"
            disabled={busy || disableResume}
            onClick={onResume}
            title={disableResume ? "Clear Safe Mode first" : undefined}
          >
            Resume
          </Button>
        )}
      </div>
    </div>
  );
}

export function SystemControlsPage() {
  const { isDemo, isLive } = useDataMode();
  const { push } = useToast();
  const [confirm, setConfirm] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => ownerApi.getSystemStatus(), []);
  const { data: status, error, loading, reload } = useAsyncResource(load, {
    enabled: isLive,
    deps: [isLive],
  });

  /** Readiness is informational only — failures must not block system controls. */
  const loadReadiness = useCallback(async () => {
    try {
      return await ownerApi.getReadiness();
    } catch {
      return null;
    }
  }, []);
  const { data: readinessPayload } = useAsyncResource(loadReadiness, {
    enabled: isLive,
    deps: [isLive],
  });
  const readiness = summarizeReadiness(readinessPayload);

  if (isDemo) {
    return (
      <section className="panel">
        <EmptyState
          title="System controls need live mode"
          description="Switch to live data to pause or resume AI operations against the real backend. Demo mode never mutates system state."
        />
      </section>
    );
  }

  if (loading && !status) {
    return <Skeleton rows={6} />;
  }

  if (error) {
    return <LiveError error={error} onRetry={reload} resourceLabel="system status" />;
  }

  const safeMode = status.system_mode === "safe_mode";
  const paused = status.system_mode === "paused_by_owner";

  const runAction = async () => {
    if (!confirm) return;
    setBusy(true);
    try {
      await confirm.fn();
      push(confirm.successMessage, "success");
      setConfirm(null);
      reload();
    } catch (err) {
      const human = humanizeApiError(err);
      push(human.description || human.title, "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="stack">
      {safeMode ? (
        <section className="callout callout--warning">
          <h2 className="callout__title">Safety mode is active</h2>
          <p>
            External communication and spending are paused
            {status.safe_mode_reason ? ` — ${status.safe_mode_reason}` : "."}
          </p>
          <p className="muted">Viewing data and internal reporting remain available.</p>
          <Button
            variant="primary"
            disabled={busy}
            onClick={() =>
              setConfirm({
                title: "Clear Safe Mode?",
                description:
                  "Only clear Safe Mode when you understand why it activated. Outbound and spending may resume.",
                confirmLabel: "Clear Safe Mode",
                successMessage: "Safe Mode cleared.",
                fn: () => ownerApi.clearSafeMode({ reason: "Cleared by owner from dashboard" }),
              })
            }
          >
            Clear Safe Mode
          </Button>
        </section>
      ) : null}

      {paused ? (
        <section className="callout callout--danger">
          <h2 className="callout__title">Paused by owner</h2>
          <p>{status.pause_reason || "All AI activity switches are off."}</p>
          <Button
            variant="primary"
            disabled={busy}
            onClick={() =>
              setConfirm({
                title: "Resume AI operations?",
                description: "This re-enables AI operations. Outbound and spending follow their own switches.",
                confirmLabel: "Resume AI",
                successMessage: "AI operations resumed.",
                fn: () => ownerApi.resumeAi({ reason: "Resumed by owner" }),
              })
            }
          >
            Resume AI
          </Button>
        </section>
      ) : null}

      <section className="panel">
        <div className="panel__header">
          <h3 className="panel__title">System status</h3>
          <div className="panel__header-actions" style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
            {readiness ? (
              <Badge variant={readiness.variant} title="Read-only pilot readiness — does not unlock production">
                {readiness.ready
                  ? "READY_FOR_PILOT"
                  : readiness.failingCount > 0
                    ? `NOT_READY · ${readiness.failingCount} check${readiness.failingCount === 1 ? "" : "s"}`
                    : "NOT_READY"}
              </Badge>
            ) : null}
            <Badge variant="neutral">{status.system_mode}</Badge>
          </div>
        </div>
        <div className="panel__body">
          {readiness && !readiness.ready ? (
            <p className="muted" style={{ marginTop: 0 }}>
              Pilot readiness is incomplete
              {readiness.failingCount > 0
                ? ` (${readiness.failingCount} failing check${readiness.failingCount === 1 ? "" : "s"})`
                : ""}
              . This status is informational only and does not unlock production.
            </p>
          ) : null}
          <ul className="status-facts">
            <li>Pilot mode: {status.pilot_mode ? "Yes" : "No"}</li>
            <li>Production locked: {status.production_locked ? "Yes" : "No"}</li>
            <li>
              Budget today: {status.current_budget_usage} / {status.budget_limit}{" "}
              {status.currency || "EUR"}
            </li>
            <li>Pending approvals: {status.pending_approvals}</li>
            <li>Active runs: {status.active_runs}</li>
          </ul>
          <div className="filter-row" style={{ marginTop: "1rem" }}>
            <Button
              variant="danger"
              disabled={busy}
              onClick={() =>
                setConfirm({
                  title: "Pause all AI activity?",
                  description:
                    "This stops new AI work, outbound communication, spending, and browser automation. Running database transactions will not be corrupted.",
                  confirmLabel: "Pause all",
                  danger: true,
                  successMessage: "System paused.",
                  fn: () => ownerApi.pauseAll({ reason: "Owner pause-all from dashboard" }),
                })
              }
            >
              Pause all
            </Button>
          </div>
        </div>
      </section>

      <section className="panel">
        <div className="panel__header">
          <h3 className="panel__title">Operational switches</h3>
        </div>
        <div className="panel__body stack" style={{ gap: "0.75rem" }}>
          <SwitchRow
            label="AI operations"
            on={status.ai_operations}
            description="Research, audits, and new governed work"
            busy={busy}
            onPause={() =>
              setConfirm({
                title: "Pause AI operations?",
                description: "New research, audits, and manager orchestration will be blocked.",
                confirmLabel: "Pause AI",
                danger: true,
                successMessage: "AI operations paused.",
                fn: () => ownerApi.pauseAi({ reason: "Paused from dashboard" }),
              })
            }
            onResume={() =>
              setConfirm({
                title: "Resume AI operations?",
                description: "Governed AI work may start again (subject to other switches).",
                confirmLabel: "Resume AI",
                successMessage: "AI operations resumed.",
                fn: () => ownerApi.resumeAi({ reason: "Resumed from dashboard" }),
              })
            }
          />
          <SwitchRow
            label="Outbound"
            on={status.outbound}
            description="Email and external communication"
            busy={busy}
            disableResume={safeMode}
            onPause={() =>
              setConfirm({
                title: "Pause outbound?",
                description: "Approved emails still cannot send while outbound is off.",
                confirmLabel: "Pause outbound",
                danger: true,
                successMessage: "Outbound paused.",
                fn: () => ownerApi.pauseOutbound({ reason: "Paused from dashboard" }),
              })
            }
            onResume={() =>
              setConfirm({
                title: "Resume outbound?",
                description: "External communication may resume when AI operations allow.",
                confirmLabel: "Resume outbound",
                successMessage: "Outbound resumed.",
                fn: () => ownerApi.resumeOutbound({ reason: "Resumed from dashboard" }),
              })
            }
          />
          <SwitchRow
            label="Spending"
            on={status.spending}
            description="Paid operations and cost recording"
            busy={busy}
            disableResume={safeMode}
            onPause={() =>
              setConfirm({
                title: "Pause spending?",
                description: "Paid actions will be denied until spending is resumed.",
                confirmLabel: "Pause spending",
                danger: true,
                successMessage: "Spending paused.",
                fn: () => ownerApi.pauseSpending({ reason: "Paused from dashboard" }),
              })
            }
            onResume={() =>
              setConfirm({
                title: "Resume spending?",
                confirmLabel: "Resume spending",
                description: "Cost recording may resume within pilot limits.",
                successMessage: "Spending resumed.",
                fn: () => ownerApi.resumeSpending({ reason: "Resumed from dashboard" }),
              })
            }
          />
          <SwitchRow
            label="Browser automation"
            on={status.browser_automation}
            description="Website inspection for research and audits"
            busy={busy}
            onPause={() =>
              setConfirm({
                title: "Pause browser automation?",
                description: "Browser-based verification will be denied.",
                confirmLabel: "Pause browser",
                danger: true,
                successMessage: "Browser automation paused.",
                fn: () => ownerApi.pauseBrowser({ reason: "Paused from dashboard" }),
              })
            }
            onResume={() =>
              setConfirm({
                title: "Resume browser automation?",
                description: "Website inspection may resume when AI operations allow.",
                confirmLabel: "Resume browser",
                successMessage: "Browser automation resumed.",
                fn: () => ownerApi.resumeBrowser({ reason: "Resumed from dashboard" }),
              })
            }
          />
        </div>
      </section>

      <ConfirmationDialog
        open={Boolean(confirm)}
        busy={busy}
        title={confirm?.title || ""}
        description={confirm?.description || ""}
        confirmLabel={confirm?.confirmLabel || "Confirm"}
        danger={Boolean(confirm?.danger)}
        onCancel={() => !busy && setConfirm(null)}
        onConfirm={runAction}
      />
    </div>
  );
}

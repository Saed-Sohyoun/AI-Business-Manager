import { Link } from "react-router-dom";
import { useCallback } from "react";
import {
  ActivityTimeline,
  Badge,
  EmptyState,
  LiveError,
  MetricStrip,
  Skeleton,
  SkeletonMetrics,
} from "../components";
import { useDataMode } from "../context/DataModeContext";
import { useAsyncResource } from "../hooks/useAsyncResource";
import * as ownerApi from "../api/owner.js";
import { overview as demoOverview } from "../data/demo";
import { formatMoney, pct } from "../lib/format";
import { PageHeader } from "../layout/PageHeader";

function modeGreeting(systemStatus) {
  if (!systemStatus) return "Here is where your business stands.";
  if (systemStatus.system_mode === "paused_by_owner") {
    return "AI operations are paused. Review controls when you are ready to continue.";
  }
  if (systemStatus.system_mode === "safe_mode") {
    return "Safety mode is active — external communication and spending are restricted.";
  }
  if (systemStatus.pending_approvals > 0) {
    const n = systemStatus.pending_approvals;
    return `${n} decision${n === 1 ? "" : "s"} need${n === 1 ? "s" : ""} your attention.`;
  }
  return "Your digital team is running. Here is the latest picture.";
}

export function OverviewPage() {
  const { isDemo, isLive } = useDataMode();

  const loadLive = useCallback(async () => {
    const [summary, work, alerts, status] = await Promise.all([
      ownerApi.getDashboardSummary(),
      ownerApi.getActiveWork({ limit: 8 }),
      ownerApi.listAlerts({ limit: 8 }),
      ownerApi.getSystemStatus(),
    ]);
    return { summary, work, alerts, status };
  }, []);

  const { data, error, loading, reload } = useAsyncResource(loadLive, {
    enabled: isLive,
    deps: [isLive],
  });

  if (isDemo) {
    return <DemoOverview />;
  }

  if (loading && !data) {
    return (
      <div className="stack">
        <PageHeader eyebrow="Live" title="Overview" description="Loading your business summary…" />
        <SkeletonMetrics count={4} />
        <Skeleton rows={5} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="stack">
        <PageHeader
          eyebrow="Live"
          title="Overview"
          description="We could not load your live dashboard."
        />
        <LiveError error={error} onRetry={reload} resourceLabel="your overview" />
      </div>
    );
  }

  const summary = data.summary;
  const status = data.status;
  const alerts = data.alerts?.items || [];
  const workItems = data.work?.items || [];
  const currency = summary.money?.currency || "EUR";
  const goal = summary.current_goal || { title: "No active goal", progress: 0, target: 0, unit: "" };
  const progressPct = pct(goal.progress, goal.target || 0);

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Live"
        title="Overview"
        description={modeGreeting(status)}
        actions={
          <Link to="/approvals" className="btn btn--primary">
            Review decisions
          </Link>
        }
      />

      {status?.system_mode === "safe_mode" ? (
        <section className="callout callout--warning" aria-live="polite">
          <h2 className="callout__title">Safety mode is active</h2>
          <p>
            External communication and spending have been paused
            {status.safe_mode_reason ? ` because: ${status.safe_mode_reason}` : "."}
          </p>
          <p className="muted">
            Viewing data and reports still work. Clear Safe Mode from Settings when the issue is
            resolved.
          </p>
          <Link to="/settings/system" className="btn btn--secondary">
            Review system controls
          </Link>
        </section>
      ) : null}

      {status?.system_mode === "paused_by_owner" ? (
        <section className="callout callout--danger" aria-live="polite">
          <h2 className="callout__title">AI operations paused</h2>
          <p>{status.pause_reason || "New AI work, outbound, spending, and browser automation are off."}</p>
          <Link to="/settings/system" className="btn btn--secondary">
            Open controls
          </Link>
        </section>
      ) : null}

      <section className="objective-block" aria-labelledby="objective-heading">
        <div className="objective-block__label" id="objective-heading">
          Current goal
        </div>
        <p className="objective-block__goal">{goal.title}</p>
        <div className="objective-block__progress">
          <div className="progress">
            <div className="progress__meta">
              <span>
                {goal.progress} / {goal.target} {goal.unit}
              </span>
              <span className="mono">{progressPct}%</span>
            </div>
            <div
              className="progress__track"
              role="progressbar"
              aria-valuenow={goal.progress}
              aria-valuemin={0}
              aria-valuemax={goal.target || 0}
            >
              <div className="progress__fill" style={{ width: `${progressPct}%` }} />
            </div>
          </div>
        </div>
      </section>

      <MetricStrip
        items={[
          { label: "Revenue", value: formatMoney(summary.money.revenue, currency) },
          { label: "Costs", value: formatMoney(summary.money.costs, currency) },
          { label: "Profit", value: formatMoney(summary.money.profit, currency) },
          {
            label: "Needs attention",
            value: String(
              (summary.attention?.pending_approvals || 0) +
                (summary.attention?.urgent_alerts || 0) +
                (summary.attention?.blocked_work || 0),
            ),
          },
        ]}
      />

      <div className="grid-2">
        <div className="stack">
          <section className="panel">
            <div className="panel__header">
              <h3 className="panel__title">Pipeline</h3>
            </div>
            <div className="panel__body panel__body--flush">
              <table className="table">
                <thead>
                  <tr>
                    <th>Stage</th>
                    <th>Count</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td className="table__primary">Companies</td>
                    <td className="mono">{summary.pipeline.companies}</td>
                  </tr>
                  <tr>
                    <td className="table__primary">Qualified leads</td>
                    <td className="mono">{summary.pipeline.qualified_leads}</td>
                  </tr>
                  <tr>
                    <td className="table__primary">Opportunities</td>
                    <td className="mono">{summary.pipeline.opportunities}</td>
                  </tr>
                  <tr>
                    <td className="table__primary">Customers</td>
                    <td className="mono">{summary.pipeline.customers}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          <section className="panel">
            <div className="panel__header">
              <h3 className="panel__title">Needs attention</h3>
              <Link to="/approvals">Approvals</Link>
            </div>
            <div className="panel__body panel__body--flush">
              <table className="table">
                <tbody>
                  <tr>
                    <td>Pending approvals</td>
                    <td className="mono">{summary.attention.pending_approvals}</td>
                  </tr>
                  <tr>
                    <td>Urgent alerts</td>
                    <td className="mono">{summary.attention.urgent_alerts}</td>
                  </tr>
                  <tr>
                    <td>Blocked work</td>
                    <td className="mono">{summary.attention.blocked_work}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          <section className="panel">
            <div className="panel__header">
              <h3 className="panel__title">Alerts</h3>
            </div>
            <div className="panel__body">
              {alerts.length === 0 ? (
                <EmptyState
                  title="No alerts"
                  description="Operational alerts will appear here when something needs your attention."
                />
              ) : (
                <div className="alert-row">
                  {alerts.map((a) => (
                    <div key={a.id} className={`alert-item alert-item--${a.priority || "info"}`}>
                      <div>
                        <div className="alert-item__title">{a.title}</div>
                        <div className="alert-item__body">{a.body}</div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </section>
        </div>

        <div className="stack">
          <section className="panel">
            <div className="panel__header">
              <h3 className="panel__title">Your team is working on</h3>
              <Link to="/work">Work</Link>
            </div>
            <div className="panel__body">
              <ul className="team-activity">
                <li>
                  Researching <strong>{summary.team_activity.researching}</strong>
                </li>
                <li>
                  Auditing <strong>{summary.team_activity.auditing}</strong>
                </li>
                <li>
                  Drafting <strong>{summary.team_activity.drafting}</strong>
                </li>
                <li>
                  Delivering <strong>{summary.team_activity.delivering}</strong>
                </li>
                <li>
                  Waiting <strong>{summary.team_activity.waiting}</strong>
                </li>
              </ul>
              {workItems.length > 0 ? (
                <ul className="data-list" style={{ marginTop: "1rem" }}>
                  {workItems.slice(0, 5).map((w, i) => (
                    <li key={w.advanced_details?.agent_run_id || i} className="data-list__item">
                      <div>
                        <div className="data-list__title">{w.title}</div>
                        <div className="data-list__meta">
                          {w.status}
                          {w.total ? ` · ${w.progress}/${w.total}` : ""}
                          {w.needs_attention ? " · needs attention" : ""}
                        </div>
                      </div>
                      {w.needs_attention ? <Badge variant="warning">Attention</Badge> : null}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="muted" style={{ marginBottom: 0 }}>
                  No active work right now.
                </p>
              )}
            </div>
          </section>

          <section className="panel">
            <div className="panel__header">
              <h3 className="panel__title">Recent activity</h3>
            </div>
            <div className="panel__body">
              {(summary.recent_activity || []).length === 0 ? (
                <EmptyState
                  title="Nothing yet"
                  description="Activity appears here as your team completes research, audits, and outreach."
                />
              ) : (
                <ActivityTimeline
                  items={(summary.recent_activity || []).map((a, i) => ({
                    id: `ra-${i}`,
                    title: a.title,
                    detail: a.kind,
                    at: a.at,
                  }))}
                />
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

function DemoOverview() {
  const { objective, finance, pipeline, approvals, alerts, opportunities, activity } = demoOverview;
  return (
    <div className="stack">
      <PageHeader
        eyebrow="Demo"
        title="Overview"
        description="Sample data for product walkthrough. Switch to live data in the status strip when your API is configured."
        actions={
          <Link to="/approvals" className="btn btn--primary">
            Review decisions
          </Link>
        }
      />
      <section className="objective-block">
        <div className="objective-block__label">Current goal</div>
        <p className="objective-block__goal">{objective.goal}</p>
        <div className="progress">
          <div className="progress__meta">
            <span>
              {objective.current} / {objective.target} {objective.unit}
            </span>
            <span className="mono">{pct(objective.current, objective.target)}%</span>
          </div>
          <div className="progress__track" role="progressbar" aria-valuenow={objective.current}>
            <div
              className="progress__fill"
              style={{ width: `${pct(objective.current, objective.target)}%` }}
            />
          </div>
        </div>
      </section>
      <MetricStrip
        items={[
          { label: "Revenue", value: formatMoney(finance.revenue, finance.currency) },
          { label: "Costs", value: formatMoney(finance.costs, finance.currency) },
          { label: "Profit", value: formatMoney(finance.profit, finance.currency) },
          { label: "Pending decisions", value: String(approvals.pending) },
        ]}
      />
      <div className="grid-2">
        <section className="panel">
          <div className="panel__header">
            <h3 className="panel__title">Pipeline</h3>
            <Badge variant="demo">Demo</Badge>
          </div>
          <div className="panel__body panel__body--flush">
            <table className="table">
              <tbody>
                <tr>
                  <td>Prospects</td>
                  <td className="mono">{pipeline.prospects}</td>
                </tr>
                <tr>
                  <td>Qualified</td>
                  <td className="mono">{pipeline.qualified}</td>
                </tr>
                <tr>
                  <td>Customers</td>
                  <td className="mono">{pipeline.customers}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
        <section className="panel">
          <div className="panel__header">
            <h3 className="panel__title">Sample opportunities</h3>
          </div>
          <div className="panel__body">
            <ul className="data-list">
              {opportunities.map((o) => (
                <li key={o.id} className="data-list__item">
                  <div>
                    <div className="data-list__title">{o.title}</div>
                    <div className="data-list__meta">
                      {typeof o.detail === "number" ? `${o.detail} ${o.label}` : o.detail}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </section>
        <section className="panel">
          <div className="panel__header">
            <h3 className="panel__title">Alerts</h3>
          </div>
          <div className="panel__body">
            <div className="alert-row">
              {alerts.map((a) => (
                <div key={a.id} className={`alert-item alert-item--${a.severity}`}>
                  <div>
                    <div className="alert-item__title">{a.title}</div>
                    <div className="alert-item__body">{a.body}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>
        <section className="panel">
          <div className="panel__header">
            <h3 className="panel__title">Recent activity</h3>
          </div>
          <div className="panel__body">
            <ActivityTimeline items={activity} />
          </div>
        </section>
      </div>
    </div>
  );
}

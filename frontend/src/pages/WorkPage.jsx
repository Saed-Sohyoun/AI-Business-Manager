import { useCallback } from "react";
import {
  AdvancedDetails,
  Badge,
  EmptyState,
  LiveError,
  Skeleton,
} from "../components";
import { useDataMode } from "../context/DataModeContext";
import { useAsyncResource } from "../hooks/useAsyncResource";
import * as ownerApi from "../api/owner.js";
import { formatDateTime, formatDuration } from "../lib/format";
import { PageHeader } from "../layout/PageHeader";
import { agents as demoAgents } from "../data/demo";

export function WorkPage() {
  const { isDemo, isLive } = useDataMode();

  const load = useCallback(() => ownerApi.getActiveWork({ limit: 50 }), []);
  const { data, error, loading, reload } = useAsyncResource(load, {
    enabled: isLive,
    deps: [isLive],
  });

  if (isDemo) {
    return (
      <div className="stack">
        <PageHeader
          eyebrow="Demo"
          title="Work"
          description="Sample team activity. Live mode shows real active work from the backend."
        />
        <section className="panel">
          <div className="panel__body">
            <ul className="data-list">
              {demoAgents
                .filter((a) => a.status === "running" || a.status === "pending")
                .map((a) => (
                  <li key={a.id} className="data-list__item">
                    <div>
                      <div className="data-list__title">{a.name}</div>
                      <div className="data-list__meta">
                        {a.task} · {a.status}
                      </div>
                    </div>
                    <Badge variant="demo">Demo</Badge>
                  </li>
                ))}
            </ul>
          </div>
        </section>
      </div>
    );
  }

  if (loading && !data) {
    return (
      <div className="stack">
        <PageHeader title="Work" description="Loading…" />
        <Skeleton rows={4} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="stack">
        <PageHeader title="Work" description="What your team is doing now" />
        <LiveError error={error} onRetry={reload} resourceLabel="active work" />
      </div>
    );
  }

  const items = data?.items || [];
  const needs = items.filter((i) => i.needs_attention);
  const working = items.filter((i) => !i.needs_attention && i.status !== "waiting");
  const waiting = items.filter((i) => String(i.status).includes("wait"));

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Live"
        title="Work"
        description="What your digital team is doing — without agent internals as the main story."
      />

      <WorkSection title="Needs attention" items={needs} empty="Nothing needs your attention." />
      <WorkSection title="Working" items={working} empty="No work in progress." />
      <WorkSection title="Waiting" items={waiting} empty="Nothing waiting." />

      {items.length === 0 ? (
        <section className="panel">
          <EmptyState
            title="No active work"
            description="When research, audits, or delivery runs start, they appear here with progress and purpose."
          />
        </section>
      ) : null}
    </div>
  );
}

function WorkSection({ title, items, empty }) {
  if (!items?.length) return null;
  return (
    <section className="panel">
      <div className="panel__header">
        <h3 className="panel__title">{title}</h3>
      </div>
      <div className="panel__body">
        {items.length === 0 ? (
          <p className="muted">{empty}</p>
        ) : (
          <ul className="data-list">
            {items.map((w, idx) => (
              <li
                key={w.advanced_details?.agent_run_id || w.advanced_details?.manager_task_id || idx}
                className="data-list__item"
              >
                <div>
                  <div className="data-list__title">{w.title}</div>
                  <div className="data-list__meta">
                    {w.business_purpose || w.status}
                    {w.total ? ` · ${w.progress} / ${w.total}` : ""}
                    {w.started_at ? ` · started ${formatDateTime(w.started_at)}` : ""}
                    {w.duration_seconds != null
                      ? ` · ${formatDuration(w.duration_seconds)}`
                      : ""}
                  </div>
                  <AdvancedDetails>
                    <ul className="tech-kv">
                      {w.advanced_details?.agent_name ? (
                        <li>Agent: {w.advanced_details.agent_name}</li>
                      ) : null}
                      {w.advanced_details?.agent_run_id ? (
                        <li>Run ID: {w.advanced_details.agent_run_id}</li>
                      ) : null}
                      {w.advanced_details?.manager_task_id ? (
                        <li>Task ID: {w.advanced_details.manager_task_id}</li>
                      ) : null}
                    </ul>
                  </AdvancedDetails>
                </div>
                {w.needs_attention ? <Badge variant="warning">Attention</Badge> : null}
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

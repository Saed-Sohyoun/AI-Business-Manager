import { useState } from "react";
import { AgentStatus, Badge, Drawer, EmptyState, Select } from "../components";
import { useDataMode } from "../context/DataModeContext";
import { agents } from "../data/demo";
import { formatDateTime } from "../lib/format";
import { PageHeader } from "../layout/PageHeader";

/**
 * Technical AI Team view — repositioned under Settings.
 * Live mode: honest note that agent roster API is not an owner primary surface.
 */
export function AiTeamPage() {
  const { isDemo } = useDataMode();
  const [filter, setFilter] = useState("all");
  const [selected, setSelected] = useState(null);
  const filtered = filter === "all" ? agents : agents.filter((a) => a.status === filter);

  if (!isDemo) {
    return (
      <div className="stack">
        <PageHeader
          eyebrow="Advanced"
          title="AI Team"
          description="Specialist workers are orchestrated by the Manager. Primary owner views use Work and Overview — not agent internals."
        />
        <section className="panel">
          <EmptyState
            title="Agent roster is not a live owner API"
            description="Use Work for active business tasks and System controls for pause/resume. A detailed agent console remains an advanced concern — not the commercial home screen."
          />
        </section>
      </div>
    );
  }

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Demo · Advanced"
        title="AI Team"
        description="Demo specialist statuses for layout reference. Prefer Work and Overview in the commercial product."
      />
      <div className="toolbar">
        <Select
          label="Status"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          options={[
            { value: "all", label: "All" },
            { value: "running", label: "Running" },
            { value: "succeeded", label: "Succeeded" },
            { value: "failed", label: "Failed" },
            { value: "pending", label: "Pending" },
            { value: "idle", label: "Idle" },
          ]}
        />
        <div className="toolbar__spacer" />
        <Badge variant="demo">Demo</Badge>
      </div>
      <section className="panel">
        <div className="panel__body">
          {filtered.length === 0 ? (
            <EmptyState title="No agents match" description="Try another status filter." />
          ) : (
            filtered.map((agent) => (
              <div
                key={agent.id}
                role="button"
                tabIndex={0}
                onClick={() => setSelected(agent)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    setSelected(agent);
                  }
                }}
              >
                <AgentStatus agent={agent} />
              </div>
            ))
          )}
        </div>
      </section>
      <Drawer
        open={Boolean(selected)}
        title={selected?.name || "Agent"}
        onClose={() => setSelected(null)}
      >
        {selected ? (
          <div className="stack">
            <p>Status: {selected.status}</p>
            <p>Task: {selected.task}</p>
            <p className="mono">Last run: {formatDateTime(selected.lastRun)}</p>
            <p className="muted">Advanced demo detail only.</p>
          </div>
        ) : null}
      </Drawer>
    </div>
  );
}

export function AdvancedSettingsPage() {
  return (
    <div className="stack">
      <section className="panel">
        <div className="panel__header">
          <h3 className="panel__title">Advanced</h3>
        </div>
        <div className="panel__body">
          <p style={{ marginTop: 0 }}>
            Providers, execution IDs, logs, models, and workflow internals stay out of the primary
            navigation. They belong here when exposed.
          </p>
          <ul className="tech-kv">
            <li>n8n workflows — backend orchestration (HMAC protected)</li>
            <li>Agent contracts & ToolGateway — Wave 1 governance (immutable in Wave 3)</li>
            <li>Owner API key — temporary local auth; replace with session auth for public prod</li>
          </ul>
        </div>
      </section>
    </div>
  );
}

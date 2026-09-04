import { Link, useNavigate, useParams } from "react-router-dom";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Badge,
  Button,
  EmptyState,
  Input,
  LiveError,
  Skeleton,
} from "../components";
import { useDataMode } from "../context/DataModeContext";
import { useAsyncResource } from "../hooks/useAsyncResource";
import { humanizeApiError } from "../api/errors.js";
import * as ownerApi from "../api/owner.js";
import { PageHeader } from "../layout/PageHeader";

const TERMINAL_STATES = new Set([
  "completed",
  "partially_completed",
  "failed",
  "cancelled",
]);

/** Demo fixtures for Opportunities — never used as live fallback. */
export const DEMO_OPPORTUNITIES = [
  {
    id: "demo-opp-1",
    company: "ABC Cleaning Berlin",
    score: 91,
    category: "Strong opportunity",
    problem: "No clear online booking and slow lead follow-up",
    value: "High",
    auditStatus: "Complete",
    outreachStatus: "Draft ready",
    evidence: "High",
    nextAction: "Review outreach proposal",
  },
  {
    id: "demo-opp-2",
    company: "Nordwerk Solutions",
    score: 88,
    category: "Strong opportunity",
    problem: "Website lacks clear service packages",
    value: "Medium–High",
    auditStatus: "Partial",
    outreachStatus: "Not started",
    evidence: "Medium",
    nextAction: "Finish audit",
  },
];

function asList(payload) {
  if (!payload) return [];
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload.items)) return payload.items;
  if (Array.isArray(payload.opportunities)) return payload.opportunities;
  return [];
}

function normalizeOpportunity(raw) {
  if (!raw || typeof raw !== "object") return null;
  const id = raw.id || raw.opportunity_id;
  if (!id) return null;
  return {
    id: String(id),
    company:
      raw.company ||
      raw.company_name ||
      raw.name ||
      raw.title ||
      "Opportunity",
    score: raw.score ?? raw.total_score ?? "—",
    category: raw.category || raw.score_category || raw.status || "",
    problem:
      raw.problem ||
      raw.summary ||
      raw.why ||
      raw.rationale ||
      raw.description ||
      "",
    value: raw.value || raw.estimated_value || raw.potential || "—",
    auditStatus: raw.audit_status || raw.auditStatus || "—",
    outreachStatus: raw.outreach_status || raw.outreachStatus || "—",
    evidence: raw.evidence || raw.evidence_level || "—",
    nextAction: raw.next_action || raw.nextAction || raw.recommended_action || "—",
    status: raw.status || "",
    raw,
  };
}

function activityLabel(execution) {
  if (!execution) return "Starting";
  const activity = (execution.current_activity || "").trim();
  if (activity) return activity;
  const state = (execution.state || execution.status || "").toLowerCase();
  if (state === "queued") return "Starting";
  if (state === "running") return "Researching";
  if (state === "waiting" || state === "waiting_for_approval") return "Verifying";
  if (state === "completed" || state === "partially_completed") return "Completed";
  if (state === "failed") return "Failed";
  if (state === "cancelled") return "Cancelled";
  if (state === "blocked") return "Blocked";
  return state || "Starting";
}

function newIdempotencyKey() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `find-opp-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function OpportunitiesPage() {
  const { isDemo, isLive } = useDataMode();

  const load = useCallback(async () => {
    const payload = await ownerApi.listOpportunities({ limit: 50 });
    return asList(payload).map(normalizeOpportunity).filter(Boolean);
  }, []);

  const { data: items, error, loading, reload } = useAsyncResource(load, {
    enabled: isLive,
    deps: [isLive],
  });

  const [showForm, setShowForm] = useState(false);
  const [niche, setNiche] = useState("");
  const [location, setLocation] = useState("");
  const [desiredCount, setDesiredCount] = useState("10");
  const [launching, setLaunching] = useState(false);
  const [launchError, setLaunchError] = useState(null);
  const [execution, setExecution] = useState(null);
  const pollRef = useRef(null);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  function stopPolling() {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  async function pollExecution(executionId) {
    stopPolling();
    const tick = async () => {
      try {
        const view = await ownerApi.getExecution(executionId);
        setExecution(view);
        const state = (view.state || view.status || "").toLowerCase();
        if (TERMINAL_STATES.has(state)) {
          stopPolling();
          reload();
        }
      } catch (err) {
        stopPolling();
        setLaunchError(humanizeApiError(err));
      }
    };
    await tick();
    pollRef.current = setInterval(tick, 2000);
  }

  async function onFindOpportunities(e) {
    e.preventDefault();
    setLaunchError(null);
    setLaunching(true);
    try {
      const body = {
        idempotency_key: newIdempotencyKey(),
      };
      if (niche.trim()) body.niche = niche.trim();
      if (location.trim()) body.location = location.trim();
      const count = Number.parseInt(desiredCount, 10);
      if (Number.isFinite(count) && count > 0) body.desired_count = count;

      const result = await ownerApi.findOpportunities(body);
      setShowForm(false);
      setExecution({
        id: result.execution_id,
        state: result.status,
        current_activity: "Starting",
        result_summary: result.message,
      });
      if (result.execution_id) {
        await pollExecution(result.execution_id);
      }
    } catch (err) {
      setLaunchError(humanizeApiError(err));
    } finally {
      setLaunching(false);
    }
  }

  if (isDemo) {
    return (
      <div className="stack">
        <PageHeader
          eyebrow="Demo"
          title="Opportunities"
          description="Sample commercial pipeline. Switch to live and sign in to run real searches."
        />
        <OpportunityList items={DEMO_OPPORTUNITIES} demo />
      </div>
    );
  }

  if (loading && !items) {
    return (
      <div className="stack">
        <PageHeader title="Opportunities" description="Loading pipeline…" />
        <Skeleton rows={4} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="stack">
        <PageHeader title="Opportunities" description="Commercial pipeline" />
        <LiveError error={error} onRetry={reload} resourceLabel="opportunities" />
      </div>
    );
  }

  const list = items || [];

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Live"
        title="Opportunities"
        description="Qualified businesses your team has researched and scored."
        actions={
          <Button variant="primary" onClick={() => setShowForm((v) => !v)}>
            Find opportunities
          </Button>
        }
      />

      {showForm ? (
        <section className="panel">
          <div className="panel__header">
            <h3 className="panel__title">Start a search</h3>
          </div>
          <form className="panel__body stack" onSubmit={onFindOpportunities}>
            <Input
              id="find-niche"
              label="Niche"
              hint="Optional — e.g. cleaning services"
              value={niche}
              onChange={(e) => setNiche(e.target.value)}
            />
            <Input
              id="find-location"
              label="Location"
              hint="Optional — e.g. Berlin"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
            />
            <Input
              id="find-count"
              label="Desired count"
              type="number"
              min={1}
              max={50}
              value={desiredCount}
              onChange={(e) => setDesiredCount(e.target.value)}
            />
            <div className="filter-row">
              <Button type="submit" variant="primary" disabled={launching}>
                {launching ? "Starting…" : "Start search"}
              </Button>
              <Button type="button" variant="ghost" onClick={() => setShowForm(false)}>
                Cancel
              </Button>
            </div>
          </form>
        </section>
      ) : null}

      {launchError ? (
        <div className="callout callout--warning" role="alert">
          <h3 className="callout__title">{launchError.title}</h3>
          <p className="muted" style={{ marginBottom: 0 }}>
            {launchError.description}
          </p>
        </div>
      ) : null}

      {execution ? (
        <section className="panel">
          <div className="panel__header">
            <h3 className="panel__title">Search progress</h3>
            <Badge variant="accent">{activityLabel(execution)}</Badge>
          </div>
          <div className="panel__body">
            <p style={{ marginTop: 0 }}>
              Status: <strong>{activityLabel(execution)}</strong>
              {execution.state || execution.status ? (
                <>
                  {" "}
                  · <span className="mono">{execution.state || execution.status}</span>
                </>
              ) : null}
            </p>
            {execution.result_summary || execution.message ? (
              <p className="muted">{execution.result_summary || execution.message}</p>
            ) : null}
            {execution.failure_message ? (
              <p className="muted">{execution.failure_message}</p>
            ) : null}
            {typeof execution.completed_steps === "number" &&
            typeof execution.total_steps === "number" &&
            execution.total_steps > 0 ? (
              <p className="mono muted">
                Steps {execution.completed_steps} / {execution.total_steps}
              </p>
            ) : null}
          </div>
        </section>
      ) : null}

      <section className="panel">
        {list.length === 0 ? (
          <EmptyState
            title="No opportunities yet"
            description="Start a search to have your team research and score local businesses."
            actionLabel="Find opportunities"
            onAction={() => setShowForm(true)}
          />
        ) : (
          <div className="panel__body panel__body--flush">
            <OpportunityList items={list} />
          </div>
        )}
      </section>
    </div>
  );
}

function OpportunityList({ items, demo }) {
  return (
    <ul className="opp-list">
      {items.map((item) => (
        <li key={item.id} className="opp-list__item">
          <div className="opp-list__main">
            <div className="opp-list__title">
              {item.company}
              {demo ? <Badge variant="demo">Demo</Badge> : null}
            </div>
            <div className="opp-list__score">
              {item.score} / 100{item.category ? ` · ${item.category}` : ""}
            </div>
            {item.problem ? (
              <p className="opp-list__why">
                <strong>Why:</strong> {item.problem}
              </p>
            ) : null}
            <div className="opp-list__meta">
              Potential: {item.value} · Audit: {item.auditStatus} · Outreach: {item.outreachStatus} ·
              Evidence: {item.evidence}
            </div>
            <div className="opp-list__next">Next: {item.nextAction}</div>
          </div>
          <Link className="btn btn--secondary" to={`/opportunities/${item.id}`}>
            View opportunity
          </Link>
        </li>
      ))}
    </ul>
  );
}

export function OpportunityDetailPage() {
  const { id } = useParams();
  const { isDemo, isLive } = useDataMode();
  const navigate = useNavigate();

  const demoItem = DEMO_OPPORTUNITIES.find((o) => o.id === id);

  const load = useCallback(() => ownerApi.getOpportunity(id), [id]);
  const { data, error, loading, reload } = useAsyncResource(load, {
    enabled: isLive && Boolean(id),
    deps: [isLive, id],
  });

  if (isDemo) {
    if (!demoItem) {
      return (
        <EmptyState
          title="Not found"
          description="This demo opportunity does not exist."
          actionLabel="Back"
          onAction={() => navigate("/opportunities")}
        />
      );
    }
    return <OpportunityDetailView item={demoItem} demo />;
  }

  if (loading && !data) {
    return (
      <div className="stack">
        <PageHeader title="Opportunity" description="Loading…" />
        <Skeleton rows={4} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="stack">
        <PageHeader title="Opportunity" description="Detail view" />
        <LiveError error={error} onRetry={reload} resourceLabel="opportunity" />
      </div>
    );
  }

  const item = normalizeOpportunity(data);
  if (!item) {
    return (
      <EmptyState
        title="Not found"
        description="This opportunity is not available."
        actionLabel="Back"
        onAction={() => navigate("/opportunities")}
      />
    );
  }

  return <OpportunityDetailView item={item} />;
}

function OpportunityDetailView({ item, demo }) {
  return (
    <div className="stack">
      <PageHeader
        eyebrow={demo ? "Demo" : "Live"}
        title={item.company}
        description={`${item.score}/100${item.category ? ` · ${item.category}` : ""}`}
        actions={
          <Link to="/opportunities" className="btn btn--ghost">
            Back
          </Link>
        }
      />
      <section className="panel">
        <div className="panel__header">
          <h3 className="panel__title">Why this is an opportunity</h3>
        </div>
        <div className="panel__body">
          <p>{item.problem || "No summary provided."}</p>
          <p>
            <strong>Estimated value:</strong> {item.value}
          </p>
        </div>
      </section>
      <section className="panel">
        <div className="panel__header">
          <h3 className="panel__title">Evidence</h3>
        </div>
        <div className="panel__body">
          <p>
            <strong>Finding:</strong> {item.problem || "—"}
          </p>
          <p>
            <strong>Confidence:</strong> {item.evidence}
          </p>
          {demo ? <p className="muted">Sample evidence for demo walkthrough only.</p> : null}
        </div>
      </section>
      <section className="panel">
        <div className="panel__header">
          <h3 className="panel__title">Recommended next step</h3>
        </div>
        <div className="panel__body">
          <p>{item.nextAction}</p>
          <p>
            Audit: {item.auditStatus} · Outreach: {item.outreachStatus}
          </p>
        </div>
      </section>
    </div>
  );
}

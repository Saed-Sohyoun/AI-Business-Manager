import { useCallback, useState } from "react";
import { Badge, Button, EmptyState, LiveError, Skeleton, Table } from "../components";
import { useDataMode } from "../context/DataModeContext";
import { useAsyncResource } from "../hooks/useAsyncResource";
import { humanizeApiError } from "../api/errors.js";
import * as ownerApi from "../api/owner.js";
import { reports as demoReports } from "../data/demo";
import { formatDateTime } from "../lib/format";
import { PageHeader } from "../layout/PageHeader";

function asList(payload) {
  if (!payload) return [];
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload.items)) return payload.items;
  if (Array.isArray(payload.reports)) return payload.reports;
  return [];
}

function normalizeReport(raw) {
  if (!raw || typeof raw !== "object") return null;
  const id = raw.id;
  if (!id) return null;
  return {
    id: String(id),
    title: raw.title || "Report",
    period: raw.period_type || raw.period || "",
    status: raw.status || "generated",
    at: raw.generated_at || raw.at || raw.created_at || null,
    sections: raw.sections || [],
    facts: raw.facts_snapshot || raw.facts || null,
    raw,
  };
}

function newIdempotencyKey() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `report-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function sectionStatements(sections, kind) {
  if (!Array.isArray(sections)) return [];
  const texts = [];
  for (const section of sections) {
    const statements = section.statements || [];
    for (const s of statements) {
      if (!kind || s.kind === kind) {
        if (s.text) texts.push(s.text);
      }
    }
  }
  return texts;
}

export function ReportsPage() {
  const { isDemo, isLive } = useDataMode();
  const [expandedId, setExpandedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState(null);
  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState(null);
  const [generateMessage, setGenerateMessage] = useState(null);

  const load = useCallback(async () => {
    const payload = await ownerApi.listReports();
    return asList(payload).map(normalizeReport).filter(Boolean);
  }, []);

  const { data: items, error, loading, reload } = useAsyncResource(load, {
    enabled: isLive,
    deps: [isLive],
  });

  async function toggleExpand(id) {
    if (expandedId === id) {
      setExpandedId(null);
      setDetail(null);
      setDetailError(null);
      return;
    }
    setExpandedId(id);
    setDetail(null);
    setDetailError(null);
    setDetailLoading(true);
    try {
      const raw = await ownerApi.getReport(id);
      setDetail(normalizeReport(raw));
    } catch (err) {
      setDetailError(humanizeApiError(err));
    } finally {
      setDetailLoading(false);
    }
  }

  async function onGenerate() {
    setGenerateError(null);
    setGenerateMessage(null);
    setGenerating(true);
    try {
      const result = await ownerApi.generateReport({
        period_type: "daily",
        idempotency_key: newIdempotencyKey(),
      });
      if (result?.execution_id) {
        setGenerateMessage(
          result.message || "Report generation started. Refresh the list shortly.",
        );
      } else if (result?.id || result?.report?.id) {
        setGenerateMessage("Report generated.");
        await reload();
      } else {
        setGenerateMessage(result?.message || "Report request accepted.");
        await reload();
      }
    } catch (err) {
      setGenerateError(humanizeApiError(err));
    } finally {
      setGenerating(false);
    }
  }

  if (isDemo) {
    return (
      <div className="stack">
        <PageHeader
          eyebrow="Demo"
          title="Reports"
          description="Sample CEO reports for layout only."
        />
        <section className="panel">
          <div className="panel__header">
            <h3 className="panel__title">Recent reports</h3>
            <Badge variant="demo">Demo</Badge>
          </div>
          <div className="panel__body panel__body--flush">
            <Table
              columns={[
                { key: "title", header: "Report", primary: true, render: (r) => r.title },
                {
                  key: "period",
                  header: "Period",
                  render: (r) => <Badge variant="neutral">{r.period}</Badge>,
                },
                {
                  key: "status",
                  header: "Status",
                  render: (r) => <Badge variant="success">{r.status}</Badge>,
                },
                {
                  key: "at",
                  header: "Generated",
                  render: (r) => <span className="mono">{formatDateTime(r.at)}</span>,
                },
              ]}
              rows={demoReports}
            />
          </div>
        </section>
        <section className="panel">
          <div className="panel__header">
            <h3 className="panel__title">How reports are structured</h3>
          </div>
          <div className="panel__body report-structure">
            <div>
              <h4>Facts</h4>
              <p className="muted">What happened — ledger and ops numbers only.</p>
            </div>
            <div>
              <h4>Interpretation</h4>
              <p className="muted">What it means for the business.</p>
            </div>
            <div>
              <h4>Recommendations</h4>
              <p className="muted">What you should decide next.</p>
            </div>
          </div>
        </section>
      </div>
    );
  }

  if (loading && !items) {
    return (
      <div className="stack">
        <PageHeader title="Reports" description="Loading…" />
        <Skeleton rows={3} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="stack">
        <PageHeader title="Reports" description="CEO reports" />
        <LiveError error={error} onRetry={reload} resourceLabel="reports" />
      </div>
    );
  }

  const list = items || [];

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Live"
        title="Reports"
        description="CEO reports separate facts, interpretation, and recommendations."
        actions={
          <Button variant="primary" onClick={onGenerate} disabled={generating}>
            {generating ? "Generating…" : "Generate report"}
          </Button>
        }
      />

      {generateError ? (
        <div className="callout callout--warning" role="alert">
          <h3 className="callout__title">{generateError.title}</h3>
          <p className="muted" style={{ marginBottom: 0 }}>
            {generateError.description}
          </p>
        </div>
      ) : null}
      {generateMessage ? <p className="muted">{generateMessage}</p> : null}

      <section className="panel">
        {list.length === 0 ? (
          <EmptyState
            title="No reports yet"
            description="Generate a CEO report when you want a structured facts · interpretation · recommendations summary."
            actionLabel="Generate report"
            onAction={onGenerate}
          />
        ) : (
          <ul className="report-list">
            {list.map((r) => (
              <li key={r.id} className="report-list__item">
                <button
                  type="button"
                  className="report-list__toggle"
                  onClick={() => toggleExpand(r.id)}
                  aria-expanded={expandedId === r.id}
                >
                  <span className="report-list__title">{r.title}</span>
                  <span className="report-list__meta mono">
                    {r.period || "—"} · {r.at ? formatDateTime(r.at) : "—"}
                  </span>
                </button>
                {expandedId === r.id ? (
                  <div className="report-list__detail">
                    {detailLoading ? <Skeleton rows={2} /> : null}
                    {detailError ? (
                      <p role="alert">
                        {detailError.title}: {detailError.description}
                      </p>
                    ) : null}
                    {detail && !detailLoading ? <ReportDetailBody report={detail} /> : null}
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function ReportDetailBody({ report }) {
  const facts = sectionStatements(report.sections, "fact");
  const interpretation = sectionStatements(report.sections, "interpretation");
  const recommendations = sectionStatements(report.sections, "recommendation");

  const hasSections =
    facts.length || interpretation.length || recommendations.length || report.sections?.length;

  if (!hasSections && !report.facts) {
    return <p className="muted">No section content returned for this report.</p>;
  }

  return (
    <div className="report-structure">
      <div>
        <h4>Facts</h4>
        {facts.length ? (
          <ul>
            {facts.map((t, i) => (
              <li key={`f-${i}`}>{t}</li>
            ))}
          </ul>
        ) : (
          <p className="muted">No fact statements.</p>
        )}
      </div>
      <div>
        <h4>Interpretation</h4>
        {interpretation.length ? (
          <ul>
            {interpretation.map((t, i) => (
              <li key={`i-${i}`}>{t}</li>
            ))}
          </ul>
        ) : (
          <p className="muted">No interpretation statements.</p>
        )}
      </div>
      <div>
        <h4>Recommendations</h4>
        {recommendations.length ? (
          <ul>
            {recommendations.map((t, i) => (
              <li key={`r-${i}`}>{t}</li>
            ))}
          </ul>
        ) : (
          <p className="muted">No recommendations.</p>
        )}
      </div>
    </div>
  );
}

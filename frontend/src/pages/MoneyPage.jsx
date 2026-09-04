import { useCallback } from "react";
import {
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
import { finance as demoFinance } from "../data/demo";
import { formatMoney } from "../lib/format";
import { PageHeader } from "../layout/PageHeader";

export function MoneyPage() {
  const { isDemo, isLive } = useDataMode();

  const load = useCallback(() => ownerApi.getDashboardSummary(), []);
  const { data: summary, error, loading, reload } = useAsyncResource(load, {
    enabled: isLive,
    deps: [isLive],
  });

  if (isDemo) {
    return (
      <div className="stack">
        <PageHeader
          eyebrow="Demo"
          title="Money"
          description="Sample ledger figures. Live mode uses real revenue and cost totals from the database."
        />
        <MetricStrip
          items={[
            { label: "Revenue", value: formatMoney(demoFinance.revenue, demoFinance.currency) },
            { label: "Costs", value: formatMoney(demoFinance.costs, demoFinance.currency) },
            { label: "Profit", value: formatMoney(demoFinance.profit, demoFinance.currency) },
          ]}
        />
        <section className="panel">
          <div className="panel__header">
            <h3 className="panel__title">Derived metrics</h3>
            <Badge variant="demo">Demo</Badge>
          </div>
          <div className="panel__body">
            <p className="muted">MRR, ROI, CPL, and CAC are not shown from demo inventiveness.</p>
          </div>
        </section>
      </div>
    );
  }

  if (loading && !summary) {
    return (
      <div className="stack">
        <PageHeader title="Money" description="Loading…" />
        <SkeletonMetrics count={3} />
        <Skeleton rows={3} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="stack">
        <PageHeader title="Money" description="Revenue, costs, and profit" />
        <LiveError error={error} onRetry={reload} resourceLabel="financial summary" />
      </div>
    );
  }

  const currency = summary.money?.currency || "EUR";
  const revenue = Number(summary.money?.revenue || 0);
  const costs = Number(summary.money?.costs || 0);
  const profit = Number(summary.money?.profit || 0);
  const hasActivity = revenue !== 0 || costs !== 0;

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Live"
        title="Money"
        description="Totals from your ledger. Derived ratios only appear when the math is defined."
      />

      <MetricStrip
        items={[
          { label: "Revenue", value: formatMoney(revenue, currency) },
          { label: "Costs", value: formatMoney(costs, currency) },
          { label: "Profit", value: formatMoney(profit, currency) },
        ]}
      />

      {!hasActivity ? (
        <section className="panel">
          <EmptyState
            title="No financial activity yet"
            description="Revenue and cost entries will appear as delivery and operations record money in the ledger."
          />
        </section>
      ) : null}

      <section className="panel">
        <div className="panel__header">
          <h3 className="panel__title">Derived metrics</h3>
        </div>
        <div className="panel__body panel__body--flush">
          <table className="table">
            <tbody>
              <tr>
                <td>MRR</td>
                <td>Not enough data yet</td>
              </tr>
              <tr>
                <td>ROI</td>
                <td>{costs > 0 ? `${((profit / costs) * 100).toFixed(1)}%` : "Not enough data yet"}</td>
              </tr>
              <tr>
                <td>CPL</td>
                <td>Not enough data yet</td>
              </tr>
              <tr>
                <td>CAC</td>
                <td>Not enough data yet</td>
              </tr>
            </tbody>
          </table>
          <p className="field__hint" style={{ padding: "0.75rem 1rem" }}>
            CPL and CAC need attributed acquisition costs and converted customers. MRR needs
            recurring revenue classification. We will not invent those from incomplete data.
          </p>
        </div>
      </section>
    </div>
  );
}

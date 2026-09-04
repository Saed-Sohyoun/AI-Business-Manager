import { Link, useNavigate, useParams } from "react-router-dom";
import { useCallback } from "react";
import {
  Badge,
  EmptyState,
  LiveError,
  Skeleton,
  Table,
} from "../components";
import { useDataMode } from "../context/DataModeContext";
import { useAsyncResource } from "../hooks/useAsyncResource";
import * as ownerApi from "../api/owner.js";
import { customers as demoCustomers } from "../data/demo";
import { formatDate, formatMoney } from "../lib/format";
import { PageHeader } from "../layout/PageHeader";

function asList(payload) {
  if (!payload) return [];
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload.items)) return payload.items;
  if (Array.isArray(payload.customers)) return payload.customers;
  return [];
}

function normalizeCustomer(raw) {
  if (!raw || typeof raw !== "object") return null;
  const id = raw.id;
  if (!id) return null;
  return {
    id: String(id),
    name: raw.name || raw.company_name || "Customer",
    status: raw.status || "active",
    since: raw.converted_at || raw.since || raw.created_at || null,
    mrr: raw.mrr ?? raw.monthly_revenue ?? null,
    email: raw.email || "",
    raw,
  };
}

export function CustomersPage() {
  const { isDemo, isLive } = useDataMode();

  const load = useCallback(async () => {
    const payload = await ownerApi.listCustomers();
    return asList(payload).map(normalizeCustomer).filter(Boolean);
  }, []);

  const { data: items, error, loading, reload } = useAsyncResource(load, {
    enabled: isLive,
    deps: [isLive],
  });

  if (isDemo) {
    return (
      <div className="stack">
        <PageHeader
          eyebrow="Demo"
          title="Customers"
          description="Sample accounts. Live mode loads real customers from the owner API."
        />
        <section className="panel">
          <div className="panel__body panel__body--flush">
            <Table
              columns={[
                { key: "name", header: "Customer", primary: true, render: (c) => c.name },
                {
                  key: "status",
                  header: "Status",
                  render: (c) => (
                    <Badge variant={c.status === "active" ? "success" : "neutral"}>
                      {c.status}
                    </Badge>
                  ),
                },
                {
                  key: "since",
                  header: "Since",
                  render: (c) => <span className="mono">{formatDate(c.since)}</span>,
                },
                {
                  key: "mrr",
                  header: "MRR",
                  render: (c) => <span className="mono">{formatMoney(c.mrr, "EUR")}</span>,
                },
              ]}
              rows={demoCustomers}
            />
          </div>
        </section>
      </div>
    );
  }

  if (loading && !items) {
    return (
      <div className="stack">
        <PageHeader title="Customers" description="Loading…" />
        <Skeleton rows={3} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="stack">
        <PageHeader title="Customers" description="Relationships and delivery" />
        <LiveError error={error} onRetry={reload} resourceLabel="customers" />
      </div>
    );
  }

  const list = items || [];

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Live"
        title="Customers"
        description="Accounts under delivery."
      />
      <section className="panel">
        {list.length === 0 ? (
          <EmptyState
            title="No customers yet"
            description="When prospects convert and delivery starts, customers will appear here with status and next actions."
          />
        ) : (
          <div className="panel__body panel__body--flush">
            <Table
              columns={[
                {
                  key: "name",
                  header: "Customer",
                  primary: true,
                  render: (c) => (
                    <Link to={`/customers/${c.id}`}>{c.name}</Link>
                  ),
                },
                {
                  key: "status",
                  header: "Status",
                  render: (c) => (
                    <Badge variant={c.status === "active" ? "success" : "neutral"}>
                      {c.status}
                    </Badge>
                  ),
                },
                {
                  key: "since",
                  header: "Since",
                  render: (c) => (
                    <span className="mono">{c.since ? formatDate(c.since) : "—"}</span>
                  ),
                },
                {
                  key: "mrr",
                  header: "MRR",
                  render: (c) => (
                    <span className="mono">
                      {c.mrr != null ? formatMoney(c.mrr, "EUR") : "—"}
                    </span>
                  ),
                },
              ]}
              rows={list}
            />
          </div>
        )}
      </section>
    </div>
  );
}

export function CustomerDetailPage() {
  const { id } = useParams();
  const { isDemo, isLive } = useDataMode();
  const navigate = useNavigate();

  const demoItem = demoCustomers.find((c) => c.id === id);

  const load = useCallback(() => ownerApi.getCustomer(id), [id]);
  const { data, error, loading, reload } = useAsyncResource(load, {
    enabled: isLive && Boolean(id),
    deps: [isLive, id],
  });

  if (isDemo) {
    if (!demoItem) {
      return (
        <EmptyState
          title="Not found"
          description="This demo customer does not exist."
          actionLabel="Back"
          onAction={() => navigate("/customers")}
        />
      );
    }
    return (
      <div className="stack">
        <PageHeader
          eyebrow="Demo"
          title={demoItem.name}
          description={`Status: ${demoItem.status}`}
          actions={
            <Link to="/customers" className="btn btn--ghost">
              Back
            </Link>
          }
        />
        <section className="panel">
          <div className="panel__body">
            <p>
              Since <span className="mono">{formatDate(demoItem.since)}</span>
            </p>
            <p>
              MRR: <span className="mono">{formatMoney(demoItem.mrr, "EUR")}</span>
            </p>
          </div>
        </section>
      </div>
    );
  }

  if (loading && !data) {
    return (
      <div className="stack">
        <PageHeader title="Customer" description="Loading…" />
        <Skeleton rows={3} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="stack">
        <PageHeader title="Customer" description="Detail" />
        <LiveError error={error} onRetry={reload} resourceLabel="customer" />
      </div>
    );
  }

  const item = normalizeCustomer(data);
  if (!item) {
    return (
      <EmptyState
        title="Not found"
        description="This customer is not available."
        actionLabel="Back"
        onAction={() => navigate("/customers")}
      />
    );
  }

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Live"
        title={item.name}
        description={`Status: ${item.status}`}
        actions={
          <Link to="/customers" className="btn btn--ghost">
            Back
          </Link>
        }
      />
      <section className="panel">
        <div className="panel__body">
          {item.email ? <p>Email: {item.email}</p> : null}
          <p>
            Since{" "}
            <span className="mono">{item.since ? formatDate(item.since) : "—"}</span>
          </p>
          {item.mrr != null ? (
            <p>
              MRR: <span className="mono">{formatMoney(item.mrr, "EUR")}</span>
            </p>
          ) : null}
        </div>
      </section>
    </div>
  );
}

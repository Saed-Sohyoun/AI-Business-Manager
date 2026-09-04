import { useCallback, useState } from "react";
import {
  ConfirmationDialog,
  DecisionApprovalCard,
  EmptyState,
  LiveError,
  Skeleton,
} from "../components";
import { useDataMode } from "../context/DataModeContext";
import { useAsyncResource } from "../hooks/useAsyncResource";
import { useToast } from "../hooks/useToast";
import * as ownerApi from "../api/owner.js";
import { humanizeApiError } from "../api/errors.js";
import { ApiClientError } from "../api/client.js";
import { approvals as demoApprovals } from "../data/demo";
import { PageHeader } from "../layout/PageHeader";

function mapDemoApproval(a) {
  return {
    id: a.id,
    title: a.actionType,
    summary: a.description,
    why: a.description,
    affected_party: a.requestedBy,
    estimated_cost: null,
    expected_benefit: null,
    risk: a.risk,
    reversibility: "Review carefully",
    expires_at: a.expiresAt,
    status: a.status,
    recommended_action: "Review",
    advanced_details: {
      requesting_agent: a.requestedBy,
      action_id: a.actionType,
    },
  };
}

export function ApprovalsPage() {
  const { isDemo, isLive } = useDataMode();
  const { push } = useToast();
  const [pending, setPending] = useState(null);
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(() => ownerApi.listApprovals({ status: "pending", limit: 50 }), []);
  const { data, error, loading, reload, setData } = useAsyncResource(load, {
    enabled: isLive,
    deps: [isLive],
  });

  if (isDemo) {
    return <DemoApprovals />;
  }

  if (loading && !data) {
    return (
      <div className="stack">
        <PageHeader eyebrow="Decisions" title="Approvals" description="Loading pending decisions…" />
        <Skeleton rows={4} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="stack">
        <PageHeader eyebrow="Decisions" title="Approvals" description="Live decisions from your team." />
        <LiveError error={error} onRetry={reload} resourceLabel="approvals" />
      </div>
    );
  }

  const items = Array.isArray(data) ? data.filter((a) => a.status === "pending") : [];

  const runConfirm = async () => {
    if (!pending) return;
    const { approval, mode } = pending;
    setBusyId(approval.id);
    try {
      const updated =
        mode === "approve"
          ? await ownerApi.approveApproval(approval.id, { note: "Approved by owner" })
          : await ownerApi.rejectApproval(approval.id, { note: "Rejected by owner" });
      setData((prev) => {
        const list = Array.isArray(prev) ? prev : [];
        return list.map((a) => (a.id === updated.id ? updated : a));
      });
      push(
        mode === "approve" ? "Approved — the system may proceed when other controls allow." : "Rejected.",
        mode === "approve" ? "success" : "info",
      );
      setPending(null);
      reload();
    } catch (err) {
      const human = humanizeApiError(err);
      push(human.description || human.title, "error");
      if (err instanceof ApiClientError && (err.status === 409 || err.status === 422)) {
        reload();
        setPending(null);
      }
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Decisions"
        title="Approvals"
        description="Your team asks before sending outreach or taking sensitive actions. Approve only what you understand."
      />

      {items.length === 0 ? (
        <section className="panel">
          <EmptyState
            title="No pending decisions"
            description="When outreach or other sensitive work needs your say, it will appear here."
          />
        </section>
      ) : (
        <div className="stack" style={{ gap: "0.75rem" }}>
          {items.map((approval) => (
            <DecisionApprovalCard
              key={approval.id}
              approval={approval}
              busy={busyId === approval.id}
              onApprove={(a) => setPending({ approval: a, mode: "approve" })}
              onReject={(a) => setPending({ approval: a, mode: "reject" })}
            />
          ))}
        </div>
      )}

      <ConfirmationDialog
        open={Boolean(pending)}
        busy={Boolean(busyId)}
        title={pending?.mode === "approve" ? "Approve this action?" : "Reject this action?"}
        description={
          pending
            ? pending.mode === "approve"
              ? `You are authorizing: ${pending.approval.title}. ${pending.approval.summary}`
              : `Reject: ${pending.approval.title}. The team will not proceed with this action.`
            : ""
        }
        confirmLabel={pending?.mode === "approve" ? "Approve" : "Reject"}
        danger={pending?.mode === "reject"}
        onCancel={() => !busyId && setPending(null)}
        onConfirm={runConfirm}
      >
        {pending?.approval?.estimated_cost ? (
          <p className="muted">Estimated cost: {pending.approval.estimated_cost}</p>
        ) : null}
        {pending?.approval?.affected_party ? (
          <p className="muted">Affected: {pending.approval.affected_party}</p>
        ) : null}
      </ConfirmationDialog>
    </div>
  );
}

function DemoApprovals() {
  const { push } = useToast();
  const [items, setItems] = useState(demoApprovals.map(mapDemoApproval));
  const [pending, setPending] = useState(null);
  const pendingItems = items.filter((a) => a.status === "pending");

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Demo"
        title="Approvals"
        description="Sample decisions only. Switch to live data to approve real requests against the backend."
      />
      {pendingItems.length === 0 ? (
        <EmptyState title="No pending approvals" description="Demo queue is empty." />
      ) : (
        pendingItems.map((approval) => (
          <DecisionApprovalCard
            key={approval.id}
            approval={approval}
            onApprove={(a) => setPending({ approval: a, mode: "approve" })}
            onReject={(a) => setPending({ approval: a, mode: "reject" })}
          />
        ))
      )}
      <ConfirmationDialog
        open={Boolean(pending)}
        title="Demo action"
        description="This updates sample data only — not the live backend."
        confirmLabel={pending?.mode === "approve" ? "Approve (demo)" : "Reject (demo)"}
        danger={pending?.mode === "reject"}
        onCancel={() => setPending(null)}
        onConfirm={() => {
          setItems((prev) =>
            prev.map((a) =>
              a.id === pending.approval.id
                ? { ...a, status: pending.mode === "approve" ? "approved" : "rejected" }
                : a,
            ),
          );
          push("Demo state updated — not a live approval.", "info");
          setPending(null);
        }}
      />
    </div>
  );
}

import { Badge } from "./Badge";
import { Button } from "./Button";
import { AdvancedDetails } from "./AdvancedDetails";
import { formatDateTime, formatMoney } from "../lib/format";

function riskVariant(risk) {
  const r = String(risk || "").toLowerCase();
  if (r === "red") return "danger";
  if (r === "green") return "success";
  return "warning";
}

/**
 * Owner-facing approval decision card (business language first).
 */
export function DecisionApprovalCard({
  approval,
  busy = false,
  onApprove,
  onReject,
  onReview,
}) {
  const adv = approval.advanced_details || {};
  const cost =
    approval.estimated_cost != null && approval.estimated_cost !== ""
      ? String(approval.estimated_cost)
      : null;

  return (
    <article className={`decision-card decision-card--${String(approval.risk || "yellow").toLowerCase()}`}>
      <div className="decision-card__top">
        <h3 className="decision-card__title">{approval.title}</h3>
        <Badge variant={riskVariant(approval.risk)}>
          {String(approval.risk || "review").toUpperCase()}
        </Badge>
      </div>

      <dl className="decision-grid">
        <div>
          <dt>What</dt>
          <dd>{approval.summary}</dd>
        </div>
        <div>
          <dt>Why</dt>
          <dd>{approval.why}</dd>
        </div>
        {approval.affected_party ? (
          <div>
            <dt>Who</dt>
            <dd>{approval.affected_party}</dd>
          </div>
        ) : null}
        {cost ? (
          <div>
            <dt>Cost</dt>
            <dd>{cost.includes("€") || cost.includes("$") ? cost : formatMoney(cost, "EUR")}</dd>
          </div>
        ) : null}
        {approval.expected_benefit ? (
          <div>
            <dt>Benefit</dt>
            <dd>{approval.expected_benefit}</dd>
          </div>
        ) : null}
        <div>
          <dt>Risk</dt>
          <dd>{approval.risk}</dd>
        </div>
        <div>
          <dt>Reversibility</dt>
          <dd>{approval.reversibility}</dd>
        </div>
        <div>
          <dt>Expires</dt>
          <dd>{formatDateTime(approval.expires_at)}</dd>
        </div>
      </dl>

      <AdvancedDetails>
        <ul className="tech-kv">
          {adv.requesting_agent ? <li>Requesting agent: {adv.requesting_agent}</li> : null}
          {adv.action_id ? <li>Action ID: {adv.action_id}</li> : null}
          {adv.execution_id ? <li>Execution ID: {adv.execution_id}</li> : null}
          {adv.policy_level ? <li>Policy level: {adv.policy_level}</li> : null}
          {adv.contract_version ? <li>Contract: {adv.contract_version}</li> : null}
          {adv.fingerprint ? <li>Fingerprint: {adv.fingerprint}</li> : null}
        </ul>
      </AdvancedDetails>

      <div className="decision-card__actions">
        {onReview ? (
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => onReview(approval)}>
            Review details
          </Button>
        ) : null}
        <Button size="sm" variant="secondary" disabled={busy} onClick={() => onReject(approval)}>
          Reject
        </Button>
        <Button size="sm" variant="primary" disabled={busy} onClick={() => onApprove(approval)}>
          {busy ? "Working…" : "Approve"}
        </Button>
      </div>
    </article>
  );
}

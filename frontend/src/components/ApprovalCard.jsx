import { Badge } from './Badge'
import { Button } from './Button'
import { formatDateTime } from '../lib/format'

export function ApprovalCard({ approval, onApprove, onReject, onView }) {
  const riskVariant = approval.risk === 'red' ? 'danger' : approval.risk === 'green' ? 'success' : 'warning'
  return (
    <article className={`approval-card approval-card--${approval.risk}`}>
      <div className="approval-card__top">
        <div className="approval-card__action">{approval.actionType}</div>
        <Badge variant={riskVariant}>{String(approval.risk).toUpperCase()}</Badge>
      </div>
      <p className="approval-card__desc">{approval.description}</p>
      <div className="approval-card__meta">
        <span>by {approval.requestedBy}</span>
        <span>{formatDateTime(approval.requestedAt)}</span>
        {approval.expiresAt ? <span>expires {formatDateTime(approval.expiresAt)}</span> : null}
      </div>
      <div className="approval-card__actions">
        {onView ? (
          <Button size="sm" variant="ghost" onClick={() => onView(approval)}>
            Details
          </Button>
        ) : null}
        {onReject ? (
          <Button size="sm" variant="secondary" onClick={() => onReject(approval)}>
            Reject
          </Button>
        ) : null}
        {onApprove ? (
          <Button size="sm" variant="primary" onClick={() => onApprove(approval)} disabled={approval.risk === 'red'}>
            {approval.risk === 'red' ? 'Human-only' : 'Approve'}
          </Button>
        ) : null}
      </div>
    </article>
  )
}

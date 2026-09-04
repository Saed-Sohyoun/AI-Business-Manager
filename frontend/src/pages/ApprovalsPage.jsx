import { useState } from 'react'
import {
  ApprovalCard,
  ConfirmationDialog,
  EmptyState,
} from '../components'
import { approvals as seed } from '../data/demo'
import { useToast } from '../hooks/useToast'
import { PageHeader } from '../layout/PageHeader'

export function ApprovalsPage() {
  const { push } = useToast()
  const [items, setItems] = useState(seed)
  const [pending, setPending] = useState(null)

  const pendingItems = items.filter((a) => a.status === 'pending')

  const confirmAction = () => {
    if (!pending) return
    const { approval, mode } = pending
    setItems((prev) =>
      prev.map((a) =>
        a.id === approval.id
          ? { ...a, status: mode === 'approve' ? 'approved' : 'rejected' }
          : a,
      ),
    )
    push(
      mode === 'approve'
        ? `Approved ${approval.actionType} (demo UI only)`
        : `Rejected ${approval.actionType} (demo UI only)`,
      mode === 'approve' ? 'success' : 'info',
    )
    setPending(null)
  }

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Operate"
        title="Approvals"
        description="YELLOW actions require an authorized human. RED actions stay human-only. This screen does not call the live API yet."
      />
      {pendingItems.length === 0 ? (
        <section className="panel">
          <EmptyState
            title="No pending approvals"
            description="When agents request outbound or sensitive work, items appear here."
          />
        </section>
      ) : (
        <div className="stack" style={{ gap: '0.75rem' }}>
          {pendingItems.map((approval) => (
            <ApprovalCard
              key={approval.id}
              approval={approval}
              onApprove={(a) => setPending({ approval: a, mode: 'approve' })}
              onReject={(a) => setPending({ approval: a, mode: 'reject' })}
            />
          ))}
        </div>
      )}

      <ConfirmationDialog
        open={Boolean(pending)}
        title={pending?.mode === 'approve' ? 'Approve action?' : 'Reject action?'}
        description={
          pending
            ? `${pending.approval.actionType} — ${pending.approval.description} This updates demo state only.`
            : ''
        }
        confirmLabel={pending?.mode === 'approve' ? 'Approve' : 'Reject'}
        danger={pending?.mode === 'reject'}
        onCancel={() => setPending(null)}
        onConfirm={confirmAction}
      />
    </div>
  )
}

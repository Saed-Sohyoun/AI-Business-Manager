import { Badge, Table } from '../components'
import { outreach } from '../data/demo'
import { PageHeader } from '../layout/PageHeader'

export function OutreachPage() {
  return (
    <div className="stack">
      <PageHeader
        eyebrow="Pipeline"
        title="Outreach"
        description="Drafts and sends always gate through approvals. Nothing here auto-sends."
      />
      <section className="panel">
        <div className="panel__body panel__body--flush">
          <Table
            columns={[
              { key: 'company', header: 'Company', primary: true, render: (o) => o.company },
              { key: 'subject', header: 'Subject', render: (o) => o.subject },
              {
                key: 'status',
                header: 'Status',
                render: (o) => (
                  <Badge variant={o.status === 'pending_approval' ? 'warning' : 'neutral'}>
                    {o.status.replaceAll('_', ' ')}
                  </Badge>
                ),
              },
              {
                key: 'risk',
                header: 'Risk',
                render: (o) => <Badge variant="warning">{o.risk.toUpperCase()}</Badge>,
              },
            ]}
            rows={outreach}
          />
        </div>
      </section>
    </div>
  )
}

import { Badge, Status, Table } from '../components'
import { audits } from '../data/demo'
import { formatDateTime } from '../lib/format'
import { PageHeader } from '../layout/PageHeader'

export function AuditsPage() {
  return (
    <div className="stack">
      <PageHeader
        eyebrow="Pipeline"
        title="Audits"
        description="Evidence-backed digital presence audits. Findings counts are demo summaries."
      />
      <section className="panel">
        <div className="panel__body panel__body--flush">
          <Table
            columns={[
              { key: 'company', header: 'Company', primary: true, render: (a) => a.company },
              {
                key: 'status',
                header: 'Status',
                render: (a) => <Status value={a.status} />,
              },
              {
                key: 'priority',
                header: 'Priority',
                render: (a) => (
                  <Badge variant={a.priority === 'high' ? 'warning' : 'neutral'}>{a.priority}</Badge>
                ),
              },
              {
                key: 'findings',
                header: 'Findings',
                render: (a) => <span className="mono">{a.findings}</span>,
              },
              {
                key: 'at',
                header: 'Completed',
                render: (a) => <span className="mono">{formatDateTime(a.at)}</span>,
              },
            ]}
            rows={audits}
          />
        </div>
      </section>
    </div>
  )
}

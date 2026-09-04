import { Badge, Table } from '../components'
import { reports } from '../data/demo'
import { formatDateTime } from '../lib/format'
import { PageHeader } from '../layout/PageHeader'

export function ReportsPage() {
  return (
    <div className="stack">
      <PageHeader
        eyebrow="Delivery"
        title="Reports"
        description="CEO reports composed from ledger and ops facts. Listed reports are demo artifacts."
      />
      <section className="panel">
        <div className="panel__body panel__body--flush">
          <Table
            columns={[
              { key: 'title', header: 'Report', primary: true, render: (r) => r.title },
              {
                key: 'period',
                header: 'Period',
                render: (r) => <Badge variant="neutral">{r.period}</Badge>,
              },
              {
                key: 'status',
                header: 'Status',
                render: (r) => <Badge variant="success">{r.status}</Badge>,
              },
              {
                key: 'at',
                header: 'Generated',
                render: (r) => <span className="mono">{formatDateTime(r.at)}</span>,
              },
            ]}
            rows={reports}
          />
        </div>
      </section>
    </div>
  )
}

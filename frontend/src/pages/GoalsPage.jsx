import { Badge, Table } from '../components'
import { goals } from '../data/demo'
import { formatDateTime, pct } from '../lib/format'
import { PageHeader } from '../layout/PageHeader'

export function GoalsPage() {
  return (
    <div className="stack">
      <PageHeader
        eyebrow="Operate"
        title="Goals"
        description="Active targets the Manager and specialists work toward. Demo rows only."
      />
      <section className="panel">
        <div className="panel__body panel__body--flush">
          <Table
            columns={[
              {
                key: 'title',
                header: 'Goal',
                primary: true,
                render: (g) => g.title,
              },
              {
                key: 'status',
                header: 'Status',
                render: (g) => <Badge variant="accent">{g.status.replace('_', ' ')}</Badge>,
              },
              {
                key: 'progress',
                header: 'Progress',
                render: (g) => (
                  <span className="mono">
                    {g.current}/{g.target} ({pct(g.current, g.target)}%)
                  </span>
                ),
              },
              { key: 'owner', header: 'Owner', render: (g) => g.owner },
              {
                key: 'updatedAt',
                header: 'Updated',
                render: (g) => <span className="mono">{formatDateTime(g.updatedAt)}</span>,
              },
            ]}
            rows={goals}
          />
        </div>
      </section>
    </div>
  )
}

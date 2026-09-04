import { Badge, Table } from '../components'
import { leads } from '../data/demo'
import { PageHeader } from '../layout/PageHeader'

export function LeadsPage() {
  return (
    <div className="stack">
      <PageHeader
        eyebrow="Pipeline"
        title="Leads"
        description="Lead lifecycle and score category. Contact fields show only when present in demo data."
      />
      <section className="panel">
        <div className="panel__body panel__body--flush">
          <Table
            columns={[
              { key: 'company', header: 'Company', primary: true, render: (l) => l.company },
              {
                key: 'status',
                header: 'Status',
                render: (l) => <Badge variant="accent">{l.status}</Badge>,
              },
              {
                key: 'scoreCategory',
                header: 'Category',
                render: (l) => <Badge variant="neutral">{l.scoreCategory}</Badge>,
              },
              {
                key: 'email',
                header: 'Email',
                render: (l) => (l.email ? <span className="mono">{l.email}</span> : '—'),
              },
            ]}
            rows={leads}
          />
        </div>
      </section>
    </div>
  )
}

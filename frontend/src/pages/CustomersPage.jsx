import { Badge, Table } from '../components'
import { customers } from '../data/demo'
import { formatDate, formatMoney } from '../lib/format'
import { PageHeader } from '../layout/PageHeader'

export function CustomersPage() {
  return (
    <div className="stack">
      <PageHeader
        eyebrow="Delivery"
        title="Customers"
        description="Accounts under delivery. MRR values are demo ledger placeholders."
      />
      <section className="panel">
        <div className="panel__body panel__body--flush">
          <Table
            columns={[
              { key: 'name', header: 'Customer', primary: true, render: (c) => c.name },
              {
                key: 'status',
                header: 'Status',
                render: (c) => (
                  <Badge variant={c.status === 'active' ? 'success' : 'neutral'}>{c.status}</Badge>
                ),
              },
              {
                key: 'since',
                header: 'Since',
                render: (c) => <span className="mono">{formatDate(c.since)}</span>,
              },
              {
                key: 'mrr',
                header: 'MRR',
                render: (c) => <span className="mono">{formatMoney(c.mrr)}</span>,
              },
            ]}
            rows={customers}
          />
        </div>
      </section>
    </div>
  )
}

import { Badge, MetricStrip, Table } from '../components'
import { finance } from '../data/demo'
import { formatDate, formatMoney } from '../lib/format'
import { PageHeader } from '../layout/PageHeader'

export function FinancePage() {
  return (
    <div className="stack">
      <PageHeader
        eyebrow="Delivery"
        title="Finance"
        description={`${finance.periodLabel}. Amounts are demo ledger entries — not production books.`}
      />
      <MetricStrip
        items={[
          { label: 'Revenue', value: formatMoney(finance.revenue, finance.currency) },
          { label: 'Costs', value: formatMoney(finance.costs, finance.currency) },
          { label: 'Profit', value: formatMoney(finance.profit, finance.currency) },
        ]}
      />
      <section className="panel">
        <div className="panel__header">
          <h3 className="panel__title">Recent entries</h3>
          <Badge variant="demo">Demo</Badge>
        </div>
        <div className="panel__body panel__body--flush">
          <Table
            columns={[
              {
                key: 'kind',
                header: 'Type',
                render: (e) => (
                  <Badge variant={e.kind === 'revenue' ? 'success' : 'neutral'}>{e.kind}</Badge>
                ),
              },
              { key: 'label', header: 'Description', primary: true, render: (e) => e.label },
              {
                key: 'amount',
                header: 'Amount',
                render: (e) => (
                  <span className="mono">
                    {e.kind === 'cost' ? '−' : '+'}
                    {formatMoney(e.amount, finance.currency)}
                  </span>
                ),
              },
              {
                key: 'at',
                header: 'Date',
                render: (e) => <span className="mono">{formatDate(e.at)}</span>,
              },
            ]}
            rows={finance.entries}
          />
        </div>
      </section>
    </div>
  )
}

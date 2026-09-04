import { useMemo, useState } from 'react'
import { Badge, Input, Table } from '../components'
import { companies } from '../data/demo'
import { PageHeader } from '../layout/PageHeader'

export function CompaniesPage() {
  const [q, setQ] = useState('')
  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase()
    if (!needle) return companies
    return companies.filter(
      (c) =>
        c.name.toLowerCase().includes(needle) ||
        (c.domain || '').toLowerCase().includes(needle) ||
        (c.location || '').toLowerCase().includes(needle),
    )
  }, [q])

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Pipeline"
        title="Companies"
        description="Long-term company memory. Scores and domains are demo placeholders."
      />
      <div className="toolbar">
        <Input
          label="Search"
          placeholder="Name, domain, location"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          style={{ minWidth: '220px' }}
        />
      </div>
      <section className="panel">
        <div className="panel__body panel__body--flush">
          <Table
            emptyLabel="No companies match this search"
            columns={[
              { key: 'name', header: 'Company', primary: true, render: (c) => c.name },
              {
                key: 'domain',
                header: 'Domain',
                render: (c) => (c.domain ? <span className="mono">{c.domain}</span> : '—'),
              },
              { key: 'location', header: 'Location', render: (c) => c.location || '—' },
              {
                key: 'status',
                header: 'Status',
                render: (c) => <Badge variant="neutral">{c.status}</Badge>,
              },
              {
                key: 'score',
                header: 'Score',
                render: (c) => (
                  <span className="mono">
                    {c.score} · {c.band}
                  </span>
                ),
              },
            ]}
            rows={rows}
          />
        </div>
      </section>
    </div>
  )
}

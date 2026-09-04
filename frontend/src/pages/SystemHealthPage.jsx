import { Badge, Status, Table } from '../components'
import { pilotMode, systemHealth } from '../data/demo'
import { formatDateTime } from '../lib/format'
import { PageHeader } from '../layout/PageHeader'

export function SystemHealthPage() {
  return (
    <div className="stack">
      <PageHeader
        eyebrow="System"
        title="System health"
        description="API, database, providers, Pilot Mode, and recent n8n workflow executions. Demo status until live APIs are connected."
      />
      <div className="metric-strip">
        <div className="metric-strip__item">
          <div className="metric">
            <div className="metric__label">Pilot Mode</div>
            <div className="metric__value" style={{ fontSize: '1rem' }}>
              <Badge variant="accent">
                {systemHealth.pilotMode ? 'ON' : 'OFF'} · {systemHealth.operatingMode}
              </Badge>
            </div>
          </div>
        </div>
        <div className="metric-strip__item">
          <div className="metric">
            <div className="metric__label">API</div>
            <div className="metric__value" style={{ fontSize: '1rem' }}>
              <Status value={systemHealth.api === 'ok' ? 'succeeded' : 'failed'} label={systemHealth.api} />
            </div>
          </div>
        </div>
        <div className="metric-strip__item">
          <div className="metric">
            <div className="metric__label">Database</div>
            <div className="metric__value" style={{ fontSize: '1rem' }}>
              <Status
                value={systemHealth.database === 'ok' ? 'succeeded' : 'failed'}
                label={systemHealth.database}
              />
            </div>
          </div>
        </div>
        <div className="metric-strip__item">
          <div className="metric">
            <div className="metric__label">n8n</div>
            <div className="metric__value" style={{ fontSize: '1rem' }}>
              <Badge variant="accent">{systemHealth.n8n}</Badge>
            </div>
          </div>
        </div>
      </div>

      <section className="panel">
        <div className="panel__header">
          <h3 className="panel__title">Pilot caps</h3>
        </div>
        <div className="panel__body">
          <p className="muted" style={{ marginTop: 0 }}>
            System stops safely when any cap is reached. Owner is notified for budget warnings, daily
            limits, critical failures, and approval requests.
          </p>
          <ul className="plain-list">
            <li>Companies / day: {pilotMode.limits.maxCompaniesPerDay}</li>
            <li>Audits / day: {pilotMode.limits.maxAuditsPerDay}</li>
            <li>Initial outreach / day: {pilotMode.limits.maxInitialOutreachPerDay}</li>
            <li>Follow-ups / lead: {pilotMode.limits.maxFollowupsPerLead}</li>
            <li>
              Daily spend: {pilotMode.limits.maxDailySpending} {pilotMode.currency}
            </li>
            <li>
              Max expense: {pilotMode.limits.maxSingleExpense} {pilotMode.currency}
            </li>
          </ul>
        </div>
      </section>

      <div className="grid-2">
        <section className="panel">
          <div className="panel__header">
            <h3 className="panel__title">Providers</h3>
          </div>
          <div className="panel__body panel__body--flush">
            <Table
              columns={[
                { key: 'name', header: 'Provider', primary: true, render: (p) => p.name },
                {
                  key: 'configured',
                  header: 'Configured',
                  render: (p) => (p.configured ? 'Yes' : 'No'),
                },
                {
                  key: 'status',
                  header: 'Status',
                  render: (p) => <Status value={p.status === 'ok' ? 'succeeded' : p.status} />,
                },
              ]}
              rows={systemHealth.providers}
            />
          </div>
        </section>

        <section className="panel">
          <div className="panel__header">
            <h3 className="panel__title">Recent workflows</h3>
            <Badge variant="demo">Demo</Badge>
          </div>
          <div className="panel__body panel__body--flush">
            <Table
              columns={[
                {
                  key: 'name',
                  header: 'Workflow',
                  primary: true,
                  render: (w) => <span className="mono">{w.name}</span>,
                },
                {
                  key: 'status',
                  header: 'Status',
                  render: (w) => <Status value={w.status} />,
                },
                {
                  key: 'at',
                  header: 'When',
                  render: (w) => <span className="mono">{formatDateTime(w.at)}</span>,
                },
              ]}
              rows={systemHealth.recentWorkflows}
            />
          </div>
        </section>
      </div>
    </div>
  )
}

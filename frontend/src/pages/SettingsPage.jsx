import { useState } from 'react'
import { Badge, Button, Input, Modal, Select } from '../components'
import { pilotMode, settings } from '../data/demo'
import { useToast } from '../hooks/useToast'
import { PageHeader } from '../layout/PageHeader'

export function SettingsPage() {
  const { push } = useToast()
  const [form, setForm] = useState({
    env: settings.env,
    operatingMode: settings.operatingMode,
    maxOutbound: String(settings.maxOutboundPerDay),
    maxCompanies: String(settings.maxCompaniesPerDay),
    maxAudits: String(settings.maxAuditsPerDay),
    maxInitialOutreach: String(settings.maxInitialOutreachPerDay),
    maxFollowups: String(settings.maxFollowups),
    approvalTtl: String(settings.approvalTtlHours),
    dailyBudget: String(settings.dailyBudget),
    maxSingleExpense: String(settings.maxSingleExpense),
  })
  const [showHelp, setShowHelp] = useState(false)

  const onChange = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }))

  return (
    <div className="stack">
      <PageHeader
        eyebrow="System"
        title="Settings"
        description="Pilot Mode safety limits mirrored from backend configuration. Saving here updates the demo form only."
        actions={
          <Button variant="ghost" onClick={() => setShowHelp(true)}>
            About settings
          </Button>
        }
      />

      <section className="panel">
        <div className="panel__header">
          <h3 className="panel__title">Operating mode</h3>
          <Badge variant="accent">Pilot Mode</Badge>
        </div>
        <div className="panel__body">
          <p className="muted" style={{ marginTop: 0 }}>
            Production mode cannot be enabled accidentally. Backend requires{' '}
            <code>ALLOW_PRODUCTION_MODE=true</code> together with{' '}
            <code>OPERATING_MODE=production</code>.
          </p>
          <div className="filter-row" style={{ maxWidth: '32rem', flexDirection: 'column', alignItems: 'stretch' }}>
            <Select
              label="Operating mode"
              value={form.operatingMode}
              onChange={onChange('operatingMode')}
              options={[
                { value: 'pilot', label: 'Pilot (safe default)' },
                { value: 'production', label: 'Production (locked without unlock flag)' },
              ]}
            />
            <Select
              label="Environment"
              value={form.env}
              onChange={onChange('env')}
              options={[
                { value: 'development', label: 'Development' },
                { value: 'staging', label: 'Staging' },
                { value: 'production', label: 'Production' },
              ]}
            />
            <Input label="API prefix" value={settings.apiPrefix} readOnly />
          </div>
        </div>
      </section>

      <section className="panel">
        <div className="panel__header">
          <h3 className="panel__title">Pilot limits</h3>
        </div>
        <div className="panel__body">
          <div className="filter-row" style={{ maxWidth: '32rem', flexDirection: 'column', alignItems: 'stretch' }}>
            <Input
              label="Max companies / day"
              type="number"
              value={form.maxCompanies}
              onChange={onChange('maxCompanies')}
            />
            <Input
              label="Max audits / day"
              type="number"
              value={form.maxAudits}
              onChange={onChange('maxAudits')}
            />
            <Input
              label="Max initial outreach / day"
              type="number"
              value={form.maxInitialOutreach}
              onChange={onChange('maxInitialOutreach')}
            />
            <Input
              label="Max follow-ups / lead"
              type="number"
              value={form.maxFollowups}
              onChange={onChange('maxFollowups')}
            />
            <Input
              label={`Daily budget (${settings.currency})`}
              type="number"
              value={form.dailyBudget}
              onChange={onChange('dailyBudget')}
            />
            <Input
              label={`Max single expense (${settings.currency})`}
              type="number"
              value={form.maxSingleExpense}
              onChange={onChange('maxSingleExpense')}
            />
            <Input
              label="Approval TTL (hours)"
              type="number"
              value={form.approvalTtl}
              onChange={onChange('approvalTtl')}
            />
            <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem' }}>
              <Button
                variant="primary"
                onClick={() => push('Demo settings saved locally — not written to backend.', 'info')}
              >
                Save (demo)
              </Button>
            </div>
          </div>
        </div>
      </section>

      <section className="panel">
        <div className="panel__header">
          <h3 className="panel__title">Approvals required in Pilot Mode</h3>
        </div>
        <div className="panel__body">
          <ul className="plain-list">
            {pilotMode.approvalRequired.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      </section>

      <Modal open={showHelp} title="Settings scope" onClose={() => setShowHelp(false)}>
        <p>
          Live limits are enforced by LimitService, BudgetGuard, and ExecutionGuard in the backend.
          This page is an operator shell; it does not mutate secrets or bypass approvals.
        </p>
      </Modal>
    </div>
  )
}

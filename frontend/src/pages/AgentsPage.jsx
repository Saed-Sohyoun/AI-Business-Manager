import { useState } from 'react'
import { AgentStatus, Badge, Drawer, EmptyState, Select } from '../components'
import { agents } from '../data/demo'
import { formatDateTime } from '../lib/format'
import { PageHeader } from '../layout/PageHeader'

export function AgentsPage() {
  const [filter, setFilter] = useState('all')
  const [selected, setSelected] = useState(null)
  const filtered =
    filter === 'all' ? agents : agents.filter((a) => a.status === filter)

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Operate"
        title="Agents"
        description="Specialist workers orchestrated by the Manager. Status reflects last known demo run."
      />
      <div className="toolbar">
        <Select
          label="Status"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          options={[
            { value: 'all', label: 'All' },
            { value: 'running', label: 'Running' },
            { value: 'succeeded', label: 'Succeeded' },
            { value: 'failed', label: 'Failed' },
            { value: 'pending', label: 'Pending' },
            { value: 'idle', label: 'Idle' },
          ]}
        />
        <div className="toolbar__spacer" />
        <Badge variant="demo">Demo</Badge>
      </div>
      <section className="panel">
        <div className="panel__body">
          {filtered.length === 0 ? (
            <EmptyState title="No agents match" description="Try another status filter." />
          ) : (
            filtered.map((agent) => (
              <button
                key={agent.id}
                type="button"
                className="agent-row-btn"
                onClick={() => setSelected(agent)}
              >
                <AgentStatus agent={agent} />
              </button>
            ))          )}
        </div>
      </section>

      <Drawer
        open={Boolean(selected)}
        title={selected?.name || 'Agent'}
        onClose={() => setSelected(null)}
      >
        {selected ? (
          <div className="stack" style={{ gap: '1rem' }}>
            <p>
              <strong>Status:</strong> {selected.status}
            </p>
            <p>
              <strong>Last task:</strong> {selected.task}
            </p>
            <p>
              <strong>Last run:</strong> {formatDateTime(selected.lastRun)}
            </p>
            <p className="field__hint">
              Agents never bypass ApprovalService for YELLOW/RED actions. Live detail will come from agent_runs.
            </p>
          </div>
        ) : null}
      </Drawer>
    </div>
  )
}

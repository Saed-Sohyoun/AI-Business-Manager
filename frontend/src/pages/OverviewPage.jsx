import { Link } from 'react-router-dom'
import {
  ActivityTimeline,
  AgentStatus,
  Badge,
  MetricStrip,
} from '../components'
import { overview, agents } from '../data/demo'
import { formatMoney, pct } from '../lib/format'
import { PageHeader } from '../layout/PageHeader'

export function OverviewPage() {
  const { objective, finance, pipeline, agents: agentCounts, approvals, alerts, opportunities, activity, revenueSeries } =
    overview
  const maxBar = Math.max(...revenueSeries)

  return (
    <div className="stack">
      <PageHeader
        eyebrow="Now"
        title="What is happening"
        description="Business objective, money, pipeline, agents, and items that need attention — demo figures until live APIs are wired."
        actions={
          <Link to="/approvals" className="btn btn--primary">
            Review approvals
          </Link>
        }
      />

      <section className="objective-block" aria-labelledby="objective-heading">
        <div className="objective-block__label" id="objective-heading">
          Current business objective
        </div>
        <p className="objective-block__goal">{objective.goal}</p>
        <div className="objective-block__progress">
          <div className="progress">
            <div className="progress__meta">
              <span>
                {objective.current} / {objective.target} {objective.unit}
              </span>
              <span className="mono">{pct(objective.current, objective.target)}%</span>
            </div>
            <div
              className="progress__track"
              role="progressbar"
              aria-valuenow={objective.current}
              aria-valuemin={0}
              aria-valuemax={objective.target}
            >
              <div
                className="progress__fill"
                style={{ width: `${pct(objective.current, objective.target)}%` }}
              />
            </div>
          </div>
        </div>
      </section>

      <MetricStrip
        items={[
          { label: `Revenue (${finance.periodLabel})`, value: formatMoney(finance.revenue, finance.currency) },
          { label: 'Costs', value: formatMoney(finance.costs, finance.currency) },
          { label: 'Profit', value: formatMoney(finance.profit, finance.currency), delta: 'Demo MTD', deltaTone: 'up' },
          { label: 'Qualified leads', value: String(pipeline.qualified) },
          {
            label: 'Approvals pending',
            value: String(approvals.pending),
            delta: approvals.expiringSoon ? `${approvals.expiringSoon} expiring soon` : undefined,
            deltaTone: approvals.expiringSoon ? 'down' : undefined,
          },
          {
            label: 'Active agents',
            value: String(agentCounts.active),
            delta: `${agentCounts.failed} failed · ${agentCounts.idle} idle`,
          },
        ]}
      />

      <div className="grid-2">
        <div className="stack">
          <section className="panel">
            <div className="panel__header">
              <h3 className="panel__title">Pipeline</h3>
              <Badge variant="neutral">Demo</Badge>
            </div>
            <div className="panel__body panel__body--flush">
              <table className="table">
                <thead>
                  <tr>
                    <th>Stage</th>
                    <th>Count</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td className="table__primary">Prospects</td>
                    <td className="mono">{pipeline.prospects}</td>
                  </tr>
                  <tr>
                    <td className="table__primary">Contacted</td>
                    <td className="mono">{pipeline.contacted}</td>
                  </tr>
                  <tr>
                    <td className="table__primary">Qualified</td>
                    <td className="mono">{pipeline.qualified}</td>
                  </tr>
                  <tr>
                    <td className="table__primary">Customers</td>
                    <td className="mono">{pipeline.customers}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          <section className="panel">
            <div className="panel__header">
              <h3 className="panel__title">Revenue trend (demo weeks)</h3>
            </div>
            <div className="panel__body">
              <div className="sparkline" role="img" aria-label="Weekly revenue bars, demo only">
                {revenueSeries.map((v, i) => (
                  <div
                    key={i}
                    className={`sparkline__bar${i === revenueSeries.length - 1 ? '' : ' sparkline__bar--muted'}`}
                    style={{ height: `${Math.max(8, (v / maxBar) * 100)}%` }}
                    title={`${v}k`}
                  />
                ))}
              </div>
              <p className="field__hint" style={{ marginTop: '0.75rem' }}>
                Bars are illustrative demo series — not live ledger data.
              </p>
            </div>
          </section>

          <section className="panel">
            <div className="panel__header">
              <h3 className="panel__title">Important alerts</h3>
              <Link to="/system">System</Link>
            </div>
            <div className="panel__body">
              <div className="alert-row">
                {alerts.map((a) => (
                  <div key={a.id} className={`alert-item alert-item--${a.severity}`}>
                    <div>
                      <div className="alert-item__title">{a.title}</div>
                      <div className="alert-item__body">{a.body}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </section>
        </div>

        <div className="stack">
          <section className="panel">
            <div className="panel__header">
              <h3 className="panel__title">Opportunities</h3>
            </div>
            <div className="panel__body">
              <ul className="data-list">
                {opportunities.map((o) => (
                  <li key={o.id} className="data-list__item">
                    <div>
                      <div className="data-list__title">{o.title}</div>
                      <div className="data-list__meta">
                        {typeof o.detail === 'number' ? `${o.detail} ${o.label}` : o.detail}
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          </section>

          <section className="panel">
            <div className="panel__header">
              <h3 className="panel__title">Agents</h3>
              <Link to="/agents">All agents</Link>
            </div>
            <div className="panel__body">
              {agents.slice(0, 5).map((agent) => (
                <AgentStatus key={agent.id} agent={agent} />
              ))}
            </div>
          </section>

          <section className="panel">
            <div className="panel__header">
              <h3 className="panel__title">Recent activity</h3>
            </div>
            <div className="panel__body">
              <ActivityTimeline items={activity} />
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}

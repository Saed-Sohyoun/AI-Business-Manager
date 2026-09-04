import { Status } from './Status'
import { formatDateTime } from '../lib/format'

export function AgentStatus({ agent }) {
  return (
    <div className="agent-status">
      <div className="agent-status__name">{agent.name}</div>
      <Status value={agent.status} />
      <div className="agent-status__task">
        {agent.task} · last {formatDateTime(agent.lastRun)}
      </div>
    </div>
  )
}

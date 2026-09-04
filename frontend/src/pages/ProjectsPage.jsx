import { Badge, Status, Table } from '../components'
import { projects } from '../data/demo'
import { PageHeader } from '../layout/PageHeader'

export function ProjectsPage() {
  return (
    <div className="stack">
      <PageHeader
        eyebrow="Delivery"
        title="Projects"
        description="Delivery projects and task progress. Blocked items need human attention."
      />
      <section className="panel">
        <div className="panel__body panel__body--flush">
          <Table
            columns={[
              { key: 'name', header: 'Project', primary: true, render: (p) => p.name },
              { key: 'customer', header: 'Customer', render: (p) => p.customer },
              {
                key: 'status',
                header: 'Status',
                render: (p) =>
                  p.status === 'blocked' ? (
                    <Status value="blocked" />
                  ) : p.status === 'in_progress' ? (
                    <Status value="running" label="In progress" />
                  ) : (
                    <Badge variant="neutral">{p.status}</Badge>
                  ),
              },
              {
                key: 'tasks',
                header: 'Tasks',
                render: (p) => (
                  <span className="mono">
                    {p.tasksDone} done · {p.tasksOpen} open
                  </span>
                ),
              },
            ]}
            rows={projects}
          />
        </div>
      </section>
    </div>
  )
}

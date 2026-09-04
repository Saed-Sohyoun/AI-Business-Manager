import { Button } from './Button'

export function EmptyState({ title, description, actionLabel, onAction }) {
  return (
    <div className="state-block">
      <h3 className="state-block__title">{title}</h3>
      {description ? <p className="state-block__desc">{description}</p> : null}
      {actionLabel && onAction ? (
        <div className="state-block__actions">
          <Button variant="secondary" onClick={onAction}>
            {actionLabel}
          </Button>
        </div>
      ) : null}
    </div>
  )
}

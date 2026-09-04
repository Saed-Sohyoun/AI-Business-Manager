import { Button } from './Button'

export function ErrorState({ title = 'Something went wrong', description, onRetry }) {
  return (
    <div className="state-block error-state">
      <h3 className="state-block__title">{title}</h3>
      {description ? <p className="state-block__desc">{description}</p> : null}
      {onRetry ? (
        <div className="state-block__actions">
          <Button variant="secondary" onClick={onRetry}>
            Retry
          </Button>
        </div>
      ) : null}
    </div>
  )
}

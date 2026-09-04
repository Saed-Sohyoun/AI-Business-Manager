const LABELS = {
  idle: 'Idle',
  running: 'Running',
  succeeded: 'Succeeded',
  success: 'Success',
  failed: 'Failed',
  error: 'Error',
  pending: 'Pending',
  blocked: 'Blocked',
  ok: 'OK',
  degraded: 'Degraded',
  unconfigured: 'Not configured',
}

export function Status({ value, label }) {
  const key = String(value || 'idle').toLowerCase()
  return (
    <span className={`status status--${key}`}>
      <span className="status__dot" aria-hidden="true" />
      <span>{label || LABELS[key] || value}</span>
    </span>
  )
}

export function Metric({ label, value, delta, deltaTone }) {
  return (
    <div className="metric">
      <div className="metric__label">{label}</div>
      <div className="metric__value">{value}</div>
      {delta ? (
        <div className={`metric__delta${deltaTone ? ` metric__delta--${deltaTone}` : ''}`}>{delta}</div>
      ) : null}
    </div>
  )
}

export function MetricStrip({ items }) {
  return (
    <div className="metric-strip" role="group" aria-label="Key metrics">
      {items.map((item) => (
        <div key={item.label} className="metric-strip__item">
          <Metric {...item} />
        </div>
      ))}
    </div>
  )
}

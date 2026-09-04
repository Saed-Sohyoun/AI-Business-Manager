import { formatDateTime } from '../lib/format'

export function ActivityTimeline({ items }) {
  if (!items?.length) return null
  return (
    <ol className="timeline">
      {items.map((item) => (
        <li key={item.id} className="timeline__item">
          <div className="timeline__rail" aria-hidden="true">
            <span className="timeline__dot" />
            <span className="timeline__line" />
          </div>
          <div className="timeline__content">
            <div className="timeline__title">{item.title}</div>
            <div className="timeline__time">{formatDateTime(item.at)}</div>
            {item.detail ? <div className="timeline__detail">{item.detail}</div> : null}
          </div>
        </li>
      ))}
    </ol>
  )
}

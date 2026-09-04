export function DataList({ items }) {
  if (!items?.length) return null
  return (
    <ul className="data-list">
      {items.map((item) => (
        <li key={item.id} className="data-list__item">
          <div>
            <div className="data-list__title">{item.title}</div>
            {item.meta ? <div className="data-list__meta">{item.meta}</div> : null}
          </div>
          {item.aside ? <div>{item.aside}</div> : null}
        </li>
      ))}
    </ul>
  )
}

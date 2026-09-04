export function Table({ columns, rows, emptyLabel = 'No rows' }) {
  if (!rows?.length) {
    return (
      <div className="state-block">
        <p className="state-block__title">{emptyLabel}</p>
      </div>
    )
  }

  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            {columns.map((col) => (
              <th key={col.key} scope="col" style={col.width ? { width: col.width } : undefined}>
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id ?? JSON.stringify(row)}>
              {columns.map((col) => (
                <td key={col.key} className={col.primary ? 'table__primary' : undefined}>
                  {col.render ? col.render(row) : row[col.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function Skeleton({ rows = 3, className = "" }) {
  return (
    <div className={`skeleton-block ${className}`.trim()} aria-hidden="true">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="skeleton-row" style={{ width: `${88 - i * 8}%` }} />
      ))}
    </div>
  );
}

export function SkeletonMetrics({ count = 4 }) {
  return (
    <div className="metric-strip" aria-busy="true" aria-label="Loading metrics">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="metric metric--skeleton">
          <div className="skeleton-row skeleton-row--sm" style={{ width: "40%" }} />
          <div className="skeleton-row" style={{ width: "55%", marginTop: "0.5rem" }} />
        </div>
      ))}
    </div>
  );
}

import { useId, useState } from "react";

export function AdvancedDetails({ title = "Advanced details", children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  const panelId = useId();
  return (
    <div className="advanced-details">
      <button
        type="button"
        className="advanced-details__toggle"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((v) => !v)}
      >
        {open ? "Hide" : "Show"} {title}
      </button>
      {open ? (
        <div id={panelId} className="advanced-details__body">
          {children}
        </div>
      ) : null}
    </div>
  );
}

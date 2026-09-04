import { useState } from "react";
import { Badge } from "./Badge";
import { Button } from "./Button";

/**
 * Restrained system mode strip — expandable details.
 */
export function StatusStrip({
  dataMode,
  systemStatus,
  onToggleMode,
  loading,
}) {
  const [open, setOpen] = useState(false);

  const mode = systemStatus?.system_mode || "normal";
  const badges = [];

  if (dataMode === "demo") {
    badges.push({ key: "demo", label: "DEMO", detail: "Sample data", variant: "demo" });
  } else {
    badges.push({
      key: "live",
      label: systemStatus?.pilot_mode ? "PILOT" : "LIVE",
      detail: systemStatus?.pilot_mode ? "Real data · limits active" : "Real data",
      variant: "accent",
    });
  }

  if (mode === "paused_by_owner") {
    badges.push({
      key: "paused",
      label: "PAUSED",
      detail: "AI operations paused",
      variant: "danger",
    });
  } else if (mode === "safe_mode") {
    badges.push({
      key: "safe",
      label: "SAFE MODE",
      detail: "External actions restricted",
      variant: "warning",
    });
  }

  if (systemStatus?.production_locked) {
    badges.push({
      key: "prod",
      label: "Production locked",
      detail: "Production mode cannot be enabled accidentally",
      variant: "neutral",
    });
  }

  const healthLine = providerHealthLine(systemStatus?.provider_health);

  return (
    <div className="status-strip" role="status">
      <div className="status-strip__row">
        <div className="status-strip__badges">
          {badges.map((b) => (
            <Badge key={b.key} variant={b.variant}>
              {b.label}
            </Badge>
          ))}
          {healthLine ? <span className="status-strip__health">{healthLine}</span> : null}
          {loading ? <span className="status-strip__hint">Updating…</span> : null}
        </div>
        <div className="status-strip__actions">
          {onToggleMode ? (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => onToggleMode(dataMode === "demo" ? "live" : "demo")}
            >
              Use {dataMode === "demo" ? "live" : "demo"} data
            </Button>
          ) : null}
          <Button
            size="sm"
            variant="ghost"
            aria-expanded={open}
            onClick={() => setOpen((v) => !v)}
          >
            {open ? "Hide details" : "Details"}
          </Button>
        </div>
      </div>
      {open ? (
        <div className="status-strip__details">
          <ul className="status-strip__list">
            {badges.map((b) => (
              <li key={`${b.key}-d`}>
                <strong>{b.label}</strong> — {b.detail}
              </li>
            ))}
            {healthLine ? <li>{healthLine}</li> : null}
            {systemStatus ? (
              <>
                <li>
                  AI operations: {systemStatus.ai_operations ? "on" : "off"} · Outbound:{" "}
                  {systemStatus.outbound ? "on" : "off"} · Spending:{" "}
                  {systemStatus.spending ? "on" : "off"} · Browser:{" "}
                  {systemStatus.browser_automation ? "on" : "off"}
                </li>
                {systemStatus.safe_mode_reason ? (
                  <li>Safe Mode reason: {systemStatus.safe_mode_reason}</li>
                ) : null}
                {systemStatus.pause_reason ? (
                  <li>Pause reason: {systemStatus.pause_reason}</li>
                ) : null}
                <li>
                  Budget today: {systemStatus.current_budget_usage} / {systemStatus.budget_limit}{" "}
                  {systemStatus.currency || "EUR"}
                </li>
              </>
            ) : null}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

/**
 * Quiet one-line health from optional provider_health payload.
 * @param {unknown} health
 * @returns {string|null}
 */
function providerHealthLine(health) {
  if (!health) return null;
  if (typeof health === "string") {
    const s = health.toLowerCase();
    if (s === "ok" || s === "healthy" || s === "operational") return "System operational";
    if (s.includes("degrad")) return "Research temporarily degraded";
    return health;
  }
  if (typeof health !== "object") return null;

  const overall = String(health.overall || health.status || health.state || "").toLowerCase();
  if (overall === "ok" || overall === "healthy" || overall === "operational") {
    return "System operational";
  }
  if (overall.includes("degrad") || overall === "partial") {
    return "Research temporarily degraded";
  }

  const providers = health.providers || health.items;
  if (Array.isArray(providers)) {
    const degraded = providers.some((p) => {
      const st = String(p?.status || p?.state || "").toLowerCase();
      return st.includes("degrad") || st === "down" || st === "open" || st === "circuit_open";
    });
    if (degraded) return "Research temporarily degraded";
    if (providers.length) return "System operational";
  }

  if (overall) return "Research temporarily degraded";
  return null;
}

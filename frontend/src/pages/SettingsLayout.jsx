import { Link, NavLink, Outlet } from "react-router-dom";
import { Badge, Button } from "../components";
import { useDataMode } from "../context/DataModeContext";
import { PageHeader } from "../layout/PageHeader";

const SETTINGS_TABS = [
  { to: "/settings", end: true, label: "General" },
  { to: "/settings/system", label: "System controls" },
  { to: "/settings/ai-team", label: "AI Team" },
  { to: "/settings/advanced", label: "Advanced" },
];

export function SettingsLayout() {
  const { isDemo } = useDataMode();
  return (
    <div className="stack">
      <PageHeader
        eyebrow="System"
        title="Settings"
        description={
          isDemo
            ? "Demo mode — system controls require live data."
            : "Owner controls, pilot limits, and technical views for your digital team."
        }
      />
      <nav className="settings-tabs" aria-label="Settings sections">
        {SETTINGS_TABS.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            end={tab.end}
            className={({ isActive }) => `settings-tabs__link${isActive ? " is-active" : ""}`}
          >
            {tab.label}
          </NavLink>
        ))}
      </nav>
      <Outlet />
    </div>
  );
}

export function SettingsGeneralPage() {
  const { mode, setMode, hasOwnerKey, hasLiveAuthCapable, isLive } = useDataMode();
  return (
    <div className="stack">
      <section className="panel">
        <div className="panel__header">
          <h3 className="panel__title">Data source</h3>
          <Badge variant={isLive ? "accent" : "demo"}>{isLive ? "Live" : "Demo"}</Badge>
        </div>
        <div className="panel__body">
          <p className="muted" style={{ marginTop: 0 }}>
            Demo shows sample figures for walkthroughs. Live calls the owner API and never falls back
            to sample metrics on failure. Sign in for session auth, or use an emergency API key for
            local development.
          </p>
          <div className="filter-row">
            <Button
              variant={mode === "demo" ? "primary" : "secondary"}
              onClick={() => setMode("demo")}
            >
              Demo
            </Button>
            <Button
              variant={mode === "live" ? "primary" : "secondary"}
              onClick={() => setMode("live")}
            >
              Live / Pilot
            </Button>
          </div>
          {hasLiveAuthCapable || hasOwnerKey ? (
            <p className="field__hint">
              Emergency <code>VITE_OWNER_API_KEY</code> is configured for local live access. Prefer
              owner sign-in for normal use.
            </p>
          ) : (
            <p className="field__hint">
              Live mode uses owner sign-in. You will be asked to sign in when switching to live
              without a session.
            </p>
          )}
        </div>
      </section>

      <section className="panel">
        <div className="panel__header">
          <h3 className="panel__title">Production lock</h3>
        </div>
        <div className="panel__body">
          <p style={{ marginTop: 0 }}>
            Production mode stays locked. Unlocking requires an explicit backend configuration change
            — it cannot be enabled from this dashboard.
          </p>
          <Link to="/settings/system" className="btn btn--secondary">
            Open system controls
          </Link>
        </div>
      </section>
    </div>
  );
}

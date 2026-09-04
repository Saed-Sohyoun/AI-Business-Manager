import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useEffect, useState } from "react";
import { NAV_SECTIONS, pageTitleForPath } from "../nav";
import { StatusStrip } from "../components";
import { useDataMode } from "../context/DataModeContext";
import { useAsyncResource } from "../hooks/useAsyncResource";
import * as ownerApi from "../api/owner.js";

export function AppShell() {
  const [navOpen, setNavOpen] = useState(false);
  const location = useLocation();
  const title = pageTitleForPath(location.pathname);
  const { mode, setMode, isLive } = useDataMode();

  const statusLoader = () => ownerApi.getSystemStatus();
  const { data: systemStatus, loading: statusLoading, reload: reloadStatus } = useAsyncResource(
    statusLoader,
    { enabled: isLive, deps: [isLive, location.pathname] },
  );

  useEffect(() => {
    setNavOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") setNavOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className={`app-shell${navOpen ? " app-shell--nav-open" : ""}`}>
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <div
        className="nav-overlay"
        onClick={() => setNavOpen(false)}
        aria-hidden={!navOpen}
      />
      <aside className="sidebar" aria-label="Primary">
        <div className="sidebar__brand">
          <span className="sidebar__mark">Business OS</span>
          <span className="sidebar__mark-sub">owner</span>
        </div>
        <nav className="sidebar__nav">
          {NAV_SECTIONS.map((section) => (
            <div key={section.label}>
              <div className="sidebar__section-label">{section.label}</div>
              {section.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) =>
                    `sidebar__link${isActive ? " sidebar__link--active" : ""}`
                  }
                >
                  {item.label}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="sidebar__footer">Your digital team · database is source of truth</div>
      </aside>

      <div className="main-column">
        <StatusStrip
          dataMode={mode}
          systemStatus={isLive ? systemStatus : null}
          loading={isLive && statusLoading}
          onToggleMode={(next) => {
            setMode(next);
            if (next === "live") reloadStatus();
          }}
        />
        <header className="topbar">
          <div className="topbar__left">
            <button
              type="button"
              className="topbar__menu"
              aria-label="Open navigation"
              aria-expanded={navOpen}
              onClick={() => setNavOpen(true)}
            >
              <span className="topbar__menu-icon" aria-hidden="true">
                <span />
                <span />
                <span />
              </span>
            </button>
            <h1 className="topbar__title">{title}</h1>
          </div>
        </header>
        <main className="content" id="main-content">
          <Outlet context={{ systemStatus, reloadStatus }} />
        </main>
      </div>
    </div>
  );
}

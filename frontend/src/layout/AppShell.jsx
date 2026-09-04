import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { NAV_SECTIONS, PAGE_TITLES } from '../nav'
import { Badge } from '../components'
import { demoMeta, pilotMode } from '../data/demo'

export function AppShell() {
  const [navOpen, setNavOpen] = useState(false)
  const location = useLocation()
  const title = PAGE_TITLES[location.pathname] || 'Business OS'

  useEffect(() => {
    setNavOpen(false)
  }, [location.pathname])

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') setNavOpen(false)
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])

  return (
    <div className={`app-shell${navOpen ? ' app-shell--nav-open' : ''}`}>
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
          <span className="sidebar__mark-sub">ops</span>
        </div>
        <nav className="sidebar__nav">
          {NAV_SECTIONS.map((section) => (
            <div key={section.label}>
              <div className="sidebar__section-label">{section.label}</div>
              {section.items.map((item, index) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) =>
                    `sidebar__link${isActive ? ' sidebar__link--active' : ''}`
                  }
                >
                  <span className="sidebar__link-index" aria-hidden="true">
                    {String(index + 1).padStart(2, '0')}
                  </span>
                  {item.label}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="sidebar__footer">Backend remains source of truth</div>
      </aside>

      <div className="main-column">
        <div className="demo-banner" role="status">
          <span className="demo-banner__mark">DEMO</span>
          <span>{demoMeta.note}</span>
        </div>
        {pilotMode.enabled ? (
          <div className="pilot-banner" role="status">
            <span className="pilot-banner__mark">PILOT MODE</span>
            <span>
              Caps active: {pilotMode.limits.maxCompaniesPerDay} companies/day ·{' '}
              {pilotMode.limits.maxAuditsPerDay} audits/day ·{' '}
              {pilotMode.limits.maxInitialOutreachPerDay} outreach/day ·{' '}
              {pilotMode.limits.maxDailySpending} {pilotMode.currency}/day · max expense{' '}
              {pilotMode.limits.maxSingleExpense} {pilotMode.currency}. Production mode is locked
              until explicitly unlocked.
            </span>
          </div>
        ) : null}
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
          <div className="topbar__right">
            <Badge variant="accent">Pilot Mode</Badge>
            <Badge variant="demo">Demo dataset</Badge>
            <span className="topbar__meta">{demoMeta.asOf.slice(0, 10)}</span>
          </div>
        </header>
        <main className="content" id="main-content">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

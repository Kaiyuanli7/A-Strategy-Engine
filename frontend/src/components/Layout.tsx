import { NavLink, Outlet } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { api } from '@/api/client'
import type { Health } from '@/types/api'

export default function Layout() {
  const [health, setHealth] = useState<Health | null>(null)

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null))
  }, [])

  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-white border-b border-ink-100 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-6 py-3 flex items-center gap-6">
          <div className="font-semibold text-lg">A-Strategy-Engine</div>
          <nav className="flex gap-1 text-sm">
            <NavLink
              to="/"
              end
              className={({ isActive }) =>
                'nav-link' + (isActive ? ' nav-link-active' : '')
              }
            >
              Factor Lab
            </NavLink>
            <NavLink
              to="/correlation"
              className={({ isActive }) =>
                'nav-link' + (isActive ? ' nav-link-active' : '')
              }
            >
              Correlation
            </NavLink>
            <NavLink
              to="/portfolio"
              className={({ isActive }) =>
                'nav-link' + (isActive ? ' nav-link-active' : '')
              }
            >
              Portfolio
            </NavLink>
            <NavLink
              to="/walkforward"
              className={({ isActive }) =>
                'nav-link' + (isActive ? ' nav-link-active' : '')
              }
            >
              Walk-Forward
            </NavLink>
          </nav>
          <div className="ml-auto text-xs text-ink-400 font-mono">
            {health ? (
              <span>
                v{health.version} · {health.cached_stocks} stocks · {health.cached_runs} runs
              </span>
            ) : (
              <span className="text-accent-red">API offline</span>
            )}
          </div>
        </div>
      </header>
      <main className="flex-1 max-w-7xl w-full mx-auto px-6 py-6">
        <Outlet />
      </main>
    </div>
  )
}

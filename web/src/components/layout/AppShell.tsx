import type React from 'react';
import { Settings2 } from 'lucide-react';
import { NavLink, Outlet } from 'react-router-dom';
import { ThemeToggle } from '../theme/ThemeToggle';
import { cn } from '../../utils/cn';

const NAV_ITEMS = [
  { to: '/', label: '工作台' },
  { to: '/information-watch', label: '信息观察池' },
  { to: '/theme-factor-scans', label: '主题因子' },
  { to: '/theme-picker', label: '主题选股' },
  { to: '/stock-query', label: '单股查询' },
  { to: '/etf-query', label: '单 ETF' },
  { to: '/watchlist', label: '观察池' },
  { to: '/deep-analysis', label: '深度分析' },
] as const;

export const AppShell: React.FC = () => {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-40 px-3 pt-3 md:px-5 lg:px-6">
        <div className="mx-auto max-w-[1880px]">
          <div className="shell-header-surface px-3 py-3 md:px-4 md:py-3.5">
            <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
              <div className="flex items-center justify-between gap-3 xl:min-w-[260px]">
                <NavLink to="/" className="flex min-w-0 items-center gap-3">
                  <div className="shell-brand-mark">
                    <span className="text-[11px] font-semibold tracking-[0.16em]">TP</span>
                  </div>
                  <div className="min-w-0">
                    <p className="shell-brand-eyebrow">主题选股 · 工作台</p>
                    <h1 className="shell-brand-title">Theme Picker</h1>
                  </div>
                </NavLink>

                <div className="flex items-center gap-2 xl:hidden">
                  <ThemeToggle compact />
                  <NavLink to="/settings" className="shell-icon-button" aria-label="设置" title="设置">
                    <Settings2 className="h-4 w-4" />
                  </NavLink>
                </div>
              </div>

              <nav className="overflow-x-auto xl:flex-1 xl:px-4">
                <div className="shell-nav">
                  {NAV_ITEMS.map((item) => (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      end={item.to === '/'}
                      className={({ isActive }) =>
                        cn('shell-nav-link', isActive ? 'shell-nav-link-active' : 'shell-nav-link-inactive')
                      }
                    >
                      <span>{item.label}</span>
                    </NavLink>
                  ))}
                </div>
              </nav>

              <div className="hidden items-center gap-3 xl:flex">
                <div className="shell-status" aria-label="实时数据状态">
                  <span className="shell-status-dot" aria-hidden="true" />
                  <span>实时数据 · 已同步</span>
                </div>
                <ThemeToggle compact />
                <NavLink to="/settings" className="shell-icon-button" aria-label="设置" title="设置">
                  <Settings2 className="h-4 w-4" />
                </NavLink>
              </div>
            </div>
          </div>
        </div>
      </header>

      <Outlet />
    </div>
  );
};

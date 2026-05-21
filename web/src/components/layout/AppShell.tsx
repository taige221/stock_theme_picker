import type React from 'react';
import { Bell, House, Layers3, Newspaper, Orbit, Radar, Settings2, Sparkles, Star, WalletCards } from 'lucide-react';
import { NavLink, Outlet } from 'react-router-dom';
import { ThemeToggle } from '../theme/ThemeToggle';
import { Badge } from '../common';
import { cn } from '../../utils/cn';

const NAV_ITEMS = [
  { to: '/', label: '工作台', icon: House },
  { to: '/theme-factor-scans', label: '主题因子', icon: Orbit },
  { to: '/theme-picker', label: '主题选股', icon: Sparkles },
  { to: '/stock-query', label: '单股查询', icon: Radar },
  { to: '/etf-query', label: '单 ETF', icon: Layers3 },
  { to: '/watchlist', label: '观察池', icon: WalletCards },
  { to: '/deep-analysis', label: '深度分析', icon: Star },
] as const;

export const AppShell: React.FC = () => {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-40 border-b border-border/70 bg-background/90 backdrop-blur-xl">
        <div className="mx-auto flex max-w-[1560px] items-center justify-between gap-4 px-4 py-4 md:px-7 lg:px-10">
          <div className="flex items-center gap-6">
            <NavLink to="/" className="flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-2xl border border-foreground/10 bg-foreground text-primary-foreground shadow-soft-card">
                <span className="text-sm font-semibold tracking-[0.18em]">TP</span>
              </div>
              <div>
                <p className="text-[10px] uppercase tracking-[0.22em] text-secondary-text">Research Workspace</p>
                <h1 className="font-display text-lg font-semibold tracking-tight text-foreground">Theme Picker</h1>
              </div>
            </NavLink>

            <nav className="hidden items-center gap-2 lg:flex">
              {NAV_ITEMS.map((item) => {
                const Icon = item.icon;
                return (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    end={false}
                    className={({ isActive }) =>
                      cn(
                        'inline-flex items-center gap-2 rounded-full border px-4 py-2 text-sm font-medium transition-all',
                        isActive
                          ? 'border-foreground/15 bg-foreground text-background shadow-soft-card'
                          : 'border-border/70 bg-card/75 text-secondary-text hover:border-foreground/10 hover:bg-foreground/4 hover:text-foreground',
                      )
                    }
                  >
                    <Icon className="h-4 w-4" />
                    <span>{item.label}</span>
                  </NavLink>
                );
              })}
            </nav>
          </div>

          <div className="flex items-center gap-3">
            <div className="hidden items-center gap-2 rounded-full border border-border/70 bg-card/75 px-3 py-2 md:flex">
              <Bell className="h-4 w-4 text-foreground" />
              <span className="text-sm text-secondary-text">实时数据</span>
              <Badge variant="info" className="border-0 px-2 py-0.5">已同步</Badge>
            </div>
            <NavLink
              to="/information-watch"
              className="hidden rounded-full border border-border/70 bg-card/75 px-3 py-2 text-sm text-secondary-text transition hover:bg-foreground/4 hover:text-foreground xl:inline-flex"
            >
              <span className="inline-flex items-center gap-2">
                <Newspaper className="h-4 w-4" />
                信息观察
              </span>
            </NavLink>
            <ThemeToggle />
            <NavLink
              to="/settings"
              className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-border/70 bg-card/80 text-foreground shadow-soft-card transition hover:bg-foreground/4"
              aria-label="设置"
              title="设置"
            >
              <Settings2 className="h-4 w-4" />
            </NavLink>
          </div>
        </div>

        <div className="mx-auto flex max-w-[1560px] gap-2 overflow-x-auto px-4 pb-3 lg:hidden md:px-7 lg:px-10">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={false}
                className={({ isActive }) =>
                  cn(
                    'inline-flex shrink-0 items-center gap-2 rounded-full border px-4 py-2 text-sm font-medium transition-all',
                    isActive
                      ? 'border-foreground/15 bg-foreground text-background shadow-soft-card'
                      : 'border-border/70 bg-card/75 text-secondary-text',
                  )
                }
              >
                <Icon className="h-4 w-4" />
                <span>{item.label}</span>
              </NavLink>
            );
          })}
        </div>
      </header>

      <Outlet />
    </div>
  );
};

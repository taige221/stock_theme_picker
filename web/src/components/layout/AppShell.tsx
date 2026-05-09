import type React from 'react';
import { Bell, LayoutGrid, Radar, Sparkles, Star, WalletCards } from 'lucide-react';
import { NavLink, Outlet } from 'react-router-dom';
import { ThemeToggle } from '../theme/ThemeToggle';
import { Badge } from '../common';
import { cn } from '../../utils/cn';

const NAV_ITEMS = [
  { to: '/', label: '工作台', icon: LayoutGrid },
  { to: '/theme-picker', label: '主题选股', icon: Sparkles },
  { to: '/stock-query', label: '单股查询', icon: Radar },
  { to: '/watchlist', label: '观察池', icon: WalletCards },
  { to: '/deep-analysis', label: '深度分析', icon: Star },
] as const;

export const AppShell: React.FC = () => {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-40 border-b border-border/60 bg-background/85 backdrop-blur-xl">
        <div className="mx-auto flex max-w-[1680px] items-center justify-between gap-4 px-4 py-4 md:px-6 lg:px-8">
          <div className="flex items-center gap-6">
            <NavLink to="/" className="flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-primary-gradient text-primary-foreground shadow-lg shadow-cyan/20">
                <Sparkles className="h-5 w-5" />
              </div>
              <div>
                <p className="text-[11px] uppercase tracking-[0.2em] text-secondary-text">Research Workspace</p>
                <h1 className="text-lg font-semibold tracking-tight text-foreground">Theme Picker</h1>
              </div>
            </NavLink>

            <nav className="hidden items-center gap-2 lg:flex">
              {NAV_ITEMS.map((item) => {
                const Icon = item.icon;
                return (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    end={item.to === '/'}
                    className={({ isActive }) =>
                      cn(
                        'inline-flex items-center gap-2 rounded-full border px-4 py-2 text-sm font-medium transition-all',
                        isActive
                          ? 'border-cyan/30 bg-primary-gradient text-primary-foreground shadow-lg shadow-cyan/15'
                          : 'border-border/60 bg-card/70 text-secondary-text hover:border-cyan/20 hover:bg-hover/60 hover:text-foreground',
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
            <div className="hidden items-center gap-2 rounded-full border border-border/60 bg-card/70 px-3 py-2 md:flex">
              <Bell className="h-4 w-4 text-cyan" />
              <span className="text-sm text-secondary-text">今日提醒</span>
              <Badge variant="info" className="border-0 px-2 py-0.5">4</Badge>
            </div>
            <ThemeToggle />
            <div className="flex h-11 w-11 items-center justify-center rounded-full border border-border/60 bg-card/80 text-sm font-semibold text-foreground shadow-soft-card">
              TP
            </div>
          </div>
        </div>

        <div className="mx-auto flex max-w-[1680px] gap-2 overflow-x-auto px-4 pb-3 lg:hidden md:px-6 lg:px-8">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                className={({ isActive }) =>
                  cn(
                    'inline-flex shrink-0 items-center gap-2 rounded-full border px-4 py-2 text-sm font-medium transition-all',
                    isActive
                      ? 'border-cyan/30 bg-primary-gradient text-primary-foreground shadow-lg shadow-cyan/15'
                      : 'border-border/60 bg-card/70 text-secondary-text',
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

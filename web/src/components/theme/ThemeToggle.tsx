import type React from 'react';
import { Moon, SunMedium } from 'lucide-react';
import { useTheme } from 'next-themes';
import { Button } from '../common';

export const ThemeToggle: React.FC = () => {
  const { resolvedTheme, setTheme } = useTheme();
  const isDark = resolvedTheme !== 'light';

  return (
    <Button
      type="button"
      variant="secondary"
      size="sm"
      onClick={() => setTheme(isDark ? 'light' : 'dark')}
      className="rounded-full border-border/60 bg-background/80 px-4 text-foreground backdrop-blur-sm"
      aria-label={isDark ? '切换到浅色模式' : '切换到深色模式'}
      title={isDark ? '切换到浅色模式' : '切换到深色模式'}
    >
      {isDark ? <SunMedium className="h-4 w-4 text-amber-500" /> : <Moon className="h-4 w-4 text-cyan" />}
      <span>{isDark ? '浅色模式' : '深色模式'}</span>
    </Button>
  );
};

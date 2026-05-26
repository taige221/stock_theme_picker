import type React from 'react';
import { Moon, SunMedium } from 'lucide-react';
import { useTheme } from 'next-themes';
import { Button } from '../common';
import { cn } from '../../utils/cn';

interface ThemeToggleProps {
  compact?: boolean;
  className?: string;
}

export const ThemeToggle: React.FC<ThemeToggleProps> = ({ compact = false, className }) => {
  const { resolvedTheme, setTheme } = useTheme();
  const isDark = resolvedTheme !== 'light';
  const label = isDark ? '切换到浅色模式' : '切换到深色模式';
  const text = isDark ? '浅色' : '深色';

  return (
    <Button
      type="button"
      variant="secondary"
      size="sm"
      onClick={() => setTheme(isDark ? 'light' : 'dark')}
      className={cn(
        compact
          ? 'shell-icon-button h-9 w-9 rounded-full px-0'
          : 'rounded-full border-border/70 bg-background/80 px-3 text-foreground backdrop-blur-sm',
        className,
      )}
      aria-label={label}
      title={label}
    >
      {isDark ? <SunMedium className="h-4 w-4 text-foreground" /> : <Moon className="h-4 w-4 text-foreground" />}
      {!compact ? <span>{text}</span> : null}
    </Button>
  );
};

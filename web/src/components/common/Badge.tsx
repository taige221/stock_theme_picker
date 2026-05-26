import React from 'react';
import { cn } from '../../utils/cn';

type BadgeVariant = 'default' | 'success' | 'warning' | 'danger' | 'info' | 'history';

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  children: React.ReactNode;
  variant?: BadgeVariant;
  size?: 'sm' | 'md';
  glow?: boolean;
  className?: string;
  style?: React.CSSProperties;
}

const variantStyles: Record<BadgeVariant, string> = {
  default: 'border-border/80 bg-card/92 text-secondary-text',
  success: 'border-success/18 bg-success/8 text-[hsl(var(--success)/0.92)]',
  warning: 'border-warning/18 bg-warning/9 text-[hsl(var(--warning)/0.92)]',
  danger: 'border-danger/18 bg-danger/8 text-[hsl(var(--danger)/0.92)]',
  info: 'border-foreground/12 bg-foreground/5 text-foreground',
  history: 'border-border/70 bg-background/55 text-secondary-text',
};

const glowStyles: Record<BadgeVariant, string> = {
  default: 'shadow-[0_8px_20px_hsl(var(--foreground)/0.05)]',
  success: 'shadow-[0_8px_20px_hsl(var(--success)/0.08)]',
  warning: 'shadow-[0_8px_20px_hsl(var(--warning)/0.08)]',
  danger: 'shadow-[0_8px_20px_hsl(var(--danger)/0.08)]',
  info: 'shadow-[0_8px_20px_hsl(var(--foreground)/0.06)]',
  history: 'shadow-[0_8px_20px_hsl(var(--foreground)/0.05)]',
};

export const Badge: React.FC<BadgeProps> = ({
  children,
  variant = 'default',
  size = 'sm',
  glow = false,
  className = '',
  style,
  ...rest
}) => {
  const sizeStyles = size === 'sm' ? 'px-2.5 py-1 text-[11px]' : 'px-3 py-1.5 text-sm';

  return (
    <span
      {...rest}
      style={style}
      className={cn(
        'inline-flex items-center gap-1 rounded-full border font-medium backdrop-blur-sm',
        sizeStyles,
        variantStyles[variant],
        glow && glowStyles[variant],
        className,
      )}
    >
      {children}
    </span>
  );
};

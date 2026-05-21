import React from 'react';
import { cn } from '../../utils/cn';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost' | 'gradient' | 'danger' | 'danger-subtle' | 'settings-primary' | 'settings-secondary' | 'action-primary' | 'action-secondary' | 'home-action-ai' | 'home-action-report';
  size?: 'xsm' | 'sm' | 'md' | 'lg' | 'xl';
  isLoading?: boolean;
  /** Custom loading text. */
  loadingText?: string;
  glow?: boolean;
}

const BUTTON_SIZE_STYLES = {
  xsm: 'h-6 rounded-xl px-2.5 text-xs',
  sm: 'h-8 rounded-xl px-3 text-sm',
  md: 'h-11 rounded-[1.35rem] px-4 text-sm',
  lg: 'h-11 rounded-[1.35rem] px-4.5 text-sm',
  xl: 'h-11 rounded-[1.35rem] px-5 text-sm',
} as const;

const ACTION_AI_STYLES = 'border border-border/85 bg-card/96 text-foreground shadow-none hover:-translate-y-px hover:border-foreground/16 hover:bg-card';
const ACTION_REPORT_STYLES = 'border border-border/80 bg-background/55 text-secondary-text shadow-none hover:-translate-y-px hover:border-foreground/16 hover:bg-card hover:text-foreground';

const BUTTON_VARIANT_STYLES = {
  primary: 'border border-foreground/92 bg-foreground text-background shadow-[0_14px_32px_hsl(var(--foreground)/0.12)] hover:-translate-y-px hover:bg-foreground/96 hover:shadow-[0_18px_36px_hsl(var(--foreground)/0.16)]',
  secondary: 'border border-border/90 bg-card/98 text-foreground shadow-none hover:-translate-y-px hover:border-foreground/14 hover:bg-card',
  'settings-primary': 'border border-foreground/92 bg-foreground text-background shadow-[0_14px_32px_hsl(var(--foreground)/0.12)] hover:-translate-y-px hover:bg-foreground/96',
  'settings-secondary': 'border border-border/90 bg-card/98 text-foreground shadow-none hover:-translate-y-px hover:border-foreground/14 hover:bg-card',
  outline: 'border border-border/90 bg-background/55 text-foreground shadow-none hover:-translate-y-px hover:border-foreground/14 hover:bg-card/72',
  ghost: 'border border-transparent bg-transparent text-secondary-text shadow-none hover:bg-foreground/5 hover:text-foreground',
  gradient: 'border border-foreground/85 bg-[linear-gradient(180deg,hsl(var(--foreground)),hsl(var(--foreground)/0.88))] text-background shadow-[0_12px_28px_hsl(var(--foreground)/0.12)] hover:-translate-y-px hover:opacity-95',
  danger: 'border border-danger/50 bg-danger/92 text-destructive-foreground shadow-none hover:-translate-y-px hover:bg-danger',
  'danger-subtle': 'border border-danger/24 bg-danger/8 text-danger hover:border-danger/36 hover:bg-danger/12',
  'action-primary': ACTION_AI_STYLES,
  'action-secondary': ACTION_REPORT_STYLES,
  'home-action-ai': ACTION_AI_STYLES,
  'home-action-report': ACTION_REPORT_STYLES,
} as const;

export const Button: React.FC<ButtonProps> = ({
  children,
  variant = 'primary',
  size = 'md',
  isLoading = false,
  loadingText = '处理中...',
  glow = false,
  className = '',
  disabled,
  type = 'button',
  ...props
}) => {
  const glowStyles = glow ? 'shadow-[0_14px_28px_hsl(var(--foreground)/0.14)] hover:shadow-[0_18px_34px_hsl(var(--foreground)/0.18)]' : '';

  return (
    <button
      type={type}
      aria-busy={isLoading || undefined}
      data-variant={variant}
      className={cn(
        'inline-flex cursor-pointer items-center justify-center gap-2 font-medium transition-all duration-200',
        'focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-foreground/10 focus-visible:ring-offset-0',
        'disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 disabled:transform-none',
        BUTTON_SIZE_STYLES[size],
        BUTTON_VARIANT_STYLES[variant],
        glowStyles,
        className,
      )}
      disabled={disabled || isLoading}
      {...props}
    >
      {isLoading ? (
        <span className="flex items-center justify-center gap-2">
          <svg
            className="h-4 w-4 animate-spin text-current"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            />
          </svg>
          {loadingText}
        </span>
      ) : (
        children
      )}
    </button>
  );
};

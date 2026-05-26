import type React from 'react';
import { cn } from '../../utils/cn';

type InlineAlertVariant = 'info' | 'success' | 'warning' | 'danger';

interface InlineAlertProps {
  title?: string;
  message: React.ReactNode;
  variant?: InlineAlertVariant;
  action?: React.ReactNode;
  className?: string;
}

const variantStyles: Record<InlineAlertVariant, string> = {
  info: 'border-foreground/12 bg-foreground/5 text-foreground',
  success: 'border-success/18 bg-success/8 text-[hsl(var(--success)/0.95)]',
  warning: 'border-warning/18 bg-warning/9 text-[hsl(var(--warning)/0.95)]',
  danger: 'border-danger/20 bg-danger/8 text-[hsl(var(--danger)/0.95)]',
};

export const InlineAlert: React.FC<InlineAlertProps> = ({
  title,
  message,
  variant = 'info',
  action,
  className = '',
}) => {
  return (
    <div
      role="alert"
      className={cn('rounded-[1.35rem] border px-4 py-3 shadow-soft-card', variantStyles[variant], className)}
    >
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          {title ? <p className="text-sm font-semibold text-foreground">{title}</p> : null}
          <div className={cn('text-sm', title ? 'mt-1 opacity-90' : 'opacity-90')}>{message}</div>
        </div>
        {action ? <div className="shrink-0">{action}</div> : null}
      </div>
    </div>
  );
};

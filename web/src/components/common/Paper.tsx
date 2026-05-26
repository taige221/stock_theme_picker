import type React from 'react';
import { Badge } from './Badge';
import { Card } from './Card';
import { cn } from '../../utils/cn';

type PaperHeroProps = {
  children: React.ReactNode;
  className?: string;
  contentClassName?: string;
};

export const PaperHero: React.FC<PaperHeroProps> = ({ children, className, contentClassName }) => (
  <section className={cn('paper-hero', className)}>
    <div className={cn('px-5 py-6 lg:px-7 lg:py-7', contentClassName)}>
      {children}
    </div>
  </section>
);

type PaperHeroHeaderProps = {
  eyebrow: string;
  title: string;
  description?: string;
  icon?: React.ReactNode;
  className?: string;
  titleClassName?: string;
  descriptionClassName?: string;
  children?: React.ReactNode;
};

export const PaperHeroHeader: React.FC<PaperHeroHeaderProps> = ({
  eyebrow,
  title,
  description,
  icon,
  className,
  titleClassName,
  descriptionClassName,
  children,
}) => (
  <div className={cn('flex items-start gap-4', className)}>
    {icon ? <div className="paper-hero-icon">{icon}</div> : null}
    <div>
      <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-secondary-text">{eyebrow}</p>
      <h2 className={cn('mt-1 text-[2rem] font-semibold tracking-[-0.03em] text-foreground md:text-[2.2rem]', titleClassName)}>{title}</h2>
      {description ? (
        <p className={cn('mt-2 max-w-3xl text-sm leading-6 text-secondary-text', descriptionClassName)}>{description}</p>
      ) : null}
      {children}
    </div>
  </div>
);

type PaperSectionHeaderProps = {
  eyebrow?: string;
  title?: string;
  description?: string;
  icon?: React.ReactNode;
  className?: string;
  actions?: React.ReactNode;
};

export const PaperSectionHeader: React.FC<PaperSectionHeaderProps> = ({
  eyebrow,
  title,
  description,
  icon,
  className,
  actions,
}) => (
  <div className={cn('flex items-start justify-between gap-3', className)}>
    <div className="flex items-start gap-3">
      {icon ? <div className="paper-section-icon">{icon}</div> : null}
      <div>
        {eyebrow ? <span className="label-uppercase">{eyebrow}</span> : null}
        {title ? <h3 className="mt-1 text-[1.55rem] font-semibold tracking-[-0.02em] text-foreground">{title}</h3> : null}
        {description ? <p className="mt-2 text-sm leading-6 text-secondary-text">{description}</p> : null}
      </div>
    </div>
    {actions ? <div className="shrink-0">{actions}</div> : null}
  </div>
);

type PaperStatCardProps = {
  label: string;
  value: React.ReactNode;
  detail?: React.ReactNode;
  className?: string;
};

export const PaperStatCard: React.FC<PaperStatCardProps> = ({ label, value, detail, className }) => (
  <Card variant="bordered" padding="lg" className={cn('paper-kpi-card rounded-[24px]', className)}>
    <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-secondary-text">{label}</p>
    <p className="mt-3 text-[1.9rem] font-semibold tracking-[-0.02em] text-foreground">{value}</p>
    {detail ? <p className="mt-2 text-sm leading-6 text-secondary-text">{detail}</p> : null}
  </Card>
);

type PaperSectionCardProps = {
  title?: string;
  eyebrow?: string;
  description?: string;
  icon?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  bodyClassName?: string;
};

export const PaperSectionCard: React.FC<PaperSectionCardProps> = ({
  title,
  eyebrow,
  description,
  icon,
  actions,
  children,
  className,
  bodyClassName,
}) => (
  <Card variant="bordered" padding="lg" className={cn('paper-panel rounded-[24px]', className)}>
    <PaperSectionHeader eyebrow={eyebrow} title={title} description={description} icon={icon} actions={actions} />
    <div className={cn('mt-5', bodyClassName)}>{children}</div>
  </Card>
);

type PaperListBlockProps = {
  children: React.ReactNode;
  className?: string;
  size?: 'md' | 'lg';
};

export const PaperListBlock: React.FC<PaperListBlockProps> = ({ children, className, size = 'md' }) => (
  <div className={cn('paper-list-card', size === 'lg' ? 'px-5 py-4' : 'px-4 py-4', className)}>
    {children}
  </div>
);

type PaperMetricCardProps = {
  label: string;
  value: React.ReactNode;
  detail?: React.ReactNode;
  className?: string;
  valueClassName?: string;
  detailClassName?: string;
  tone?: 'default' | 'muted' | 'alert';
  align?: 'left' | 'center';
};

export const PaperMetricCard: React.FC<PaperMetricCardProps> = ({
  label,
  value,
  detail,
  className,
  valueClassName,
  detailClassName,
  tone = 'muted',
  align = 'left',
}) => {
  const toneClass = tone === 'default' ? 'paper-panel' : tone === 'alert' ? 'paper-alert-card' : 'paper-panel-muted';
  return (
    <div className={cn(toneClass, align === 'center' ? 'text-center' : '', 'px-4 py-3', className)}>
      <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-secondary-text">{label}</p>
      <p className={cn('mt-2 text-[1.05rem] font-semibold tracking-[-0.02em] text-foreground', valueClassName)}>{value}</p>
      {detail ? <p className={cn('mt-1 text-xs leading-5 text-secondary-text', detailClassName)}>{detail}</p> : null}
    </div>
  );
};

type PaperDataBlockCardProps = {
  title: string;
  subtitle?: React.ReactNode;
  status?: React.ReactNode;
  children?: React.ReactNode;
  footer?: React.ReactNode;
  className?: string;
  bodyClassName?: string;
};

export const PaperDataBlockCard: React.FC<PaperDataBlockCardProps> = ({
  title,
  subtitle,
  status,
  children,
  footer,
  className,
  bodyClassName,
}) => (
  <PaperListBlock size="lg" className={className}>
    <div className="flex items-start justify-between gap-3">
      <div>
        <p className="text-sm font-semibold text-foreground">{title}</p>
        {subtitle ? <div className="mt-1 text-xs text-secondary-text">{subtitle}</div> : null}
      </div>
      {status ? <div className="shrink-0">{status}</div> : null}
    </div>

    {(children || footer) ? (
      <div className={cn('mt-3 space-y-3', bodyClassName)}>
        {children}
        {footer}
      </div>
    ) : null}
  </PaperListBlock>
);

type PaperSummaryBlockProps = {
  title: string;
  summary?: string | null;
  items?: string[];
  danger?: boolean;
  className?: string;
};

export const PaperSummaryBlock: React.FC<PaperSummaryBlockProps> = ({
  title,
  summary,
  items = [],
  danger = false,
  className,
}) => {
  if (!summary && items.length === 0) return null;

  return (
    <PaperListBlock className={cn(danger ? 'paper-alert-card' : 'paper-list-card', className)}>
      <p className="text-sm font-semibold text-foreground">{title}</p>
      {summary ? <p className="mt-2 text-sm leading-6 text-secondary-text">{summary}</p> : null}
      {items.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {items.map((item) => (
            <span key={item} className="paper-chip px-3 py-2 text-xs font-medium text-foreground">
              {item}
            </span>
          ))}
        </div>
      ) : null}
    </PaperListBlock>
  );
};

type PaperStatusBadgeProps = {
  value: string;
  className?: string;
};

export const PaperStatusBadge: React.FC<PaperStatusBadgeProps> = ({ value, className }) => {
  const variant = value === 'ok' || value === 'full' ? 'success' : value === 'partial' ? 'warning' : 'default';
  return (
    <Badge variant={variant} className={cn('border-0 px-2 py-1', className)}>
      {value}
    </Badge>
  );
};

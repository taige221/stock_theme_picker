import type React from 'react';
import { useEffect, useCallback } from 'react';
import { cn } from '../../utils/cn';

let activeDrawerCount = 0;

interface DrawerProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
  width?: string;
  zIndex?: number;
  side?: 'left' | 'right';
  backdropClassName?: string;
}

export const Drawer: React.FC<DrawerProps> = ({
  isOpen,
  onClose,
  title,
  children,
  width = 'max-w-2xl',
  zIndex = 50,
  side = 'right',
  backdropClassName,
}) => {
  // Close the drawer when Escape is pressed.
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    },
    [onClose]
  );

  useEffect(() => {
    if (isOpen) {
      document.addEventListener('keydown', handleKeyDown);
      activeDrawerCount++;
      if (activeDrawerCount === 1) {
        document.body.style.overflow = 'hidden';
      }

      return () => {
        document.removeEventListener('keydown', handleKeyDown);
        activeDrawerCount--;
        if (activeDrawerCount === 0) {
          document.body.style.overflow = '';
        }
      };
    }
  }, [isOpen, handleKeyDown]);

  if (!isOpen) return null;

  const titleId = title ? `drawer-title-${side}` : undefined;
  const sidePositionClass = side === 'left' ? 'left-0 justify-start' : 'right-0 justify-end';
  const borderClass = side === 'left' ? 'border-r' : 'border-l';

  return (
    <div className="fixed inset-0 overflow-hidden" style={{ zIndex }} role="presentation">
      {/* Backdrop */}
      <div
        className={cn(
          'absolute inset-0 bg-[hsl(var(--foreground)/0.12)] backdrop-blur-[2px] transition-opacity duration-300',
          backdropClassName,
        )}
        onClick={onClose}
      />

      <div className={cn('absolute inset-y-0 flex w-full', sidePositionClass, width)}>
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby={titleId}
          className={cn(
            'relative flex w-full flex-col bg-[linear-gradient(180deg,hsl(var(--card)/0.98),hsl(var(--background)/0.96))]',
            borderClass,
            side === 'right' ? 'border-border/80 shadow-[0_18px_44px_hsl(var(--foreground)/0.10)]' : 'border-border/70 shadow-[0_18px_44px_hsl(var(--foreground)/0.10)]',
            side === 'left' ? 'animate-slide-in-left' : 'animate-slide-in-right'
          )}
        >
          <div className="flex items-center justify-between border-b border-border/60 px-6 py-4">
            {title ? (
              <div>
                <span className="label-uppercase">DETAIL</span>
                <h2 id={titleId} className="mt-1 text-lg font-semibold text-foreground">{title}</h2>
              </div>
            ) : <div />}
            <button
              type="button"
              onClick={onClose}
              className="inline-flex h-10 w-10 items-center justify-center rounded-2xl border border-border/75 bg-card/90 text-secondary-text transition-all duration-200 hover:border-foreground/16 hover:bg-background/70 hover:text-foreground"
              aria-label="关闭抽屉"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-6">
            {children}
          </div>
        </div>
      </div>
    </div>
  );
};

import type React from 'react';
import { cn } from '../../utils/cn';

interface AppPageProps {
  children: React.ReactNode;
  className?: string;
}

export const AppPage: React.FC<AppPageProps> = ({ children, className = '' }) => {
  return (
    <main className={cn('mx-auto min-h-full w-full max-w-[1560px] px-4 pb-10 pt-6 md:px-7 lg:px-10', className)}>
      {children}
    </main>
  );
};

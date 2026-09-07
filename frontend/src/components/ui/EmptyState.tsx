import React from 'react';

interface EmptyStateProps {
  icon: React.ReactNode;
  title: string;
  description?: React.ReactNode;
  action?: React.ReactNode;
  tone?: 'neutral' | 'success' | 'warn' | 'danger';
  className?: string;
  /** When true, renders without the outer card so it can sit inside another card */
  compact?: boolean;
  secondaryHelp?: string;
}

const toneRing: Record<NonNullable<EmptyStateProps['tone']>, string> = {
  neutral: 'text-[#B8BEC9] border-[#202631] bg-[#11141B]',
  success: 'text-[#35D6A3] border-[rgba(53,214,163,0.34)] bg-[rgba(53,214,163,0.09)]',
  warn:    'text-[#F0B429] border-[rgba(240,180,41,0.38)] bg-[rgba(240,180,41,0.10)]',
  danger:  'text-[#F27781] border-[rgba(242,119,129,0.34)] bg-[rgba(242,119,129,0.09)]',
};

export const EmptyState: React.FC<EmptyStateProps> = ({
  icon,
  title,
  description,
  action,
  tone = 'neutral',
  className = '',
  compact,
  secondaryHelp,
}) => {
  const body = (
    <>
      <div
        className={`h-12 w-12 rounded-full border flex items-center justify-center shrink-0 shadow-card transition-all duration-300 group-hover:scale-110 ${toneRing[tone]}`}
        aria-hidden="true"
      >
        {icon}
      </div>
      <div className="space-y-2 max-w-sm">
        <p className="text-sm font-semibold text-text tracking-wide">{title}</p>
        {description && (
          <p className="text-xs text-text-muted leading-relaxed font-sans font-normal">{description}</p>
        )}
        {secondaryHelp && (
          <p className="text-[10px] text-text-subtle font-normal leading-normal font-sans italic">{secondaryHelp}</p>
        )}
      </div>
      {action && <div className="pt-2 select-none">{action}</div>}
    </>
  );

  if (compact) {
    return (
      <div className={`flex flex-col items-center justify-center gap-3.5 text-center py-6 px-4 group fade-up ${className}`}>
        {body}
      </div>
    );
  }

  return (
    <div className={`card flex flex-col items-center justify-center gap-4 text-center py-14 px-8 shadow-card border-border/80 bg-surface-1/40 hover:border-border transition-all duration-300 group fade-up ${className}`}>
      {body}
    </div>
  );
};

export default EmptyState;

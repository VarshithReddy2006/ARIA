import React from 'react';

export type Tone = 'success' | 'warn' | 'danger' | 'info' | 'violet' | 'neutral' | 'primary';

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  tone?: Tone;
  icon?: React.ReactNode;
}

const toneMap: Record<Tone, string> = {
  success: 'bg-[rgba(53,214,163,0.09)] text-[#35D6A3] border border-[rgba(53,214,163,0.34)]',
  warn:    'bg-[rgba(240,180,41,0.10)] text-[#F0B429] border border-[rgba(240,180,41,0.38)]',
  danger:  'bg-[rgba(242,119,129,0.09)] text-[#F27781] border border-[rgba(242,119,129,0.34)]',
  info:    'bg-[rgba(76,201,232,0.08)] text-[#4CC9E8] border border-[rgba(76,201,232,0.28)]',
  violet:  'bg-[rgba(165,140,255,0.09)] text-[#A58CFF] border border-[rgba(165,140,255,0.30)]',
  neutral: 'bg-[#11141B] text-[#B8BEC9] border border-[#202631]',
  primary: 'bg-[rgba(124,131,255,0.10)] text-[#7C83FF] border border-[rgba(124,131,255,0.38)]',
};

export const Badge: React.FC<BadgeProps> = ({
  tone = 'neutral',
  icon,
  className = '',
  children,
  ...rest
}) => (
  <span
    className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-semibold uppercase tracking-wider ${toneMap[tone]} ${className}`}
    {...rest}
  >
    {icon && <span aria-hidden="true" className="shrink-0">{icon}</span>}
    {children}
  </span>
);

export default Badge;

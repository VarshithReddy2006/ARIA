import React from 'react';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';
type Size = 'sm' | 'md' | 'lg';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  /** When true, the button stretches to fill its container */
  block?: boolean;
  /** When true, shows a spinner and disables the button */
  loading?: boolean;
  /** Left icon */
  leadingIcon?: React.ReactNode;
  /** Right icon */
  trailingIcon?: React.ReactNode;
}

const base =
  'inline-flex items-center justify-center gap-2 rounded-md font-semibold font-mono text-xs transition-all ' +
  'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[#7C83FF] disabled:cursor-not-allowed select-none';

const sizes: Record<Size, string> = {
  sm: 'text-[11px] px-2.5 py-1',
  md: 'text-xs px-3.5 py-1.5',
  lg: 'text-sm px-4.5 py-2',
};

const variants: Record<Variant, string> = {
  primary:   'bg-[#7C83FF] text-[#FFFFFF] hover:bg-[#9197FF] active:bg-[#636BEF] disabled:opacity-40 shadow-sm border border-[#7C83FF]/40',
  secondary: 'bg-[#11141B] text-[#B8BEC9] border border-[#2A313C] hover:bg-[#161A22] hover:border-[#3A4350] hover:text-[#F5F7FA] active:bg-[#0D1015] disabled:opacity-40',
  ghost:     'bg-transparent text-[#858D9A] border border-[#202631] hover:text-[#F5F7FA] hover:border-[#7C83FF]/40 hover:bg-[#11141B] disabled:opacity-40',
  danger:    'bg-[rgba(242,119,129,0.09)] text-[#F27781] border border-[rgba(242,119,129,0.34)] hover:bg-[rgba(242,119,129,0.18)] active:bg-[rgba(242,119,129,0.25)] disabled:opacity-40',
};

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>((
  {
    variant = 'primary',
    size = 'md',
    block,
    loading,
    leadingIcon,
    trailingIcon,
    className = '',
    children,
    disabled,
    ...rest
  },
  ref,
) => (
  <button
    ref={ref}
    disabled={disabled || loading}
    aria-busy={loading || undefined}
    className={[
      base,
      sizes[size],
      variants[variant],
      block ? 'w-full' : '',
      className,
    ].filter(Boolean).join(' ')}
    {...rest}
  >
    {loading
      ? <svg className="h-3.5 w-3.5 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" aria-hidden="true"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z"/></svg>
      : leadingIcon && <span className="shrink-0" aria-hidden="true">{leadingIcon}</span>
    }
    {children}
    {!loading && trailingIcon && <span className="shrink-0" aria-hidden="true">{trailingIcon}</span>}
  </button>
));
Button.displayName = 'Button';

export default Button;

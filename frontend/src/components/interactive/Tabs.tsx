import React, { useEffect, useRef, useState } from 'react';

export interface TabItem<T extends string> {
  id: T;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  /** Optional group label — rendered as a separator when the group changes */
  group?: string;
}

interface TabsProps<T extends string> {
  items: TabItem<T>[];
  active: T;
  onChange: (id: T) => void;
  className?: string;
}

/**
 * Analysis surface navigation.
 *
 * A quiet strip with a single hairline baseline and a thin indigo underline on
 * the active tab — no rounded container per tab, no filled backgrounds. The
 * strip scrolls inside itself (`.inner-scroll-x`) so a long tab list can never
 * produce a document-level horizontal scrollbar, and the active tab is scrolled
 * into view when it changes from elsewhere (deep link, KPI click, keyboard).
 *
 * Accessibility is unchanged: role="tablist", arrow/Home/End navigation,
 * aria-selected, and aria-controls pointing at `tabpanel-${id}`.
 */
/** Clearance kept between the active tab and the rail edge, in px. Larger than
 *  the CSS fade (`--tab-fade`, 28px) so a scrolled-to tab is never under it. */
const EDGE_CLEARANCE = 40;

export function Tabs<T extends string>({ items, active, onChange, className = '' }: TabsProps<T>) {
  const listRef = useRef<HTMLDivElement>(null);
  const activeRef = useRef<HTMLButtonElement>(null);

  /** Geometry of the single underline, measured from the active tab. */
  const [marker, setMarker] = useState({ left: 0, width: 0, ready: false });

  /** Which sides still have tabs off-screen, so the fade only shows there. */
  const [edges, setEdges] = useState({ start: false, end: false });

  // Keep the selected tab visible, and glide the underline to it. Measured on
  // selection change only — never on hover, and never per frame.
  useEffect(() => {
    const el = activeRef.current;
    const list = listRef.current;
    if (!el || !list) return;

    const place = () => {
      setMarker({ left: el.offsetLeft, width: el.offsetWidth, ready: true });
    };
    place();

    const elLeft = el.offsetLeft;
    const elRight = elLeft + el.offsetWidth;
    const viewLeft = list.scrollLeft;
    const viewRight = viewLeft + list.clientWidth;

    if (elLeft < viewLeft + EDGE_CLEARANCE) {
      list.scrollTo({ left: Math.max(0, elLeft - EDGE_CLEARANCE), behavior: 'smooth' });
    } else if (elRight > viewRight - EDGE_CLEARANCE) {
      list.scrollTo({
        left: elRight - list.clientWidth + EDGE_CLEARANCE,
        behavior: 'smooth',
      });
    }

    if (typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(place);
    ro.observe(list);
    return () => ro.disconnect();
  }, [active, items.length]);

  /*
    Track which end of the rail still holds tabs. State is only written when a
    boolean actually flips, so a scroll gesture does not re-render per frame.
  */
  useEffect(() => {
    const list = listRef.current;
    if (!list) return;

    const measure = () => {
      const start = list.scrollLeft > 2;
      const end = list.scrollLeft + list.clientWidth < list.scrollWidth - 2;
      setEdges((prev) => (prev.start === start && prev.end === end ? prev : { start, end }));
    };

    measure();
    list.addEventListener('scroll', measure, { passive: true });

    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(measure) : null;
    ro?.observe(list);

    return () => {
      list.removeEventListener('scroll', measure);
      ro?.disconnect();
    };
  }, [items.length]);

  const onKey = (e: React.KeyboardEvent) => {
    const idx = items.findIndex((i) => i.id === active);
    if (idx < 0) return;
    if (e.key === 'ArrowRight') {
      e.preventDefault();
      onChange(items[(idx + 1) % items.length].id);
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault();
      onChange(items[(idx - 1 + items.length) % items.length].id);
    } else if (e.key === 'Home') {
      e.preventDefault();
      onChange(items[0].id);
    } else if (e.key === 'End') {
      e.preventDefault();
      onChange(items[items.length - 1].id);
    }
  };

  return (
    <div
      role="tablist"
      ref={listRef}
      onKeyDown={onKey}
      className={[
        'tab-rail inner-scroll-x relative flex items-stretch gap-6',
        'border-b border-white/[0.055]',
        // Proximity rather than mandatory: the rail still settles on a tab
        // boundary, but programmatic scroll-into-view is not fought.
        'snap-x snap-proximity',
        edges.start ? 'is-overflow-start' : '',
        edges.end ? 'is-overflow-end' : '',
        className,
      ].join(' ')}
    >
      {/* One underline for the whole strip, gliding between selections */}
      <span
        aria-hidden="true"
        className="pointer-events-none absolute bottom-0 h-px bg-primary"
        style={{
          left: 0,
          width: marker.width,
          transform: `translateX(${marker.left}px)`,
          opacity: marker.ready ? 1 : 0,
          transition:
            'transform 320ms cubic-bezier(0.16,1,0.3,1), width 320ms cubic-bezier(0.16,1,0.3,1), opacity 200ms ease',
        }}
      />
      {items.map(({ id, label, icon: Icon }) => {
        const isActive = active === id;

        return (
          <button
            key={id}
            ref={isActive ? activeRef : undefined}
            role="tab"
            type="button"
            aria-selected={isActive}
            aria-controls={`tabpanel-${id}`}
            tabIndex={isActive ? 0 : -1}
            onClick={() => onChange(id)}
            className={[
              'group relative shrink-0 snap-start flex items-center gap-2 pb-3 pt-1',
              'font-mono text-[11px] uppercase tracking-[0.14em] whitespace-nowrap',
              'transition-colors duration-200 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary/40 rounded-sm',
              isActive ? 'text-white font-medium' : 'text-text-muted hover:text-text',
            ].join(' ')}
          >
            <Icon
              className={`h-3.5 w-3.5 shrink-0 transition-colors duration-200 ${
                isActive ? 'text-primary' : 'text-text-muted group-hover:text-text'
              }`}
              aria-hidden="true"
            />
            <span>{label}</span>
          </button>
        );
      })}
    </div>
  );
}

export default Tabs;

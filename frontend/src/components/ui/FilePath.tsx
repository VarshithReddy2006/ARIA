import React from 'react';

export type FilePathTone = 'primary' | 'secondary' | 'metadata';
export type FilePathSize = 'sm' | 'md' | 'lg';

interface FilePathProps {
  /** Full repository-relative path, e.g. `fastapi/routing.py`. */
  path: string;
  /** primary = the subject, secondary = a reference, metadata = telemetry. */
  tone?: FilePathTone;
  size?: FilePathSize;
  /** Renders a semantic button and fires on click/Enter/Space. */
  onActivate?: () => void;
  /** Currently selected — exposed via `aria-current`, not colour alone. */
  active?: boolean;
  /** A small directional glyph, for imports and relationship targets. */
  marker?: 'import' | 'target';
  /** Appended after the path, e.g. a line number or count. */
  trailing?: React.ReactNode;
  className?: string;
}

const TONE_CLASS: Record<FilePathTone, string> = {
  primary: 'fp--primary',
  secondary: 'fp--secondary',
  metadata: 'fp--metadata',
};

const SIZE_CLASS: Record<FilePathSize, string> = {
  sm: 'fp--sm',
  md: 'fp--md',
  lg: 'fp--lg',
};

/**
 * The single way ARIA renders a file path.
 *
 * One component so the same file reads as the same entity everywhere — the
 * explorer, centrality rail, relationship timeline, inspector and entry points.
 * The directory prefix recedes and the filename carries the emphasis, so a path
 * scans as "which file" first and "where" second.
 *
 * Long paths wrap rather than truncate: the filename must never disappear, and
 * the page must never scroll sideways. `overflow-wrap: anywhere` satisfies both,
 * with weight and colour keeping the filename the visual anchor even when the
 * directory prefix wraps above it.
 */
export const FilePath: React.FC<FilePathProps> = ({
  path,
  tone = 'primary',
  size = 'md',
  onActivate,
  active = false,
  marker,
  trailing,
  className = '',
}) => {
  const cut = path.lastIndexOf('/');
  const dir = cut >= 0 ? path.slice(0, cut + 1) : '';
  const name = cut >= 0 ? path.slice(cut + 1) : path;

  const classes = [
    'fp',
    TONE_CLASS[tone],
    SIZE_CLASS[size],
    onActivate ? 'fp--interactive' : '',
    active ? 'fp--active' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  const content = (
    <>
      {marker && (
        <span className="fp-marker" aria-hidden="true">
          →
        </span>
      )}
      {dir && <span className="fp-dir">{dir}</span>}
      <span className="fp-name">{name}</span>
      {trailing && <span className="fp-trailing">{trailing}</span>}
    </>
  );

  if (onActivate) {
    return (
      <button
        type="button"
        onClick={onActivate}
        className={classes}
        // The full path is the accessible name; the split rendering is visual.
        aria-label={path}
        aria-current={active ? 'true' : undefined}
        title={path}
      >
        {content}
      </button>
    );
  }

  return (
    <span className={classes} title={path} aria-label={path}>
      {content}
    </span>
  );
};

export default FilePath;

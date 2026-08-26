/**
 * Derived repository metrics.
 *
 * These are presentation-layer heuristics computed from data the analysis API
 * already returns. They are deliberately centralised so the hero section and
 * the overview cards can never disagree on the same number.
 *
 * Anything sourced from the backend (health score, grade) is fetched, not
 * invented — see `useRepoHealth`.
 */

export type ComplexityBand = 'low' | 'moderate' | 'high' | 'very-high';

export interface ComplexityResult {
  /** 0–100 density proxy */
  score: number;
  band: ComplexityBand;
  label: string;
  tone: 'success' | 'warn' | 'danger' | 'info';
}

export interface ComplexityInputs {
  fileCount: number;
  componentCount: number;
  dependencyCount: number;
}

const BAND_META: Record<ComplexityBand, Pick<ComplexityResult, 'label' | 'tone'>> = {
  'low':       { label: 'Low',       tone: 'success' },
  'moderate':  { label: 'Moderate',  tone: 'info' },
  'high':      { label: 'High',      tone: 'warn' },
  'very-high': { label: 'Very High', tone: 'danger' },
};

/**
 * Density proxy combining indexed breadth (files), architectural integration
 * (components) and external surface (dependencies).
 */
export function computeComplexity({
  fileCount,
  componentCount,
  dependencyCount,
}: ComplexityInputs): ComplexityResult {
  // Normalize file breadth with logarithmic compression + architectural coupling
  const fileScore = Math.min(45, Math.round(Math.log10(Math.max(1, fileCount)) * 15));
  const compScore = Math.min(35, Math.round(componentCount * 2.5));
  const depScore = Math.min(20, Math.round(Math.log2(Math.max(1, dependencyCount + 1)) * 3.5));
  const score = Math.max(5, Math.min(100, Math.round(fileScore + compScore + depScore)));

  let band: ComplexityBand = 'low';
  if (score >= 85) band = 'very-high';
  else if (score >= 60) band = 'high';
  else if (score >= 30) band = 'moderate';

  return { score, band, ...BAND_META[band] };
}

/**
 * Estimated focused-reading time for the generated onboarding path.
 * Assumes roughly 6 minutes of attentive reading per ranked step, which
 * matches the granularity of the reading-path output.
 */
export function estimateReadingMinutes(readingSteps: number): number {
  if (!readingSteps || readingSteps <= 0) return 0;
  return readingSteps * 6;
}

/** Formats minutes as a compact human duration: 45m, 1h 20m, 3h. */
export function formatDuration(minutes: number): string {
  if (!minutes || minutes <= 0) return '—';
  if (minutes < 60) return `${Math.round(minutes)}m`;

  const hours = Math.floor(minutes / 60);
  const rest = Math.round(minutes % 60);
  return rest === 0 ? `${hours}h` : `${hours}h ${rest}m`;
}

/**
 * Picks the dominant language from the detected stack.
 * The stack array is ordered by backend confidence, so the first recognised
 * language wins; falls back to the first entry overall.
 */
const KNOWN_LANGUAGES = [
  'python', 'typescript', 'javascript', 'go', 'golang', 'rust', 'java',
  'kotlin', 'swift', 'ruby', 'php', 'c#', 'csharp', 'c++', 'cpp', 'c',
  'scala', 'elixir', 'erlang', 'dart', 'lua', 'perl', 'haskell', 'clojure',
  'zig', 'objective-c', 'shell', 'bash', 'html', 'css',
];

export function detectPrimaryLanguage(techStack: string[]): string | null {
  if (!techStack || techStack.length === 0) return null;

  for (const entry of techStack) {
    const normalized = entry.trim().toLowerCase();
    if (KNOWN_LANGUAGES.includes(normalized)) return entry.trim();
  }

  return techStack[0]?.trim() || null;
}

/** Relative "time ago" string from an epoch-ms timestamp or ISO date. */
export function relativeTimeFrom(value: number | string | null | undefined): string | null {
  if (value === null || value === undefined || value === '') return null;

  const timestamp = typeof value === 'number' ? value : new Date(value).getTime();
  if (Number.isNaN(timestamp)) return null;

  const seconds = Math.round((Date.now() - timestamp) / 1000);
  if (seconds < 5) return 'just now';
  if (seconds < 60) return `${seconds} sec ago`;

  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;

  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;

  const days = Math.round(hours / 24);
  return days === 1 ? 'yesterday' : `${days}d ago`;
}

/** Maps a 0–100 score to a semantic tone. */
export function scoreTone(score: number): 'success' | 'warn' | 'danger' {
  if (score >= 80) return 'success';
  if (score >= 60) return 'warn';
  return 'danger';
}

/**
 * GitHistoryAnalyzer — the repository's memory, read as an instrument.
 *
 * The reading order is the argument:
 *
 *   REPOSITORY → HISTORY WINDOW → ACTIVITY SIGNAL
 *   → HOTSPOTS / TIMELINE / AUTHORS → EVIDENCE
 *
 * Presentation notes, because they are deliberate rather than stylistic:
 *
 * · Churn is carried by indigo luminance, the same scale the landing page's
 *   repository-memory chapter uses. The previous red/orange/yellow/green ramp
 *   read as a traffic-light verdict on files that are simply changing often.
 *   Amber is now reserved for the one genuine risk the backend measures —
 *   single-author ownership.
 * · A hotspot row is an evidence record: rank, identity, a signal bar whose
 *   length is the composite score relative to the strongest signal in the field,
 *   and the readings that produced it. Bars resolve once as the field is reached
 *   and then rest; nothing pulses as though commits were arriving live.
 * · The shallow-clone caveat is a diagnostic annotation on the reading, not an
 *   alert card, because it qualifies the numbers rather than replacing them.
 * · The analysis phase rail is driven by the `status` values the churn SSE
 *   stream already emits (mining → computing → graph/hotspots → saving), so it
 *   reports the real pipeline instead of animating on a timer.
 *
 * Every figure comes from `/api/v1/churn/*` unchanged. The churn band and the
 * author aggregation are the only derived readings, both are deterministic
 * functions of the payload, and both are labelled as derived.
 */

import React, { useCallback, useMemo, useRef, useState } from 'react';
import { apiUrl, extractErrorMessage } from '../../lib/api';
import { FilePath } from '../ui/FilePath';
import { Reveal } from '../ui/Reveal';
import { useRevealed } from '../ui/useReveal';
import { SkeletonCard, SkeletonGroup } from '../ui/Skeleton';
import { AlertTriangle, ArrowRight, ChevronDown, Loader2 } from 'lucide-react';

// ── Types (unchanged — these mirror models/churn.py) ──────────────────────

interface HotspotFile {
  file_path: string;
  churn_score: number;
  centrality: number;
  hotspot_score: number;
  commit_count: number;
  primary_author: string;
  bus_factor_risk: boolean;
}

interface TimelineEntry {
  week: string;
  commit_count: number;
  files_changed: number;
  authors: string[];
}

interface AuthorOwnership {
  file_path: string;
  primary_author: string;
  ownership_pct: number;
  contributors: Record<string, number>;
}

interface ChurnSummary {
  repo: string;
  generated_at: string;
  since_days: number;
  total_commits: number;
  total_files: number;
  hotspots: HotspotFile[];
  author_ownership: AuthorOwnership[];
  timeline: TimelineEntry[];
  warning?: string;
}

interface Props {
  repoName: string;
}

type ViewId = 'hotspots' | 'timeline' | 'authors';

// ── Analysis pipeline phases ──────────────────────────────────────────────

const PHASES = [
  'MINING COMMITS',
  'MAPPING FILE CHURN',
  'CALCULATING HOTSPOTS',
  'READY',
] as const;

/**
 * The churn stream's own `status` values, mapped onto the four phases above.
 * Unknown statuses leave the rail where it is rather than guessing a position.
 */
const PHASE_OF_STATUS: Record<string, number> = {
  mining: 0,
  mining_done: 0,
  computing: 1,
  normalised: 1,
  graph: 2,
  hotspots: 2,
  saving: 3,
  complete: 3,
};

const VIEWS: { id: ViewId; label: string; criterion: string }[] = [
  { id: 'hotspots', label: 'Hotspots', criterion: 'CHURN × (1 + CENTRALITY)' },
  { id: 'timeline', label: 'Timeline', criterion: 'WEEKLY COMMIT BUCKETS' },
  { id: 'authors', label: 'Authors', criterion: 'PER-FILE OWNERSHIP RECORDS' },
];

// ── Helpers ───────────────────────────────────────────────────────────────

function clamp01to100(value: number): number {
  return Math.max(0, Math.min(100, value));
}

/**
 * Churn → indigo luminance. Deliberately narrow, exactly like the landing
 * chapter: the brightest a file gets is still a long way from neon.
 */
function churnTone(score: number): string {
  const alpha = 0.26 + (clamp01to100(score) / 100) * 0.62;
  return `rgba(129, 140, 248, ${alpha.toFixed(3)})`;
}

/** Legible text tone for a churn figure. Never red — high churn is not a fault. */
function churnTextTone(score: number): string {
  if (score >= 80) return '#b6bdfa';
  if (score >= 50) return '#9aa3ee';
  if (score >= 20) return 'var(--text-muted)';
  return 'var(--text-subtle)';
}

/** The four bands, and the boundaries that define them. Derived, disclosed. */
const CHURN_BANDS = ['LOW', 'MODERATE', 'ELEVATED', 'HIGH'] as const;
type ChurnBand = (typeof CHURN_BANDS)[number];

function churnBand(score: number): ChurnBand {
  if (score >= 80) return 'HIGH';
  if (score >= 50) return 'ELEVATED';
  if (score >= 20) return 'MODERATE';
  return 'LOW';
}

/** `01`, `02`, … — a rank reads as an index, not as a quantity. */
function pad2(n: number): string {
  return String(n).padStart(2, '0');
}

/**
 * `AUG 10` from an ISO date, parsed by hand.
 * `new Date('2026-08-10')` is UTC midnight, so `toLocaleDateString` shifts the
 * label back a day for anyone west of Greenwich — the axis would then disagree
 * with the bucket it is labelling.
 */
const MONTHS = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'];

function formatWeek(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return iso;
  return `${MONTHS[Number(m[2]) - 1] ?? '—'} ${m[3]}`;
}

function formatWeekFull(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return iso;
  return `${MONTHS[Number(m[2]) - 1] ?? '—'} ${m[3]} ${m[1]}`;
}

/** `15 AUG 2026 · 09:00` — compact enough for one line in a footer. */
function formatGenerated(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const day = String(d.getDate()).padStart(2, '0');
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  return `${day} ${MONTHS[d.getMonth()]} ${d.getFullYear()} · ${hh}:${mm}`;
}

/** An author email, shortened to its local part when the row is tight. */
function authorLabel(email: string): string {
  if (!email) return 'UNATTRIBUTED';
  return email;
}

// ── Shared micro-primitives ───────────────────────────────────────────────

/**
 * One labelled reading. `LABEL 42` — the label recedes, the figure carries the
 * emphasis, and the pair stays on one line so a row of readings scans
 * horizontally rather than as a table.
 */
const Reading: React.FC<{
  label: string;
  value: React.ReactNode;
  tone?: string;
  className?: string;
}> = ({ label, value, tone, className = '' }) => (
  <span className={`inline-flex items-baseline gap-1.5 min-w-0 ${className}`}>
    <span
      className="font-mono uppercase shrink-0"
      style={{ fontSize: 8.5, letterSpacing: '0.2em', color: 'var(--text-subtle)' }}
    >
      {label}
    </span>
    <span
      className="gh-reading font-mono text-[11px] tabular-nums truncate"
      style={{ color: tone ?? 'var(--text-muted)' }}
    >
      {value}
    </span>
  </span>
);

/** A section heading with a subordinate criterion, on a hairline. */
const FieldHeading: React.FC<{
  id?: string;
  title: string;
  criterion: string;
  count?: string;
}> = ({ id, title, criterion, count }) => (
  <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1 pb-3 hair-b">
    <h3 id={id} className="mono-label">
      {title}
    </h3>
    <span className="flex items-baseline gap-4 shrink-0">
      {count && <span className="text-[11px] text-text-subtle tabular-nums">{count}</span>}
      <span className="mono-detail" style={{ fontSize: 9 }}>
        {criterion}
      </span>
    </span>
  </div>
);

/** Absent data, in the shared vocabulary. Never an invented positive. */
const NoSignal: React.FC<{ label: string; detail: string }> = ({ label, detail }) => (
  <div className="pt-6 pb-2">
    <span className="mono-label block mb-2">{label}</span>
    <p className="text-[13px] text-text-muted leading-relaxed max-w-lg">{detail}</p>
  </div>
);

/**
 * The churn intensity scale — why a score reads as a hotspot.
 *
 * The band boundaries are drawn as ticks and the marker sits at the measured
 * value, so the reader can see which side of which threshold the file fell on
 * instead of being handed a word.
 */
const ChurnScale: React.FC<{ score: number }> = ({ score }) => {
  const band = churnBand(score);
  const pos = clamp01to100(score);

  return (
    <div className="min-w-0">
      <div className="gh-scale" aria-hidden="true">
        <span className="gh-scale-track" />
        <span className="gh-scale-tick" style={{ left: '20%' }} />
        <span className="gh-scale-tick" style={{ left: '50%' }} />
        <span className="gh-scale-tick" style={{ left: '80%' }} />
        <span className="gh-scale-marker" style={{ left: `${pos}%` }} />
      </div>

      <div
        className="mt-2 flex items-baseline justify-between font-mono uppercase"
        style={{ fontSize: 8.5, letterSpacing: '0.16em' }}
        aria-hidden="true"
      >
        {CHURN_BANDS.map((b) => (
          <span
            key={b}
            style={{ color: b === band ? 'var(--primary)' : 'var(--text-subtle)' }}
          >
            {b}
          </span>
        ))}
      </div>

      <p className="mono-detail mt-2" style={{ fontSize: 9 }}>
        {band} · {score.toFixed(1)} / 100 · BAND BOUNDARIES 20 / 50 / 80 · DERIVED FROM CHURN SCORE
      </p>
    </div>
  );
};

// ── Hotspot evidence record ───────────────────────────────────────────────

/**
 * The expanded reading for one hotspot: FILE → CHURN → CENTRALITY → OWNERSHIP
 * → SIGNAL, arriving in that order down an indigo evidence rail.
 *
 * `.evidence-surface` draws the rail and resolves the panel out of a blur;
 * `.evidence-stack` staggers the fields positionally, so nothing here needs to
 * know its own index.
 */
const HotspotEvidence: React.FC<{ h: HotspotFile }> = ({ h }) => (
  <div className="evidence-surface ml-3 sm:ml-[3.4rem] mr-3 sm:mr-4 mb-4 pl-4 sm:pl-5">
    <dl className="evidence-stack space-y-4">
      <div className="min-w-0">
        <dt className="mono-label mb-1.5" style={{ fontSize: 9 }}>
          FILE
        </dt>
        <dd className="min-w-0">
          <FilePath path={h.file_path} tone="secondary" size="sm" />
        </dd>
      </div>

      <div className="min-w-0">
        <dt className="mono-label mb-1.5" style={{ fontSize: 9 }}>
          CHURN INTENSITY
        </dt>
        <dd className="min-w-0 max-w-md">
          <ChurnScale score={h.churn_score} />
        </dd>
      </div>

      <div className="min-w-0">
        <dt className="mono-label mb-1.5" style={{ fontSize: 9 }}>
          CENTRALITY
        </dt>
        <dd className="min-w-0 max-w-md">
          <div className="meter" aria-hidden="true">
            <span
              style={{
                transform: `scaleX(${Math.max(h.centrality, 0.004)})`,
                backgroundColor: 'rgba(129, 140, 248, 0.75)',
              }}
            />
          </div>
          <p className="mono-detail mt-2" style={{ fontSize: 9 }}>
            {(h.centrality * 100).toFixed(1)}% DEGREE CENTRALITY · POSITION IN THE DEPENDENCY GRAPH
          </p>
        </dd>
      </div>

      <div className="min-w-0">
        <dt className="mono-label mb-1.5" style={{ fontSize: 9 }}>
          OWNERSHIP
        </dt>
        <dd className="min-w-0">
          <p className="font-mono text-[11.5px] text-text break-all">
            {h.primary_author || 'NOT AVAILABLE'}
          </p>
          <p
            className="mono-detail mt-1.5"
            style={{ fontSize: 9, color: h.bus_factor_risk ? 'var(--warn)' : undefined }}
          >
            {h.bus_factor_risk
              ? 'SINGLE OWNER · ONE AUTHOR HOLDS OVER 80% OF COMMITS ON THIS FILE'
              : `${h.commit_count.toLocaleString()} COMMITS IN THE ANALYSED WINDOW`}
          </p>
        </dd>
      </div>

      <div className="min-w-0">
        <dt className="mono-label mb-1.5" style={{ fontSize: 9 }}>
          SIGNAL
        </dt>
        <dd className="flex flex-wrap items-baseline gap-x-6 gap-y-1.5">
          <span
            className="font-mono text-[15px] font-bold tabular-nums"
            style={{ color: churnTextTone(h.churn_score) }}
          >
            {h.hotspot_score.toFixed(2)}
          </span>
          <span className="mono-detail" style={{ fontSize: 9 }}>
            COMPOSITE · CHURN {h.churn_score.toFixed(1)} × (1 + CENTRALITY{' '}
            {h.centrality.toFixed(3)})
          </span>
        </dd>
      </div>
    </dl>
  </div>
);

/**
 * One record in the heat field.
 *
 * The signal bar is the hero: its length is this file's composite score against
 * the strongest signal in the field, so the column of bars reads as a
 * distribution rather than as twenty-five identical rows. Luminance is churn.
 */
const HotspotRecord: React.FC<{
  h: HotspotFile;
  rank: number;
  maxScore: number;
}> = ({ h, rank, maxScore }) => {
  const [open, setOpen] = useState(false);
  const [ref, revealed] = useRevealed<HTMLLIElement>();

  // A floor of 2% so the weakest signal in the field is still visibly present.
  const reach = maxScore > 0 ? Math.max(h.hotspot_score / maxScore, 0.02) : 0;
  const panelId = `gh-hotspot-${rank}`;

  return (
    <li ref={ref} className="gh-row min-w-0">
      <button
        type="button"
        onClick={() => setOpen((p) => !p)}
        aria-expanded={open}
        aria-controls={panelId}
        className="w-full text-left grid grid-cols-[1.9rem_minmax(0,1fr)_auto] sm:grid-cols-[2.6rem_minmax(0,1fr)_auto]
                   items-start gap-x-2 sm:gap-x-4 px-3 sm:px-4 py-3.5"
      >
        <span
          className="gh-rank font-mono text-[11px] tabular-nums pt-[3px]"
          style={{ color: 'var(--text-subtle)' }}
        >
          {pad2(rank)}
        </span>

        <span className="block min-w-0">
          <FilePath path={h.file_path} tone="primary" size="sm" />

          <span className="gh-signal mt-2.5" aria-hidden="true">
            <span
              className="gh-signal-fill"
              style={
                {
                  '--gh-reach': revealed ? String(reach) : '0',
                  '--gh-delay': `${Math.min(rank, 14) * 45}ms`,
                  backgroundColor: churnTone(h.churn_score),
                } as React.CSSProperties
              }
            />
          </span>

          <span className="mt-2.5 flex flex-wrap items-baseline gap-x-5 gap-y-1.5">
            <Reading
              label="CHURN"
              value={h.churn_score.toFixed(0)}
              tone={churnTextTone(h.churn_score)}
            />
            <Reading label="BAND" value={churnBand(h.churn_score)} />
            <Reading label="CENTRALITY" value={`${(h.centrality * 100).toFixed(1)}%`} />
            <Reading label="COMMITS" value={h.commit_count.toLocaleString()} />
            {h.bus_factor_risk && (
              <span
                className="inline-flex items-center gap-1.5 font-mono uppercase shrink-0"
                style={{ fontSize: 8.5, letterSpacing: '0.2em', color: 'var(--warn)' }}
              >
                <AlertTriangle className="h-2.5 w-2.5" aria-hidden="true" />
                SINGLE OWNER
              </span>
            )}
          </span>
        </span>

        <span className="flex items-baseline gap-2 shrink-0 pt-[1px]">
          <span
            className="font-mono text-[14px] sm:text-[15px] font-bold tabular-nums"
            style={{ color: churnTextTone(h.churn_score) }}
          >
            {h.hotspot_score.toFixed(1)}
          </span>
          <ChevronDown
            className={`h-3 w-3 shrink-0 text-text-subtle transition-transform duration-200 ${
              open ? 'rotate-180' : ''
            }`}
            aria-hidden="true"
          />
        </span>
      </button>

      {open && (
        <div id={panelId}>
          <HotspotEvidence h={h} />
        </div>
      )}
    </li>
  );
};

// ── Temporal field (timeline) ─────────────────────────────────────────────

/**
 * Weekly commit activity as a measured window rather than a list of weeks.
 *
 * Markers sit on the same axis the landing chapter uses (`.era-axis` /
 * `.era-ticks`, both driven by `--p`), rise once when the field is reached, and
 * then rest. Hovering or focusing a marker fills the read-out above it; the
 * read-out's height is reserved so moving along the axis never reflows the page.
 *
 * The field defaults to the busiest week so it says something before it is
 * touched, and so keyboard users are not the only ones who ever see a detail.
 */
const TemporalField: React.FC<{ entries: TimelineEntry[] }> = ({ entries }) => {
  const [hovered, setHovered] = useState<number | null>(null);
  const [ref, revealed] = useRevealed<HTMLDivElement>();

  /* The most recent 32 buckets: enough to show a shape, few enough that each
   * marker keeps a usable hit area at 375px. */
  const visible = useMemo(() => entries.slice(-32), [entries]);

  const maxCommits = useMemo(
    () => Math.max(...visible.map((e) => e.commit_count), 1),
    [visible],
  );
  const maxAuthors = useMemo(
    () => Math.max(...visible.map((e) => e.authors.length), 1),
    [visible],
  );
  const peakIndex = useMemo(
    () => visible.reduce((best, e, i) => (e.commit_count > visible[best].commit_count ? i : best), 0),
    [visible],
  );

  const activeIndex = hovered ?? peakIndex;
  const active = visible[activeIndex];
  const first = visible[0];
  const last = visible[visible.length - 1];
  const middle = visible[Math.floor((visible.length - 1) / 2)];

  return (
    <div ref={ref} className="min-w-0">
      {/*
        Read-out. Height is reserved for the tallest state this block can reach
        — three wrapped reading lines at 375px — so travelling the axis never
        moves the field underneath the pointer.
      */}
      <div className="min-h-[5.5rem] sm:min-h-[3.25rem]" aria-live="polite">
        <span className="mono-label mono-label-accent block mb-2">
          {formatWeekFull(active.week)}
        </span>
        <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1.5">
          <Reading
            label="COMMITS"
            value={active.commit_count.toLocaleString()}
            tone="var(--text)"
          />
          <Reading label="FILES CHANGED" value={active.files_changed.toLocaleString()} />
          <Reading label="AUTHORS" value={active.authors.length.toLocaleString()} />
          <span className="mono-detail" style={{ fontSize: 9 }}>
            {hovered === null ? 'BUSIEST WEEK IN WINDOW · HOVER A MARKER' : 'SELECTED BUCKET'}
          </span>
        </div>
      </div>

      {/* Commit density. One marker per weekly bucket. */}
      <div
        className="relative mt-3 flex h-24 items-end gap-[2px]"
        onMouseLeave={() => setHovered(null)}
      >
        {visible.map((entry, i) => (
          <button
            key={entry.week}
            type="button"
            className="gh-week"
            onMouseEnter={() => setHovered(i)}
            onFocus={() => setHovered(i)}
            onBlur={() => setHovered(null)}
            aria-label={`Week of ${entry.week}: ${entry.commit_count} commits, ${entry.files_changed} files changed, ${entry.authors.length} authors`}
          >
            <span
              className="gh-week-bar"
              style={
                {
                  '--gh-h': revealed
                    ? String(Math.max(entry.commit_count / maxCommits, 0.025))
                    : '0',
                  '--gh-delay': `${Math.min(i, 32) * 16}ms`,
                  backgroundColor: churnTone((entry.commit_count / maxCommits) * 100),
                } as React.CSSProperties
              }
            />
          </button>
        ))}
      </div>

      {/* The axis itself, drawn once the field is reached. */}
      <div
        className="era-axis"
        style={{ ['--p' as string]: revealed ? '1' : '0' }}
        aria-hidden="true"
      />
      <div
        className="era-ticks"
        style={{ ['--p' as string]: revealed ? '1' : '0' }}
        aria-hidden="true"
      />

      <div className="mt-2 flex items-baseline justify-between gap-2">
        <span className="mono-label tabular-nums">{formatWeek(first.week)}</span>
        <span className="mono-label tabular-nums hidden sm:inline">{formatWeek(middle.week)}</span>
        <span className="mono-label tabular-nums">{formatWeek(last.week)}</span>
      </div>

      {/* Author density on the same horizontal scale — how many distinct people
        * were active in each bucket, so concentration is visible against volume. */}
      <div className="mt-6">
        <span className="mono-label block mb-2" style={{ fontSize: 9 }}>
          AUTHOR DENSITY
        </span>
        <div className="flex items-center gap-[2px]" aria-hidden="true">
          {visible.map((entry) => (
            <span
              key={`d-${entry.week}`}
              className="gh-density"
              style={{ opacity: revealed ? 0.16 + (entry.authors.length / maxAuthors) * 0.78 : 0 }}
            />
          ))}
        </div>
        <p className="mono-detail mt-2" style={{ fontSize: 9 }}>
          DISTINCT AUTHORS PER WEEK · PEAK {maxAuthors.toLocaleString()}
        </p>
      </div>

      {/* Accessible equivalent of the field. */}
      <p className="sr-only">
        Weekly commit activity across {visible.length} buckets, from{' '}
        {formatWeekFull(first.week)} to {formatWeekFull(last.week)}. Busiest week{' '}
        {formatWeekFull(visible[peakIndex].week)} with{' '}
        {visible[peakIndex].commit_count} commits.
      </p>
    </div>
  );
};

// ── Ownership field (authors) ─────────────────────────────────────────────

interface AuthorRollup {
  email: string;
  commits: number;
  filesTouched: number;
  filesOwned: number;
  /** Share of all commits recorded across the ownership sample, 0–100. */
  share: number;
}

/**
 * Roll the per-file ownership records up to per-author totals.
 *
 * Every figure is a sum or a count over `contributors` and `primary_author` as
 * the backend supplied them — no new metric is invented, and the sample is the
 * same one the payload carries (the backend returns the top 50 files by
 * ownership), which the section discloses.
 */
function rollupAuthors(records: AuthorOwnership[]): AuthorRollup[] {
  const acc = new Map<string, { commits: number; filesTouched: number; filesOwned: number }>();

  for (const record of records) {
    for (const [email, commits] of Object.entries(record.contributors)) {
      const current = acc.get(email) ?? { commits: 0, filesTouched: 0, filesOwned: 0 };
      current.commits += commits;
      current.filesTouched += 1;
      if (record.primary_author === email) current.filesOwned += 1;
      acc.set(email, current);
    }
  }

  const total = [...acc.values()].reduce((sum, a) => sum + a.commits, 0);

  return [...acc.entries()]
    .map(([email, v]) => ({
      email,
      ...v,
      share: total > 0 ? (v.commits / total) * 100 : 0,
    }))
    .sort((a, b) => b.commits - a.commits || b.filesOwned - a.filesOwned);
}

/** One author's concentration across the recorded files. */
const AuthorRow: React.FC<{ author: AuthorRollup; rank: number; maxShare: number }> = ({
  author,
  rank,
  maxShare,
}) => {
  const [ref, revealed] = useRevealed<HTMLLIElement>();
  const concentrated = author.share >= 50;
  const reach = maxShare > 0 ? Math.max(author.share / maxShare, 0.02) : 0;

  return (
    <li ref={ref} className="gh-own min-w-0">
      <div className="grid grid-cols-[1.9rem_minmax(0,1fr)] sm:grid-cols-[2.6rem_minmax(0,1fr)_auto]
                      items-start gap-x-2 sm:gap-x-4 px-3 sm:px-4 py-3.5">
        <span
          className="font-mono text-[11px] tabular-nums pt-[3px]"
          style={{ color: 'var(--text-subtle)' }}
        >
          {pad2(rank)}
        </span>

        <div className="min-w-0">
          <p className="font-mono text-[12px] text-text break-all leading-snug">
            {authorLabel(author.email)}
          </p>

          <div className="gh-signal mt-2.5" aria-hidden="true">
            <span
              className="gh-signal-fill"
              style={
                {
                  '--gh-reach': revealed ? String(reach) : '0',
                  '--gh-delay': `${Math.min(rank, 14) * 45}ms`,
                  backgroundColor: concentrated
                    ? 'rgba(245, 158, 11, 0.62)'
                    : 'rgba(129, 140, 248, 0.72)',
                } as React.CSSProperties
              }
            />
          </div>

          <div className="mt-2.5 flex flex-wrap items-baseline gap-x-5 gap-y-1.5">
            <Reading
              label="COMMITS"
              value={author.commits.toLocaleString()}
              tone="var(--text)"
            />
            <Reading label="FILES TOUCHED" value={author.filesTouched.toLocaleString()} />
            <Reading label="FILES OWNED" value={author.filesOwned.toLocaleString()} />
            {concentrated && (
              <span
                className="inline-flex items-center gap-1.5 font-mono uppercase shrink-0"
                style={{ fontSize: 8.5, letterSpacing: '0.2em', color: 'var(--warn)' }}
              >
                <AlertTriangle className="h-2.5 w-2.5" aria-hidden="true" />
                CONCENTRATED
              </span>
            )}
          </div>
        </div>

        <span
          className="hidden sm:flex items-baseline gap-1.5 shrink-0 pt-[1px] font-mono tabular-nums"
          style={{ color: concentrated ? 'var(--warn)' : 'var(--text)' }}
        >
          <span className="text-[15px] font-bold">{author.share.toFixed(1)}</span>
          <span style={{ fontSize: 9, color: 'var(--text-subtle)' }}>%</span>
        </span>
      </div>
    </li>
  );
};

/** One file whose commits concentrate on a single author. */
const OwnershipRow: React.FC<{ record: AuthorOwnership }> = ({ record }) => {
  const [ref, revealed] = useRevealed<HTMLLIElement>();
  const single = record.ownership_pct > 80;

  return (
    <li ref={ref} className="gh-own min-w-0">
      <div className="px-3 sm:px-4 py-3.5 min-w-0">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1.5 min-w-0">
          <FilePath path={record.file_path} tone="primary" size="sm" />
          <span
            className="font-mono text-[12px] tabular-nums shrink-0"
            style={{ color: single ? 'var(--warn)' : 'var(--text-muted)' }}
          >
            {record.ownership_pct.toFixed(0)}%
          </span>
        </div>

        <div className="meter mt-2.5 max-w-md" aria-hidden="true">
          <span
            style={{
              transform: `scaleX(${revealed ? Math.max(record.ownership_pct / 100, 0.01) : 0})`,
              backgroundColor: single ? 'rgba(245, 158, 11, 0.62)' : 'rgba(129, 140, 248, 0.72)',
            }}
          />
        </div>

        <div className="mt-2.5 flex flex-wrap items-baseline gap-x-5 gap-y-1.5 min-w-0">
          <Reading
            label="PRIMARY"
            value={authorLabel(record.primary_author)}
            className="max-w-full"
          />
          <Reading
            label="CONTRIBUTORS"
            value={Object.keys(record.contributors).length.toLocaleString()}
          />
          {single && (
            <span
              className="font-mono uppercase shrink-0"
              style={{ fontSize: 8.5, letterSpacing: '0.2em', color: 'var(--warn)' }}
            >
              SINGLE OWNER
            </span>
          )}
        </div>
      </div>
    </li>
  );
};

/**
 * Bounded registry: a preview, then a fixed-height scroll region.
 *
 * Bounded rather than growing, so a repository with hundreds of records does not
 * turn the panel into an unnavigable column. Same device the dead-code audit
 * uses, so the two surfaces expand the same way.
 */
const BoundedRegistry: React.FC<{
  total: number;
  preview: number;
  noun: string;
  children: (limit: number) => React.ReactNode;
}> = ({ total, preview, noun, children }) => {
  const [expanded, setExpanded] = useState(false);
  const overflow = total > preview;
  const shown = expanded ? total : Math.min(preview, total);

  return (
    <>
      <p className="mono-detail mb-2.5 tabular-nums" style={{ fontSize: 9 }}>
        SHOWING {shown.toLocaleString()} OF {total.toLocaleString()}
      </p>

      <div className={expanded ? 'max-h-[26rem] overflow-y-auto pr-1 -mr-1 min-w-0' : 'min-w-0'}>
        {children(shown)}
      </div>

      {overflow && (
        <button
          type="button"
          onClick={() => setExpanded((p) => !p)}
          className="api-action link-arrow mt-4"
          aria-expanded={expanded}
        >
          {expanded ? `SHOW FEWER ${noun}` : `VIEW ALL ${total.toLocaleString()} ${noun}`}
          <ArrowRight className="h-3 w-3 arrow ml-1" aria-hidden="true" />
        </button>
      )}
    </>
  );
};

// ── Main component ────────────────────────────────────────────────────────

export const GitHistoryAnalyzer: React.FC<Props> = ({ repoName }) => {
  const [summary, setSummary] = useState<ChurnSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState('');
  const [phase, setPhase] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [sinceDays, setSinceDays] = useState(365);
  const [activeView, setActiveView] = useState<ViewId>('hotspots');

  const railRefs = useRef<(HTMLButtonElement | null)[]>([]);

  const [owner, repo] = repoName.split('/');

  // Try loading cached summary on first mount or sinceDays change
  React.useEffect(() => {
    setSummary(null);
    setError(null);
    fetch(apiUrl(`/api/v1/churn/${owner}/${repo}?since_days=${sinceDays}`))
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => { if (d) setSummary(d); })
      .catch(() => { /* no cached data — show empty state */ });
  }, [repoName, sinceDays, owner, repo]);

  const runAnalysis = useCallback(async () => {
    setLoading(true);
    setError(null);
    setProgress('Starting…');
    setPhase(0);
    setSummary(null);

    try {
      const res = await fetch(apiUrl('/api/v1/churn/analyze'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ repo: repoName, since_days: sinceDays }),
      });

      if (!res.body) throw new Error('No response body from server.');

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split('\n\n');
        buffer = parts.pop() ?? '';

        for (const part of parts) {
          const line = part.replace(/^data: /, '').trim();
          if (!line) continue;
          try {
            const event = JSON.parse(line);
            if (event.status === 'error') {
              setError(event.message);
              setLoading(false);
              return;
            }
            if (event.status === 'done') { setLoading(false); return; }
            if (event.status === 'result' && event.data) {
              setSummary(event.data as ChurnSummary);
            } else {
              /* Advance the phase rail from the stream's own status values, so
               * the read-out reports the pipeline rather than a timer. Unknown
               * statuses leave the rail where it is. */
              const next = PHASE_OF_STATUS[event.status as string];
              if (next !== undefined) setPhase((p) => Math.max(p, next));
              if (event.message) setProgress(event.message);
            }
          } catch { /* non-JSON line — skip */ }
        }
      }
    } catch (err: any) {
      setError(extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [repoName, sinceDays]);

  const onRailKeyDown = useCallback((e: React.KeyboardEvent, index: number) => {
    const last = VIEWS.length - 1;
    let next = index;
    if (e.key === 'ArrowRight') next = index === last ? 0 : index + 1;
    else if (e.key === 'ArrowLeft') next = index === 0 ? last : index - 1;
    else if (e.key === 'Home') next = 0;
    else if (e.key === 'End') next = last;
    else return;
    e.preventDefault();
    setActiveView(VIEWS[next].id);
    railRefs.current[next]?.focus();
  }, []);

  const activeIndex = VIEWS.findIndex((v) => v.id === activeView);
  const busFactorFiles = summary?.hotspots.filter((h) => h.bus_factor_risk).length ?? 0;
  const maxHotspotScore = summary?.hotspots.reduce((m, h) => Math.max(m, h.hotspot_score), 0) ?? 0;

  const authors = useMemo(
    () => (summary ? rollupAuthors(summary.author_ownership) : []),
    [summary],
  );
  const maxAuthorShare = authors.length > 0 ? authors[0].share : 0;
  const singleOwnerFiles = useMemo(
    () => (summary?.author_ownership ?? []).filter((r) => r.ownership_pct > 80).length,
    [summary],
  );

  /** The header's one-word verdict on what the window actually yielded. */
  const signal = loading
    ? 'ANALYZING'
    : error
      ? 'ANALYSIS FAILED'
      : !summary
        ? 'NO DATA'
        : summary.warning
          ? 'LIMITED HISTORY'
          : summary.hotspots.length > 0
            ? 'HOTSPOTS RESOLVED'
            : 'NO HOTSPOTS DETECTED';

  const readouts: { k: string; v: string }[] = [
    { k: 'HISTORY WINDOW', v: `${sinceDays}D` },
    { k: 'COMMITS', v: summary ? summary.total_commits.toLocaleString() : '—' },
    { k: 'FILES', v: summary ? summary.total_files.toLocaleString() : '—' },
    { k: 'SIGNAL', v: signal },
  ];

  const metrics: { k: string; v: string; hint: string }[] = [
    {
      k: 'COMMITS MINED',
      v: summary ? summary.total_commits.toLocaleString() : '—',
      hint: `LAST ${sinceDays} DAYS`,
    },
    {
      k: 'FILES TRACKED',
      v: summary ? summary.total_files.toLocaleString() : '—',
      hint: 'IN HISTORY WINDOW',
    },
    {
      k: 'HOTSPOTS',
      v: summary ? summary.hotspots.length.toLocaleString() : '—',
      hint: 'HIGH CHURN · CENTRAL',
    },
    {
      k: 'BUS FACTOR FILES',
      v: summary ? busFactorFiles.toLocaleString() : '—',
      hint: 'SINGLE-OWNER RISK',
    },
  ];

  return (
    <div className="relative flex flex-col text-text min-w-0">
      <div className="gh-bloom" aria-hidden="true" />

      {/* ── 01 · Analysis header ─────────────────────────────────────────── */}
      <header className="relative min-w-0">
        <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-5">
          <div className="min-w-0 max-w-2xl">
            <span className="mono-label mono-label-accent block mb-2.5">
              GIT HISTORY / REPOSITORY MEMORY
            </span>
            <h2 className="display-3 text-text">Git History &amp; Churn Analysis</h2>
            <p className="text-[13px] text-text-muted leading-relaxed mt-3 max-w-xl">
              Identify hotspot files, author ownership risk, and commit activity trends.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2.5 shrink-0">
            <label htmlFor="since-days" className="sr-only">
              History window
            </label>
            <select
              id="since-days"
              value={sinceDays}
              onChange={(e) => setSinceDays(Number(e.target.value))}
              /* `w-auto` overrides `.input`'s `w-full` — this select sits in a
                 control row, not in a form column. */
              className="input w-auto py-1.5 pr-7 text-[11px] tracking-[0.14em] uppercase"
              disabled={loading}
            >
              <option value={90}>Last 90 days</option>
              <option value={180}>Last 180 days</option>
              <option value={365}>Last 1 year</option>
              <option value={730}>Last 2 years</option>
            </select>

            <button
              type="button"
              onClick={runAnalysis}
              disabled={loading}
              className="action-chip shrink-0 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {loading ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                  Analyzing
                </>
              ) : (
                <>
                  {summary ? 'Re-analyze' : 'Analyze History'}
                  <ArrowRight className="h-3 w-3" aria-hidden="true" />
                </>
              )}
            </button>
          </div>
        </div>

        {/* Instrument read-out: the window, what it yielded, and what it means. */}
        <dl className="mt-6 flex flex-wrap items-baseline gap-x-7 gap-y-2">
          {readouts.map((r) => (
            <div key={r.k} className="flex items-baseline gap-2 min-w-0">
              <dt
                className="font-mono uppercase shrink-0"
                style={{ fontSize: 9, letterSpacing: '0.24em', color: 'rgba(255,255,255,0.36)' }}
              >
                {r.k}
              </dt>
              <dd className="font-mono text-[11px] tabular-nums text-text truncate">
                <span style={{ color: 'var(--text-subtle)' }}>// </span>
                {r.v}
              </dd>
            </div>
          ))}
        </dl>

        {/* ── Phase rail, while the stream is open ───────────────────────── */}
        {loading && (
          <div className="mt-7" role="status" aria-live="polite">
            <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 pb-2.5">
              <span className="mono-label mono-label-accent">ANALYZING HISTORY</span>
              <span className="mono-detail" style={{ fontSize: 9 }}>
                PIPELINE STAGE · FROM ANALYSIS STREAM
              </span>
            </div>

            <div className="gh-scan" aria-hidden="true" />

            <ol className="mt-3 flex flex-wrap gap-x-6 gap-y-1.5">
              {PHASES.map((p, i) => (
                <li
                  key={p}
                  className="gh-phase flex items-center gap-2 font-mono uppercase"
                  style={{
                    fontSize: 9,
                    letterSpacing: '0.2em',
                    color: i === phase ? 'var(--primary)' : 'var(--text-subtle)',
                    opacity: i <= phase ? 1 : 0.34,
                  }}
                  aria-current={i === phase ? 'step' : undefined}
                >
                  <span className="gh-phase-dot" aria-hidden="true" />
                  {p}
                </li>
              ))}
            </ol>

            {progress && (
              <p className="mono-detail mt-2.5" style={{ fontSize: 10 }}>
                {progress}
              </p>
            )}
          </div>
        )}

        {/* ── Diagnostic notices ─────────────────────────────────────────── */}
        {error && (
          <div role="alert" className="gh-notice gh-notice--error mt-7">
            <AlertTriangle
              className="h-3 w-3 shrink-0 mt-[3px] text-danger"
              aria-hidden="true"
            />
            <div className="min-w-0">
              <span
                className="mono-label block"
                style={{ fontSize: 9, color: 'var(--danger)' }}
              >
                ANALYSIS FAILED
              </span>
              <p className="text-[11.5px] text-text-muted leading-relaxed mt-1 break-words">
                {error}
              </p>
            </div>
          </div>
        )}

        {summary?.warning && (
          <div role="status" className="gh-notice mt-7">
            <AlertTriangle className="h-3 w-3 shrink-0 mt-[3px] text-warn" aria-hidden="true" />
            <div className="min-w-0">
              <span className="mono-label block" style={{ fontSize: 9, color: 'var(--warn)' }}>
                LIMITED HISTORY
              </span>
              <p className="text-[11.5px] text-text-muted leading-relaxed mt-1 break-words">
                {summary.warning}
              </p>
            </div>
          </div>
        )}
      </header>

      {/* ── Loading ──────────────────────────────────────────────────────── */}
      {loading && !summary && (
        <div className="mt-9">
          <SkeletonGroup label="Mining git history">
            <div className="space-y-4">
              <SkeletonCard />
              <SkeletonCard />
            </div>
          </SkeletonGroup>
        </div>
      )}

      {/* ── Compact empty state, integrated with the analysis ───────────── */}
      {!loading && !summary && !error && (
        <div className="mt-9 pt-6 hair-t">
          <span className="mono-label block mb-2.5">NO CHURN DATA FOR THIS WINDOW</span>
          <p className="text-[13px] text-text-muted leading-relaxed max-w-lg">
            The git log has not been mined for this repository over the last {sinceDays} days.
            Mining it identifies which files change most, where that change lands in the dependency
            graph, and which files depend on a single author.
          </p>
          <button type="button" onClick={runAnalysis} className="api-action link-arrow mt-4">
            ANALYZE HISTORY
            <ArrowRight className="h-3 w-3 arrow ml-1" aria-hidden="true" />
          </button>
        </div>
      )}

      {/* ── Results ──────────────────────────────────────────────────────── */}
      {summary && !loading && (
        <>
          {/* ── 02 · Activity signal (telemetry) ───────────────────────── */}
          <Reveal className="mt-10 min-w-0">
            <FieldHeading
              title="ACTIVITY SIGNAL"
              criterion={`HISTORY / 02 · WINDOW ${summary.since_days}D`}
            />
            <dl className="gh-telemetry mt-1">
              {metrics.map((m, i) => (
                /* No tabIndex: the hover response is confirmation, not
                   information, so it must not add four inert tab stops. */
                <div key={m.k} className="gh-metric">
                  {/* The label wraps rather than truncates — at 375px the
                      longest of the four ("BUS FACTOR FILES") needs two lines,
                      and a clipped telemetry label is unreadable. Height is
                      reserved in CSS so all four values keep one baseline. */}
                  <div className="gh-metric-label flex items-baseline gap-2 mb-2 min-w-0">
                    <span
                      className="font-mono tabular-nums shrink-0"
                      style={{ fontSize: 9, color: 'var(--text-subtle)' }}
                    >
                      {pad2(i + 1)}
                    </span>
                    <dt className="mono-label" style={{ fontSize: 9, lineHeight: 1.45 }}>
                      {m.k}
                    </dt>
                  </div>
                  <dd className="gh-metric-value readout-value">{m.v}</dd>
                  <p className="mono-detail mt-1.5" style={{ fontSize: 9 }}>
                    {m.hint}
                  </p>
                </div>
              ))}
            </dl>
          </Reveal>

          {/* ── 03 · Instrument rail ───────────────────────────────────── */}
          <Reveal className="mt-10 min-w-0" delay={60}>
            <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1 mb-2.5">
              <span className="mono-label">ANALYSIS INSTRUMENT</span>
              <span className="mono-detail" style={{ fontSize: 9 }}>
                HISTORY / 03 · {VIEWS[activeIndex]?.criterion}
              </span>
            </div>

            <div
              className="gh-rail"
              role="tablist"
              aria-label="Churn analysis views"
              style={{ ['--gh-tab' as string]: String(activeIndex) }}
            >
              {VIEWS.map((v, i) => (
                <button
                  key={v.id}
                  ref={(el) => { railRefs.current[i] = el; }}
                  type="button"
                  role="tab"
                  id={`gh-tab-${v.id}`}
                  aria-selected={activeView === v.id}
                  aria-controls={`gh-panel-${v.id}`}
                  tabIndex={activeView === v.id ? 0 : -1}
                  onClick={() => setActiveView(v.id)}
                  onKeyDown={(e) => onRailKeyDown(e, i)}
                  className="gh-rail-item"
                >
                  <span
                    className="gh-rail-index font-mono tabular-nums shrink-0"
                    style={{ fontSize: 9 }}
                  >
                    {pad2(i + 1)}
                  </span>
                  <span
                    className="font-mono uppercase truncate"
                    style={{ fontSize: 11, letterSpacing: '0.16em' }}
                  >
                    {v.label}
                  </span>
                </button>
              ))}
            </div>
          </Reveal>

          {/* ── 04 · Evidence ──────────────────────────────────────────── */}
          <div className="mt-9 min-w-0">
            {/* Hotspot heat field */}
            {activeView === 'hotspots' && (
              <section
                id="gh-panel-hotspots"
                role="tabpanel"
                aria-labelledby="gh-tab-hotspots"
                /* tabIndex per the tabs pattern, so the panel is reachable
                   straight after the rail. The focus ring is left to the
                   browser default — a focusable region must stay visible. */
                tabIndex={0}
                className="min-w-0"
              >
                <FieldHeading
                  id="gh-hotspot-heading"
                  title="HOTSPOT FIELD"
                  criterion="CHURN × (1 + CENTRALITY)"
                  count={
                    summary.hotspots.length > 0
                      ? `${summary.hotspots.length} FILES`
                      : undefined
                  }
                />

                {summary.hotspots.length === 0 ? (
                  <NoSignal
                    label="NO HOTSPOTS DETECTED"
                    detail="No file in this window combines high churn with a central position in the dependency graph."
                  />
                ) : (
                  <>
                    <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1.5 mt-4 mb-1">
                      <span className="mono-detail" style={{ fontSize: 9 }}>
                        BAR LENGTH — COMPOSITE SIGNAL · LUMINANCE — CHURN
                      </span>
                      <span className="mono-detail" style={{ fontSize: 9 }}>
                        STRONGEST SIGNAL {maxHotspotScore.toFixed(1)}
                      </span>
                    </div>

                    <div className="relative min-w-0">
                      <div className="gh-trace" aria-hidden="true" />
                      <span className="tech-cross" style={{ left: -4, top: -4 }} aria-hidden="true" />
                      <span
                        className="tech-cross"
                        style={{ right: -4, bottom: -4 }}
                        aria-hidden="true"
                      />
                      <ol className="relative min-w-0">
                        {summary.hotspots.map((h, i) => (
                          <HotspotRecord
                            key={h.file_path}
                            h={h}
                            rank={i + 1}
                            maxScore={maxHotspotScore}
                          />
                        ))}
                      </ol>
                    </div>

                    <p className="mono-detail mt-4" style={{ fontSize: 9 }}>
                      {busFactorFiles.toLocaleString()} OF {summary.hotspots.length.toLocaleString()}{' '}
                      HOTSPOTS DEPEND ON A SINGLE AUTHOR
                    </p>
                  </>
                )}
              </section>
            )}

            {/* Temporal field */}
            {activeView === 'timeline' && (
              <section
                id="gh-panel-timeline"
                role="tabpanel"
                aria-labelledby="gh-tab-timeline"
                tabIndex={0}
                className="min-w-0"
              >
                <FieldHeading
                  title="COMMIT ACTIVITY OVER TIME"
                  criterion="WEEKLY BUCKETS · WEEK STARTS MONDAY"
                  count={
                    summary.timeline.length > 0
                      ? `${summary.timeline.length} WEEKS`
                      : undefined
                  }
                />

                {summary.timeline.length === 0 ? (
                  <NoSignal
                    label="NO TIMELINE DATA"
                    detail="No weekly commit buckets were produced for this window."
                  />
                ) : (
                  <>
                    <div className="mt-5">
                      <TemporalField entries={summary.timeline} />
                    </div>

                    <div className="mt-9 pt-6 hair-t min-w-0">
                      <FieldHeading
                        title="WEEK REGISTRY"
                        criterion="MOST RECENT FIRST"
                      />
                      <div className="mt-3">
                        <BoundedRegistry
                          total={summary.timeline.length}
                          preview={10}
                          noun="WEEKS"
                        >
                          {(limit) => (
                            <ol className="min-w-0">
                              {[...summary.timeline]
                                .reverse()
                                .slice(0, limit)
                                .map((entry) => (
                                  <li key={entry.week} className="gh-own min-w-0">
                                    <div className="flex flex-wrap items-baseline gap-x-5 gap-y-1 px-3 sm:px-4 py-2.5">
                                      <span className="font-mono text-[11px] tabular-nums text-text w-[5.5rem] shrink-0">
                                        {formatWeekFull(entry.week)}
                                      </span>
                                      <Reading
                                        label="COMMITS"
                                        value={entry.commit_count.toLocaleString()}
                                        tone="var(--text)"
                                      />
                                      <Reading
                                        label="FILES"
                                        value={entry.files_changed.toLocaleString()}
                                      />
                                      <Reading
                                        label="AUTHORS"
                                        value={entry.authors.length.toLocaleString()}
                                      />
                                    </div>
                                  </li>
                                ))}
                            </ol>
                          )}
                        </BoundedRegistry>
                      </div>
                    </div>
                  </>
                )}
              </section>
            )}

            {/* Ownership field */}
            {activeView === 'authors' && (
              <section
                id="gh-panel-authors"
                role="tabpanel"
                aria-labelledby="gh-tab-authors"
                tabIndex={0}
                className="min-w-0"
              >
                <FieldHeading
                  title="AUTHOR CONCENTRATION"
                  criterion="DERIVED FROM PER-FILE OWNERSHIP RECORDS"
                  count={authors.length > 0 ? `${authors.length} AUTHORS` : undefined}
                />

                {summary.author_ownership.length === 0 ? (
                  <NoSignal
                    label="OWNERSHIP DATA NOT AVAILABLE"
                    detail="No per-file author attribution was produced for this window."
                  />
                ) : (
                  <>
                    <p className="mono-detail mt-4 mb-1" style={{ fontSize: 9 }}>
                      BAR LENGTH — SHARE OF COMMITS ACROSS{' '}
                      {summary.author_ownership.length.toLocaleString()} RECORDED FILES
                    </p>

                    <ol className="min-w-0">
                      {authors.slice(0, 12).map((a, i) => (
                        <AuthorRow
                          key={a.email}
                          author={a}
                          rank={i + 1}
                          maxShare={maxAuthorShare}
                        />
                      ))}
                    </ol>

                    {authors.length > 12 && (
                      <p className="mono-detail mt-3 tabular-nums" style={{ fontSize: 9 }}>
                        SHOWING 12 OF {authors.length.toLocaleString()} AUTHORS · RANKED BY COMMITS
                      </p>
                    )}

                    <div className="mt-10 pt-6 hair-t min-w-0">
                      <FieldHeading
                        title="OWNERSHIP BY FILE"
                        criterion="SINGLE OWNER — OVER 80% OF COMMITS"
                        count={
                          singleOwnerFiles > 0
                            ? `${singleOwnerFiles} SINGLE-OWNER`
                            : undefined
                        }
                      />
                      <div className="mt-3">
                        <BoundedRegistry
                          total={summary.author_ownership.length}
                          preview={8}
                          noun="FILES"
                        >
                          {(limit) => (
                            <ol className="min-w-0">
                              {summary.author_ownership.slice(0, limit).map((record) => (
                                <OwnershipRow key={record.file_path} record={record} />
                              ))}
                            </ol>
                          )}
                        </BoundedRegistry>
                      </div>
                    </div>
                  </>
                )}
              </section>
            )}
          </div>

          {/* ── Provenance ─────────────────────────────────────────────── */}
          <p className="mono-label mt-10 pt-5 hair-t" style={{ letterSpacing: '0.2em' }}>
            {summary.repo} · GIT LOG · {summary.since_days}D WINDOW · GENERATED{' '}
            {formatGenerated(summary.generated_at)}
          </p>
        </>
      )}
    </div>
  );
};

export default GitHistoryAnalyzer;

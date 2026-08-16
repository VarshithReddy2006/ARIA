/**
 * PRIntelligence — PR risk assessment.
 *
 * Answers one question: what could this pull request break? The surface reads in
 * that order:
 *
 *   PR → RISK → EVIDENCE → REVIEW FOCUS → FILE / SYMBOL IMPACT
 *
 * Every figure comes from `POST /api/v1/pr/analyze` unchanged — risk score,
 * blast radius, size bucket, counts, symbols and propagation paths are all
 * backend fields. Nothing here computes a new risk metric.
 *
 * Typography rule: uppercase monospace is reserved for labels, statuses, paths
 * and telemetry. Risk explanations and review-focus titles keep readable casing.
 */

import React, { useState, useEffect, useMemo } from 'react';
import { apiUrl, extractErrorMessage } from '../../lib/api';
import { AlertTriangle, ArrowRight, Loader2 } from 'lucide-react';
import { PRReferenceForm } from './pr/PRReferenceForm';
import { RiskGauge } from './pr/RiskGauge';
import { PrerequisitesBanner } from './pr/PrerequisitesBanner';
import { DiagnosticsPanel } from './pr/DiagnosticsPanel';
import { usePrerequisites } from './pr/usePrerequisites';
import { riskTextClass, sizeTextClass, blastTextClass } from './pr/risk';
import {
  CommandWorkspace, WaitingState, PRIdentity, SectionHead, InstrumentAction,
} from './pr/instrument';
import { SkeletonCard, SkeletonGroup } from '../ui/Skeleton';
import { FilePath } from '../ui/FilePath';
import { SectionSeam } from '../ui/SectionSeam';

interface ChangedFile {
  filename: string;
  status: string;
  additions: number;
  deletions: number;
  changes: number;
}

interface SymbolChange {
  name: string;
  type: string;
  file_path: string;
  line_number: number;
  language: string;
  change_type: string;
  parent_class?: string;
}

interface PropagationPath {
  source: string;
  target: string;
  path: string[];
  depth: number;
}

interface RiskBreakdown {
  factor: string;
  score: number;
  detail: string;
}

interface ReviewFocusArea {
  area: string;
  reason: string;
  files: string[];
  priority: 'HIGH' | 'MEDIUM' | 'LOW';
}

interface PRAnalysisResult {
  repo: string;
  pr_number: number;
  pr_url: string;
  pr_title: string;
  pr_state: string;
  pr_size: 'XS' | 'S' | 'M' | 'L' | 'XL';
  risk_score: number;
  risk_level: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  risk_breakdown: RiskBreakdown[];
  top_risks: string[];
  changed_files: ChangedFile[];
  total_additions: number;
  total_deletions: number;
  added_symbols: SymbolChange[];
  modified_symbols: SymbolChange[];
  removed_symbols: SymbolChange[];
  affected_files: string[];
  impact_radius: number;
  blast_radius: 'LOW' | 'MEDIUM' | 'HIGH' | 'EXTREME';
  max_depth: number;
  propagation_paths: PropagationPath[];
  affected_components: string[];
  changed_entry_points: string[];
  changed_core_files: string[];
  changed_high_coupling_files: string[];
  review_focus_areas: ReviewFocusArea[];
  analyzed_at: string;
}

interface PRIntelligenceProps {
  repoName?: string;
}

function resolveRepo(repoName?: string): string {
  if (repoName) return repoName;
  if (typeof window !== 'undefined') {
    const urlParams = new URLSearchParams(window.location.search);
    const owner = urlParams.get('owner');
    const repo = urlParams.get('repo');
    if (owner && repo) return `${owner}/${repo}`;
    const stored = localStorage.getItem('activeRepo');
    if (stored) return stored;
  }
  return '';
}

/** Open PRs read as active work; anything else is quiet metadata. */
function prStateTone(state: string): string {
  const s = (state || '').toLowerCase();
  if (s === 'open') return 'text-success';
  return 'text-text-muted';
}

function fileStatusTone(status: string): string {
  const s = (status || '').toLowerCase();
  if (s === 'added') return 'text-success';
  if (s === 'removed' || s === 'deleted') return 'text-danger';
  return 'text-primary';
}

function priorityTone(priority: string): string {
  const p = (priority || '').toUpperCase();
  if (p === 'HIGH') return 'text-danger';
  if (p === 'MEDIUM') return 'text-warn';
  return 'text-text-muted';
}

function relativeTime(iso: string): string {
  try {
    const diff = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
    if (diff < 1) return 'just now';
    if (diff < 60) return `${diff} min ago`;
    return `${Math.round(diff / 60)}h ago`;
  } catch {
    return iso;
  }
}

/** One of the three architecture detection categories. */
const DetectionRow: React.FC<{
  label: string;
  files: string[];
  tone: string;
  quiet: string;
}> = ({ label, files, tone, quiet }) => {
  const active = files.length > 0;

  return (
    <li className="api-row py-3 border-t border-white/[0.055] last:border-b last:border-white/[0.055] min-w-0">
      <div className="flex items-baseline gap-3 min-w-0">
        <span className="mono-label shrink-0">{label}</span>
        <span className="flex-1 h-px bg-white/[0.05] min-w-[1rem]" aria-hidden="true" />
        <span
          className={`font-mono text-[13px] tabular-nums shrink-0 ${
            active ? tone : 'text-text-subtle'
          }`}
        >
          {files.length}
        </span>
      </div>

      {active ? (
        <ul className="mt-2 space-y-0.5 min-w-0">
          {files.map((f) => (
            <li key={f} className="min-w-0">
              <FilePath path={f} tone="primary" size="sm" />
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-[12px] text-text-subtle leading-relaxed mt-1">{quiet}</p>
      )}
    </li>
  );
};

/** A bounded symbol registry column. */
const SymbolColumn: React.FC<{
  title: string;
  tone: string;
  symbols: SymbolChange[];
  empty: string;
}> = ({ title, tone, symbols, empty }) => (
  <div className="min-w-0">
    <div className="flex items-baseline justify-between gap-3 pb-2.5 hair-b">
      <h4 className={`mono-label ${tone}`}>{title}</h4>
      <span className="font-mono text-[11px] tabular-nums text-text-muted shrink-0">
        {symbols.length}
      </span>
    </div>

    {symbols.length > 0 ? (
      <ul className="mt-1 max-h-[15rem] overflow-y-auto pr-1 -mr-1 min-w-0">
        {symbols.map((sym, idx) => (
          <li
            key={`${sym.name}-${idx}`}
            className="api-row py-2 border-b border-white/[0.04] min-w-0"
          >
            <div className="flex items-baseline justify-between gap-3 min-w-0">
              <span className="font-mono text-[11.5px] text-text break-all min-w-0">
                {sym.name}
              </span>
              <span className="mono-label shrink-0" style={{ fontSize: 9 }}>
                {sym.type}
              </span>
            </div>
            <span className="mono-detail block mt-0.5 truncate" style={{ fontSize: 10 }}>
              {sym.file_path.split('/').pop()}:{sym.line_number}
            </span>
          </li>
        ))}
      </ul>
    ) : (
      <p className="mono-detail mt-3" style={{ fontSize: 10 }}>
        {empty}
      </p>
    )}
  </div>
);

export const PRIntelligence: React.FC<PRIntelligenceProps> = ({ repoName }) => {
  const [activeRepo, setActiveRepo] = useState(() => resolveRepo(repoName));
  const { healthStatus, hasPrerequisites, isRepairing, repair } = usePrerequisites(activeRepo);

  const [useUrl, setUseUrl] = useState(true);
  const [prUrlInput, setPrUrlInput] = useState('');
  const [ownerInput, setOwnerInput] = useState('');
  const [repoInput, setRepoInput] = useState('');
  const [prNumberInput, setPrNumberInput] = useState('');

  const [isLoading, setIsLoading] = useState(false);
  const [analysisResult, setAnalysisResult] = useState<PRAnalysisResult | null>(null);
  const [errorMsg, setErrorMsg] = useState('');

  // Sync activeRepo with repoName prop changes and clear stale results
  useEffect(() => {
    const nextRepo = resolveRepo(repoName);
    setActiveRepo(nextRepo);
    setAnalysisResult(null);
    setErrorMsg('');
    setPrUrlInput('');
    setOwnerInput('');
    setRepoInput('');
    setPrNumberInput('');
  }, [repoName]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setErrorMsg('');
    setAnalysisResult(null);

    const payload: any = {};
    if (useUrl) {
      if (!prUrlInput.trim()) { setErrorMsg('Please enter a GitHub Pull Request URL.'); setIsLoading(false); return; }
      payload.pr_url = prUrlInput.trim();
    } else {
      if (!ownerInput.trim() || !repoInput.trim() || !prNumberInput.trim()) {
        setErrorMsg('Please fill in Owner, Repo, and PR Number.'); setIsLoading(false); return;
      }
      payload.owner = ownerInput.trim();
      payload.repo = repoInput.trim();
      payload.pr_number = parseInt(prNumberInput.trim(), 10);
    }

    try {
      const res = await fetch(apiUrl('/api/v1/pr/analyze'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(extractErrorMessage(errorData));
      }
      const data = await res.json();
      setAnalysisResult(data);
      if (data.repo) setActiveRepo(data.repo);
    } catch (err: any) {
      setErrorMsg(extractErrorMessage(err));
    } finally {
      setIsLoading(false);
    }
  };

  /** The four readings in the metric strip, straight from the payload. */
  const metricStrip = useMemo(() => {
    if (!analysisResult) return [];
    const r = analysisResult;
    return [
      {
        k: 'PR SIZE',
        v: (
          <span className={`font-mono text-[15px] uppercase tracking-[0.12em] ${sizeTextClass(r.pr_size)}`}>
            {r.pr_size}
          </span>
        ),
      },
      {
        k: 'BLAST RADIUS',
        v: (
          <span className={`font-mono text-[15px] uppercase tracking-[0.12em] ${blastTextClass(r.blast_radius)}`}>
            {r.blast_radius}
            <span className="text-text-subtle normal-case tracking-normal">
              {' '}· {r.impact_radius} downstream
            </span>
          </span>
        ),
      },
      {
        k: 'FILES',
        v: (
          <span className="font-mono text-[15px] text-text tabular-nums">
            {r.changed_files.length}
          </span>
        ),
      },
      {
        k: 'DIFF',
        v: (
          <span className="font-mono text-[15px] tabular-nums">
            <span className="text-success">+{r.total_additions}</span>
            <span className="text-text-subtle"> / </span>
            <span className="text-danger">-{r.total_deletions}</span>
          </span>
        ),
      },
    ];
  }, [analysisResult]);

  return (
    <div className="flex flex-col text-text min-w-0">
      {/* ── 01 · Header ───────────────────────────────────────────────────── */}
      <header className="min-w-0">
        <span className="mono-label mono-label-accent block mb-2.5">
          PR INTELLIGENCE / RISK ASSESSMENT
        </span>
        <h2 className="display-3 text-text">Understand what this pull request puts at risk.</h2>
        <p className="text-[13px] text-text-muted leading-relaxed mt-3 max-w-2xl">
          Trace changed files, architectural hotspots, dependency propagation, and review focus
          before merging.
        </p>
        {activeRepo && (
          <p className="mono-label mt-5" style={{ letterSpacing: '0.2em' }}>
            REPOSITORY · {activeRepo}
          </p>
        )}
      </header>

      {/* ── 02 · Command workspace ────────────────────────────────────────── */}
      <div className="mt-9 min-w-0">
        <CommandWorkspace
          input={
            <div className="min-w-0">
              <h3 className="mono-label mono-label-accent pb-3 hair-b">PULL REQUEST</h3>

              <form onSubmit={handleSubmit} className="mt-5 flex flex-col gap-5 min-w-0">
                <PRReferenceForm
                  idPrefix="pri"
                  useUrl={useUrl} setUseUrl={setUseUrl}
                  prUrl={prUrlInput} setPrUrl={setPrUrlInput}
                  owner={ownerInput} setOwner={setOwnerInput}
                  repo={repoInput} setRepo={setRepoInput}
                  prNumber={prNumberInput} setPrNumber={setPrNumberInput}
                />

                {!hasPrerequisites && healthStatus && (
                  <PrerequisitesBanner
                    activeRepo={activeRepo}
                    healthStatus={healthStatus}
                    onRepair={repair}
                    isRepairing={isRepairing}
                  />
                )}

                <div className="min-w-0">
                  <button
                    type="submit"
                    disabled={isLoading || !hasPrerequisites}
                    className="action-chip w-full justify-center disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {isLoading ? (
                      <>
                        <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                        Analyzing pull request
                      </>
                    ) : (
                      <>
                        Analyze Pull Request
                        <ArrowRight className="h-3 w-3" aria-hidden="true" />
                      </>
                    )}
                  </button>
                  {/* Reserves its 1px band either way, so starting a run shifts nothing. */}
                  <div className="mt-2.5" aria-hidden="true">
                    {isLoading ? <div className="activity-line" /> : <div className="h-px" />}
                  </div>
                </div>
              </form>

              {errorMsg && (
                <div role="alert" className="mt-6 flex items-start gap-3">
                  <AlertTriangle
                    className="h-4 w-4 shrink-0 mt-0.5 text-danger"
                    aria-hidden="true"
                  />
                  <div className="min-w-0">
                    <span className="mono-label block mb-1.5" style={{ color: 'var(--danger)' }}>
                      PR ANALYSIS FAILED
                    </span>
                    <p className="text-[12px] text-text-muted leading-relaxed">{errorMsg}</p>
                  </div>
                </div>
              )}
            </div>
          }
          diagnostics={
            <DiagnosticsPanel
              healthStatus={healthStatus}
              description="Ensure the target repository is loaded and indexed via the Overview tab before requesting PR reports."
            />
          }
        />
      </div>

      {/* ── Loading ───────────────────────────────────────────────────────── */}
      {isLoading && (
        <div className="mt-9">
          <SkeletonGroup label="Analyzing pull request">
            <div className="space-y-4">
              <SkeletonCard />
              <SkeletonCard />
            </div>
          </SkeletonGroup>
        </div>
      )}

      {/* ── Compact waiting state ─────────────────────────────────────────── */}
      {!analysisResult && !isLoading && !errorMsg && (
        <div className="mt-9 pt-6 hair-t">
          <WaitingState
            label="WAITING FOR PULL REQUEST"
            pipeline="PR → FILES → SYMBOLS → BLAST RADIUS → REVIEW"
          >
            Paste a GitHub PR URL or provide repository coordinates to begin risk analysis.
          </WaitingState>
        </div>
      )}

      {/* ── Results ───────────────────────────────────────────────────────── */}
      {analysisResult && (
        <div className="min-w-0">
          <SectionSeam label="COMMAND → PULL REQUEST" />

          <PRIdentity
            prNumber={analysisResult.pr_number}
            state={analysisResult.pr_state}
            stateTone={prStateTone(analysisResult.pr_state)}
            subject={
              <h3 className="text-[17px] sm:text-xl text-text font-medium leading-snug max-w-3xl break-words">
                {analysisResult.pr_title}
              </h3>
            }
            metadata={
              <>
                {analysisResult.repo} · ANALYZED{' '}
                {relativeTime(analysisResult.analyzed_at).toUpperCase()}
              </>
            }
            action={
              <InstrumentAction
                href={analysisResult.pr_url}
                ariaLabel={`View pull request ${analysisResult.pr_number} on GitHub`}
              >
                VIEW ON GITHUB
              </InstrumentAction>
            }
          />

          {/* ── 03 · Primary risk readout ─────────────────────────────────── */}
          <SectionSeam label="PULL REQUEST → RISK" />

          <div
            className="grid grid-cols-1 gap-y-8 items-start min-w-0
                       lg:grid-cols-[minmax(0,38fr)_minmax(0,62fr)] lg:gap-x-8"
          >
            <RiskGauge
              score={analysisResult.risk_score}
              label="RISK ASSESSMENT"
              level={`${analysisResult.risk_level} RISK`}
              levelTone={riskTextClass(analysisResult.risk_level)}
            />

            <div className="min-w-0 lg:pl-8 lg:border-l lg:border-white/[0.055]">
              <SectionHead id="pri-signals" title="KEY RISK SIGNALS" />
              {analysisResult.top_risks.length > 0 ? (
                <ul className="min-w-0">
                  {analysisResult.top_risks.map((risk, idx) => (
                    <li
                      key={idx}
                      className="spec-row spec-row--slide group flex items-start gap-3 py-3
                                 border-b border-white/[0.055] hover:border-white/[0.09]
                                 min-w-0 transition-colors duration-200"
                    >
                      <AlertTriangle
                        className="h-3.5 w-3.5 shrink-0 mt-0.5 text-warn"
                        aria-hidden="true"
                      />
                      <span
                        className="text-[13px] text-text leading-relaxed min-w-0
                                   group-hover:text-white transition-colors duration-200"
                      >
                        {risk}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-[13px] text-text-muted leading-relaxed py-4 max-w-lg">
                  No critical risk signals were raised for this change payload.
                </p>
              )}
            </div>
          </div>

          {/* ── 04 · Metric strip ─────────────────────────────────────────── */}
          <dl className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 border-y border-white/[0.055] mt-9 min-w-0">
            {metricStrip.map((cell, idx) => (
              <div
                key={cell.k}
                className={`min-w-0 px-4 sm:px-5 py-3.5
                            ${idx > 0 ? 'border-t border-white/[0.055] sm:border-t-0' : ''}
                            ${idx % 2 === 1 ? 'sm:border-l sm:border-white/[0.055]' : ''}
                            ${idx === 2 ? 'sm:border-t sm:border-white/[0.055] lg:border-t-0 lg:border-l' : ''}
                            ${idx === 3 ? 'lg:border-l lg:border-white/[0.055]' : ''}`}
              >
                <dt className="mono-label mb-1.5">{cell.k}</dt>
                <dd className="min-w-0">{cell.v}</dd>
              </div>
            ))}
          </dl>

          {/* ── 05 · Architecture detections ──────────────────────────────── */}
          <SectionSeam label="RISK → ARCHITECTURE DETECTIONS" />

          <section aria-labelledby="pri-detections" className="min-w-0">
            <SectionHead id="pri-detections" title="CRITICAL ARCHITECTURE DETECTIONS" />
            <ul className="min-w-0">
              <DetectionRow
                label="ENTRY POINTS CHANGED"
                files={analysisResult.changed_entry_points}
                tone="text-danger"
                quiet="No entry point files modified."
              />
              <DetectionRow
                label="CORE FILES CHANGED"
                files={analysisResult.changed_core_files}
                tone="text-warn"
                quiet="No core modules modified."
              />
              <DetectionRow
                label="HIGH-COUPLING CHANGED"
                files={analysisResult.changed_high_coupling_files}
                tone="text-warn"
                quiet="No high-coupling files modified."
              />
            </ul>
          </section>

          {/* ── 06 · Prioritized review focus ─────────────────────────────── */}
          <SectionSeam label="DETECTIONS → REVIEW FOCUS" />

          <section aria-labelledby="pri-focus" className="min-w-0">
            <SectionHead
              id="pri-focus"
              title="PRIORITIZED REVIEW FOCUS"
              accent
              aside={
                <span className="text-[11px] text-text-subtle tabular-nums">
                  {analysisResult.review_focus_areas.length} areas
                </span>
              }
            />

            {analysisResult.review_focus_areas.length > 0 ? (
              <ul className="min-w-0">
                {analysisResult.review_focus_areas.map((area, idx) => (
                  <li
                    key={idx}
                    className="spec-row spec-row--slide group py-4 border-b border-white/[0.055]
                               hover:border-white/[0.09] min-w-0 transition-colors duration-200"
                  >
                    <div
                      className="grid grid-cols-1 gap-x-6 gap-y-3 min-w-0
                                 lg:grid-cols-[minmax(0,62fr)_minmax(0,38fr)]"
                    >
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                          <span
                            className="text-[13px] font-medium text-text leading-snug min-w-0
                                       group-hover:text-white transition-colors duration-200"
                          >
                            {area.area}
                          </span>
                          <span
                            className={`font-mono text-[10px] uppercase tracking-[0.16em] shrink-0 ${priorityTone(
                              area.priority,
                            )}`}
                          >
                            {area.priority}
                          </span>
                        </div>
                        <p className="text-[12px] text-text-muted leading-relaxed mt-1.5 max-w-[70ch]">
                          {area.reason}
                        </p>
                      </div>

                      {area.files.length > 0 && (
                        <div className="min-w-0">
                          <span className="mono-label block mb-1.5" style={{ fontSize: 9 }}>
                            TARGET FILES
                          </span>
                          <ul className="min-w-0 space-y-0.5">
                            {area.files.map((file, fIdx) => (
                              <li key={`${file}-${fIdx}`} className="min-w-0">
                                <FilePath path={file} tone="secondary" size="sm" />
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-[13px] text-text-muted leading-relaxed py-5 max-w-lg">
                No review focus areas triggered — the standard review process is sufficient for
                this PR.
              </p>
            )}
          </section>

          {/* ── 07 · Changed files ────────────────────────────────────────── */}
          <SectionSeam label="REVIEW FOCUS → FILE IMPACT" />

          <section aria-labelledby="pri-files" className="min-w-0">
            <SectionHead
              id="pri-files"
              title={`CHANGED FILES (${analysisResult.changed_files.length})`}
            />

            {/* Column captions from `lg`; below that each row labels its own readings. */}
            <div
              className="hidden lg:grid gap-x-5 pb-2 border-b border-white/[0.055]
                         lg:grid-cols-[minmax(0,56fr)_minmax(0,14fr)_minmax(0,10fr)_minmax(0,10fr)_minmax(0,10fr)]"
              aria-hidden="true"
            >
              <span className="mono-label" style={{ fontSize: 9 }}>FILE PATH</span>
              <span className="mono-label" style={{ fontSize: 9 }}>STATUS</span>
              <span className="mono-label text-right" style={{ fontSize: 9 }}>+</span>
              <span className="mono-label text-right" style={{ fontSize: 9 }}>−</span>
              <span className="mono-label text-right" style={{ fontSize: 9 }}>Δ</span>
            </div>

            <ul className="min-w-0">
              {analysisResult.changed_files.map((file, idx) => (
                <li
                  key={`${file.filename}-${idx}`}
                  className="api-row py-2.5 border-b border-white/[0.055] min-w-0"
                >
                  <div
                    className="grid grid-cols-1 gap-x-5 gap-y-1.5 lg:items-baseline min-w-0
                               lg:grid-cols-[minmax(0,56fr)_minmax(0,14fr)_minmax(0,10fr)_minmax(0,10fr)_minmax(0,10fr)]"
                  >
                    <span className="min-w-0">
                      <FilePath path={file.filename} tone="primary" size="sm" />
                    </span>
                    <span
                      className={`font-mono text-[10px] uppercase tracking-[0.16em] ${fileStatusTone(
                        file.status,
                      )}`}
                    >
                      {file.status}
                    </span>
                    <span className="font-mono text-[11px] text-success tabular-nums lg:text-right">
                      <span className="lg:hidden mono-label mr-2" style={{ fontSize: 9 }}>ADDED</span>
                      +{file.additions}
                    </span>
                    <span className="font-mono text-[11px] text-danger tabular-nums lg:text-right">
                      <span className="lg:hidden mono-label mr-2" style={{ fontSize: 9 }}>REMOVED</span>
                      -{file.deletions}
                    </span>
                    <span className="font-mono text-[11px] text-text tabular-nums lg:text-right">
                      <span className="lg:hidden mono-label mr-2" style={{ fontSize: 9 }}>TOTAL</span>
                      {file.changes}
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          </section>

          {/* ── 08 · Symbol groups ────────────────────────────────────────── */}
          <section aria-labelledby="pri-symbols" className="mt-9 min-w-0">
            <SectionHead id="pri-symbols" title="SYMBOL CHANGES" />
            <div className="grid grid-cols-1 md:grid-cols-3 gap-x-8 gap-y-7 mt-5 min-w-0">
              <SymbolColumn
                title="SYMBOLS ADDED"
                tone="text-success"
                symbols={analysisResult.added_symbols}
                empty="NO ADDED SYMBOLS"
              />
              <SymbolColumn
                title="SYMBOLS MODIFIED"
                tone="mono-label-accent"
                symbols={analysisResult.modified_symbols}
                empty="NO MODIFIED SYMBOLS"
              />
              <SymbolColumn
                title="SYMBOLS REMOVED"
                tone="text-danger"
                symbols={analysisResult.removed_symbols}
                empty="NO REMOVED SYMBOLS"
              />
            </div>
          </section>

          {/* ── 09 · Dependency propagation ───────────────────────────────── */}
          <section aria-labelledby="pri-propagation" className="mt-9 min-w-0">
            <SectionHead
              id="pri-propagation"
              title="DEPENDENCY PROPAGATION"
              aside={
                <span className="text-[11px] text-text-subtle tabular-nums">
                  {analysisResult.propagation_paths.length} paths
                </span>
              }
            />

            {analysisResult.propagation_paths.length > 0 ? (
              <ul className="min-w-0">
                {analysisResult.propagation_paths.map((path, idx) => (
                  <li
                    key={idx}
                    className="topo-item api-row py-3.5 border-b border-white/[0.055] min-w-0"
                  >
                    <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1 mb-2">
                      <span className="mono-label topo-type">
                        PATH #{idx + 1}
                      </span>
                      <span className="mono-detail tabular-nums shrink-0" style={{ fontSize: 10 }}>
                        {path.depth} {path.depth === 1 ? 'HOP' : 'HOPS'}
                      </span>
                    </div>

                    <ol className="min-w-0">
                      {path.path.map((node, nIdx) => (
                        <li key={nIdx} className="min-w-0">
                          <FilePath
                            path={node}
                            tone={nIdx === 0 ? 'primary' : 'secondary'}
                            size="sm"
                          />
                          {nIdx < path.path.length - 1 && (
                            <span
                              className="flex items-center gap-2 my-1 ml-0.5"
                              aria-hidden="true"
                            >
                              <span
                                className="text-[10px] leading-none"
                                style={{ color: 'rgba(94, 106, 210, 0.7)' }}
                              >
                                ↳
                              </span>
                              <span className="topo-edge h-px w-8 shrink-0" />
                            </span>
                          )}
                        </li>
                      ))}
                    </ol>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-[13px] text-text-muted leading-relaxed py-5 max-w-lg">
                No multi-level import cascades found.
              </p>
            )}
          </section>

          {/*
            A neutral run summary, not a completion badge: the dashboard shell
            owns the single authoritative ANALYSIS COMPLETE indicator, so a green
            "READY" here would be a second one competing with it.
          */}
          <footer className="mt-10 pt-5 border-t border-white/[0.055]" aria-label="Risk analysis summary">
            <p className="mono-detail tabular-nums" style={{ fontSize: 10, letterSpacing: '0.16em' }}>
              RISK ANALYSIS ·{' '}
              {analysisResult.review_focus_areas.length}{' '}
              {analysisResult.review_focus_areas.length === 1 ? 'FINDING' : 'FINDINGS'} ·{' '}
              {analysisResult.changed_files.length} CHANGED{' '}
              {analysisResult.changed_files.length === 1 ? 'FILE' : 'FILES'} · ANALYZED{' '}
              {relativeTime(analysisResult.analyzed_at).toUpperCase()}
            </p>
          </footer>
        </div>
      )}
    </div>
  );
};

export default PRIntelligence;

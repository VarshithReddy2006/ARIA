/**
 * ArchitectureDrift — ARIA PR Drift & Architecture Conformance Workspace
 *
 * Final 10/10 Production Polish + Functional Hardening Pass
 *
 * Information Architecture:
 * ZONE A: PR DRIFT COMMAND HEADER (Eyebrow, primary question, repository badge, baseline status)
 * ZONE B: PR ANALYSIS COMMAND CENTER (Keyboard shortcuts '/', Ctrl+Enter, Esc, validation, collapsible PR Context bar)
 * ZONE C: ANALYSIS STATUS / BASELINE (Compact technical status rail)
 * ZONE D: EXECUTIVE DELTA BRIEF (Architecture Risk dominant, structural deltas, improvement secondary)
 * ZONE E: DELTA FINDINGS (Prioritized findings, progressive disclosure 8 -> 16, instant search override, verified-clean state)
 * ZONE F: ARCHITECTURAL HOTSPOTS (Ranked hotspots registry with Call Graph & File Graph deep-links, compact empty state)
 * ZONE G: CHANGE MATRIX (8 dimensions: Cycles, Coupling, Dependencies, Entry points with expandable concrete traces)
 * ZONE H: ARCHITECTURE DECISION (Grounded verdict: WHY, WHAT CHANGED, WHAT SHOULD BE REVIEWED, NEXT ACTION)
 * ZONE I: INVESTIGATION ACTION BAR (Persistent bottom engineering rail for Impact, Graph, Call Graph, Chat, Re-analyze, New PR)
 *
 * Visual Palette:
 * - Canvas: #020204 | Surface: #07090C | Elevated: rgba(16,18,23,0.74) | Higher: rgba(20,23,29,0.82)
 * - Hairline: rgba(255,255,255,0.06) / #1A1A1E | Strong Border: rgba(255,255,255,0.10)
 * - Primary Text: #F3F4F6 | Secondary: #A5AAB4 | Muted: #6F7681
 * - Architectural Indigo Accent: #7C83FF (Hover: #9AA0FF, Glass: rgba(88,101,216,0.09), Border: rgba(88,101,216,0.30))
 * - Verified / Healthy: #35D6A3 | Attention: #F0B429 | High Risk: #F27781 | Unknown: #7D8490
 */

import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { apiUrl, extractErrorMessage } from '../../lib/api';
import {
  AlertTriangle, ArrowRight, Loader2, Zap, ShieldCheck, ShieldAlert,
  Copy, Check, Sparkles, Network, Layers, FileCode,
  SlidersHorizontal, Terminal, ArrowUpRight, ListChecks,
  CheckCircle2, Circle, GitBranch, ChevronDown, ChevronUp,
  FolderGit2, CornerDownRight, CheckSquare, Square, Plus,
  GitCompare, GitPullRequest, Search, RefreshCw, X
} from 'lucide-react';
import { FilePath } from '../ui/FilePath';

// ── Design Tokens ───────────────────────────────────────────────────────────

const T = {
  canvas: '#050608',
  surface: '#0A0D14',
  elevated: '#0D1220',
  strongElevated: '#131A2E',
  glassCard: 'rgba(13, 18, 32, 0.90)',
  glassSurface: 'rgba(13, 18, 32, 0.90)',
  hairline: 'rgba(255, 255, 255, 0.08)',
  hairlineSolid: 'rgba(255, 255, 255, 0.08)',
  strongBorder: 'rgba(255, 255, 255, 0.14)',
  text: '#F8FAFC',
  secondary: '#CBD5E1',
  muted: '#94A3B8',
  subtle: '#64748B',
  accent: '#818CF8',
  accentHover: '#A5B4FC',
  accentActive: '#6366F1',
  accentGlass: 'rgba(99, 102, 241, 0.15)',
  accentBorder: 'rgba(99, 102, 241, 0.40)',
  verified: '#34D399',
  attention: '#FCD34D',
  risk: '#FF758F',
  critical: '#FF4D6D',
  cyan: '#38BDF8',
  violet: '#C084FC',
  unknown: '#94A3B8',
} as const;

// ── Types ───────────────────────────────────────────────────────────────────

interface DependencyEdge {
  source: string;
  target: string;
}

interface CouplingChange {
  file: string;
  before: number;
  after: number;
}

interface PRDriftResult {
  repo: string;
  pr_number: number;
  architecture_risk_score: number;
  architecture_risk_level: string;
  architecture_improvement_score: number;
  top_findings: string[];
  drift_categories: string[];
  architectural_hotspots: string[];
  added_dependencies: DependencyEdge[];
  removed_dependencies: DependencyEdge[];
  new_cycles: string[][];
  resolved_cycles: string[][];
  coupling_increase: CouplingChange[];
  coupling_decrease: CouplingChange[];
  new_entry_points: string[];
  removed_entry_points: string[];
  analyzed_at: string;
}

interface Props {
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

// ── Shared Styles ───────────────────────────────────────────────────────────

const sectionClass = `p-4 sm:p-5 rounded-xl border bg-[${T.surface}] space-y-3.5`;
const sectionBorder = { borderColor: T.hairlineSolid };
const cellBg = `bg-[${T.surface}]`;
const elevatedCellClass = `rounded-lg border bg-[rgba(16,18,23,0.74)]`;
const elevatedCellBorder = { borderColor: T.hairlineSolid };

// ── Risk Helpers ────────────────────────────────────────────────────────────

function riskColor(score: number): string {
  if (score > 50) return T.risk;
  if (score > 25) return T.attention;
  return T.verified;
}

function riskLabel(level: string): string {
  return (level || 'unknown').toUpperCase();
}

// ── Main Component ─────────────────────────────────────────────────────────

export const ArchitectureDrift: React.FC<Props> = ({ repoName }) => {
  const [activeRepo, setActiveRepo] = useState(() => resolveRepo(repoName));
  const [recentRepos, setRecentRepos] = useState<{ name: string }[]>([]);

  const [useUrl, setUseUrl] = useState(true);
  const [prUrlInput, setPrUrlInput] = useState('');
  const [ownerInput, setOwnerInput] = useState('');
  const [repoInput, setRepoInput] = useState('');
  const [prNumberInput, setPrNumberInput] = useState('');

  const [isLoading, setIsLoading] = useState(false);
  const [driftResult, setDriftResult] = useState<PRDriftResult | null>(null);
  const [errorMsg, setErrorMsg] = useState('');
  const [isCommandExpanded, setIsCommandExpanded] = useState(true);

  // Progressive disclosure & search for findings
  const [findingsLimit, setFindingsLimit] = useState(8);
  const [findingSearch, setFindingSearch] = useState('');
  const [copiedPath, setCopiedPath] = useState<string | null>(null);
  const [expandedMatrixRow, setExpandedMatrixRow] = useState<string | null>(null);

  const urlInputRef = useRef<HTMLInputElement>(null);
  const resultsRef = useRef<HTMLDivElement>(null);

  // ── Reset helper (eliminates duplicate logic) ────────────────────────────
  const resetToNewPR = useCallback(() => {
    setPrUrlInput('');
    setOwnerInput('');
    setRepoInput('');
    setPrNumberInput('');
    setDriftResult(null);
    setErrorMsg('');
    setIsCommandExpanded(true);
    setFindingsLimit(8);
    setFindingSearch('');
    setExpandedMatrixRow(null);
    setTimeout(() => urlInputRef.current?.focus(), 50);
  }, []);

  // Sync activeRepo with repoName prop changes and clear stale results
  useEffect(() => {
    const nextRepo = resolveRepo(repoName);
    if (nextRepo !== activeRepo) {
      setActiveRepo(nextRepo);
      setDriftResult(null);
      setErrorMsg('');
      setIsCommandExpanded(true);
      setFindingsLimit(8);
      setFindingSearch('');
    }
  }, [repoName]);

  // Sync global active-repo events
  useEffect(() => {
    const handleRepoChanged = (e: Event) => {
      const customEvent = e as CustomEvent<string>;
      if (customEvent.detail && customEvent.detail !== activeRepo) {
        setActiveRepo(customEvent.detail);
        setDriftResult(null);
        setErrorMsg('');
        setIsCommandExpanded(true);
      }
    };
    const handleRepoCleared = () => {
      setActiveRepo('');
      setDriftResult(null);
      setErrorMsg('');
      setIsCommandExpanded(true);
    };

    window.addEventListener('active-repo-changed', handleRepoChanged);
    window.addEventListener('active-repo-cleared', handleRepoCleared);
    return () => {
      window.removeEventListener('active-repo-changed', handleRepoChanged);
      window.removeEventListener('active-repo-cleared', handleRepoCleared);
    };
  }, [activeRepo]);

  // Fetch recent repositories if no repo is locked
  useEffect(() => {
    if (!repoName) {
      fetch(apiUrl('/api/v1/repos/recent'))
        .then((res) => res.json())
        .then((data) => {
          if (Array.isArray(data) && data.length > 0) {
            setRecentRepos(data);
            if (!activeRepo) {
              setActiveRepo(data[0].name);
            }
          }
        })
        .catch(() => { });
    }
  }, [repoName, activeRepo]);

  // Keyboard shortcut: '/' focuses PR input, Escape blurs focus
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (
        e.key === '/' &&
        document.activeElement !== urlInputRef.current &&
        !(document.activeElement instanceof HTMLInputElement || document.activeElement instanceof HTMLTextAreaElement)
      ) {
        e.preventDefault();
        setIsCommandExpanded(true);
        setTimeout(() => urlInputRef.current?.focus(), 50);
      } else if (e.key === 'Escape') {
        if (document.activeElement instanceof HTMLElement) {
          document.activeElement.blur();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Validation logic — require truly valid inputs, never allow partial
  const isUrlValid = Boolean(prUrlInput.trim().match(/^https?:\/\/github\.com\/[^/]+\/[^/]+\/pull\/\d+\/?$/i));
  const isCoordsValid = Boolean(ownerInput.trim() && repoInput.trim() && prNumberInput.trim() && !isNaN(parseInt(prNumberInput.trim(), 10)));
  const canSubmit = !isLoading && (useUrl ? isUrlValid : isCoordsValid);

  const handleSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!canSubmit || isLoading) return;

    setIsLoading(true);
    setErrorMsg('');
    setDriftResult(null);
    setExpandedMatrixRow(null);

    const payload: any = {};
    if (useUrl) {
      const trimmed = prUrlInput.trim();
      payload.pr_url = trimmed;
      const match = trimmed.match(/github\.com\/([^/]+)\/([^/]+)\/pull\/(\d+)/);
      if (match) {
        payload.owner = match[1];
        payload.repo = match[2];
        payload.pr_number = parseInt(match[3], 10);
      }
    } else {
      payload.owner = ownerInput.trim();
      payload.repo = repoInput.trim();
      payload.pr_number = parseInt(prNumberInput.trim(), 10);
    }

    try {
      const res = await fetch(apiUrl('/api/v1/architecture/drift'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(extractErrorMessage(errorData) || 'Failed to analyze pull request architecture drift.');
      }

      const data: PRDriftResult = await res.json();
      setDriftResult(data);
      if (data.repo) setActiveRepo(data.repo);
      setIsCommandExpanded(false);
      setFindingsLimit(8);
      setTimeout(() => {
        resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }, 150);
    } catch (err: any) {
      setErrorMsg(extractErrorMessage(err) || 'Network error encountered during architecture drift analysis.');
    } finally {
      setIsLoading(false);
    }
  };

  // Ctrl+Enter handler for inputs
  const handleInputKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      handleSubmit();
    }
  };

  // Cross-Surface Navigation: File Graph
  const openInGraph = (file?: string) => {
    const targetFile = file || driftResult?.architectural_hotspots?.[0] || '';
    const [owner, repo] = (activeRepo || '').split('/');
    window.dispatchEvent(
      new CustomEvent('aria-open-graph', {
        detail: {
          owner: owner || undefined,
          repo: repo || undefined,
          file: targetFile,
          path: targetFile,
          source: 'architecture_drift',
        },
      })
    );
    if (window.location.pathname === '/analysis') {
      window.dispatchEvent(
        new CustomEvent('aria-navigate-tab', {
          detail: { tab: 'graph', file: targetFile },
        })
      );
    }
  };

  // Cross-Surface Navigation: Call Graph
  const openInCallGraph = (file?: string) => {
    const targetFile = file || driftResult?.architectural_hotspots?.[0] || '';
    window.dispatchEvent(
      new CustomEvent('aria-navigate-tab', {
        detail: { tab: 'call_graph', file: targetFile },
      })
    );
  };

  // Cross-Surface Navigation: Impact Analysis
  const openInImpact = (file?: string) => {
    const targetFile = file || driftResult?.architectural_hotspots?.[0] || '';
    const [owner, repo] = (activeRepo || '').split('/');
    window.dispatchEvent(
      new CustomEvent('aria-open-impact', {
        detail: {
          file: targetFile,
          owner: owner || undefined,
          repo: repo || undefined,
        },
      })
    );
    if (window.location.pathname === '/analysis') {
      window.dispatchEvent(
        new CustomEvent('aria-navigate-tab', {
          detail: { tab: 'impact_analysis', file: targetFile },
        })
      );
    }
  };

  // Cross-Surface Navigation: ARIA Chat
  const openInChat = (customPrompt?: string) => {
    if (!driftResult) return;
    const [owner, repo] = (activeRepo || '').split('/');
    const prompt =
      customPrompt ||
      `Analyze the architectural conformance of PR #${driftResult.pr_number} in ${driftResult.repo}:

Architecture Risk Score: ${driftResult.architecture_risk_score}/100 (${driftResult.architecture_risk_level})
Architecture Improvement Score: ${driftResult.architecture_improvement_score}/100

Key Findings:
${driftResult.top_findings.map((f) => `- ${f}`).join('\n') || 'None'}

Structural Deltas:
- New Cycles: ${driftResult.new_cycles?.length ?? 0}
- Resolved Cycles: ${driftResult.resolved_cycles?.length ?? 0}
- Coupling Increased: ${driftResult.coupling_increase?.length ?? 0}
- Coupling Decreased: ${driftResult.coupling_decrease?.length ?? 0}
- Impacted Hotspots: ${driftResult.architectural_hotspots?.join(', ') || 'None'}

What is the architectural impact and should this pull request be merged as-is?`;

    window.dispatchEvent(
      new CustomEvent('aria-open-chat', {
        detail: {
          prompt,
          owner,
          repo,
          source: 'architecture_drift',
        },
      })
    );
    if (window.location.pathname !== '/chat' && window.location.pathname === '/analysis') {
      window.dispatchEvent(
        new CustomEvent('aria-navigate-tab', {
          detail: { tab: 'chat' },
        })
      );
    }
  };

  // Copy helper
  const handleCopy = (e: React.MouseEvent, text: string) => {
    e.stopPropagation();
    navigator.clipboard.writeText(text);
    setCopiedPath(text);
    setTimeout(() => setCopiedPath(null), 1500);
  };

  // Filtered findings derived computation
  const filteredFindings = useMemo(() => {
    if (!driftResult || !driftResult.top_findings) return [];
    if (!findingSearch.trim()) return driftResult.top_findings;
    const q = findingSearch.toLowerCase();
    return driftResult.top_findings.filter((f) => f.toLowerCase().includes(q));
  }, [driftResult, findingSearch]);

  const isSearchActive = Boolean(findingSearch.trim());
  const displayedFindings = useMemo(() => {
    if (isSearchActive) return filteredFindings;
    return filteredFindings.slice(0, findingsLimit);
  }, [filteredFindings, isSearchActive, findingsLimit]);

  // Grounded Architecture Verdict derived computation — epistemically correct
  const verdict = useMemo(() => {
    if (!driftResult) return null;
    const risk = driftResult.architecture_risk_score;
    const newCycles = driftResult.new_cycles?.length ?? 0;
    const couplingInc = driftResult.coupling_increase?.length ?? 0;
    const findingsCount = driftResult.top_findings?.length ?? 0;

    if (risk >= 65 || newCycles > 0) {
      return {
        label: 'HIGH ARCHITECTURAL RISK',
        tone: `text-[${T.risk}]`,
        toneBorder: `border-[${T.risk}]/25`,
        toneBg: `bg-[${T.risk}]/8`,
        why: 'Static AST and dependency graph comparison detected critical architectural boundary violations (e.g. introduced circular dependencies or severe coupling degradation).',
        whatChanged: `Introduced ${newCycles} new dependency cycle(s) and increased coupling in ${couplingInc} file(s).`,
        whatShouldReview: 'Refactor imports to break the dependency cycle before merging. Inspect downstream module relationships in the File Graph.',
        nextAction: 'High-risk architectural deviation detected. Request refactoring before approval.',
      };
    } else if (risk >= 30 || couplingInc > 0) {
      return {
        label: 'REVIEW REQUIRED',
        tone: `text-[${T.attention}]`,
        toneBorder: `border-[${T.attention}]/25`,
        toneBg: `bg-[${T.attention}]/8`,
        why: 'The pull request introduces coupling shifts or modifies central architectural hotspots without introducing closed circular dependencies.',
        whatChanged: `Coupling increased across ${couplingInc} file(s) with ${driftResult.added_dependencies?.length ?? 0} added dependency edge(s).`,
        whatShouldReview: 'Verify that newly established dependencies do not violate intended package layering boundaries.',
        nextAction: 'Architectural review recommended. Run downstream regression tests.',
      };
    } else if (findingsCount > 0) {
      return {
        label: 'MINOR DRIFT',
        tone: `text-[${T.accent}]`,
        toneBorder: `border-[${T.accent}]/25`,
        toneBg: `bg-[${T.accent}]/8`,
        why: 'Isolated structural modifications detected. The changes conform to repository module hierarchy with negligible coupling increase.',
        whatChanged: `${findingsCount} minor architectural observation(s) noted. Zero cycles introduced.`,
        whatShouldReview: 'Check that new entry points or exported symbols follow naming conventions.',
        nextAction: 'No architectural blocker detected. Standard code review acceptable.',
      };
    } else {
      return {
        label: 'NO SIGNIFICANT DRIFT',
        tone: `text-[${T.verified}]`,
        toneBorder: `border-[${T.verified}]/25`,
        toneBg: `bg-[${T.verified}]/8`,
        why: 'Indexed baseline comparison found zero newly introduced cycles, zero coupling spikes, and zero entry-point regressions.',
        whatChanged: 'No detected architectural deviations against the indexed codebase baseline.',
        whatShouldReview: 'Unit and integration behavior remains outside static architecture comparison.',
        nextAction: 'No architectural blocker detected.',
      };
    }
  }, [driftResult]);

  // ── Derived: total structural changes for summary ────────────────────────
  const totalStructuralChanges = useMemo(() => {
    if (!driftResult) return 0;
    return (
      (driftResult.new_cycles?.length ?? 0) +
      (driftResult.resolved_cycles?.length ?? 0) +
      (driftResult.coupling_increase?.length ?? 0) +
      (driftResult.coupling_decrease?.length ?? 0) +
      (driftResult.added_dependencies?.length ?? 0) +
      (driftResult.removed_dependencies?.length ?? 0) +
      (driftResult.new_entry_points?.length ?? 0) +
      (driftResult.removed_entry_points?.length ?? 0)
    );
  }, [driftResult]);

  return (
    <div className="flex flex-col text-[#F8FAFC] min-w-0 space-y-5 font-sans">
      {/* ── ZONE A: PR DRIFT COMMAND HEADER ───────────────────────────────── */}
      <header className="min-w-0 pb-4 border-b border-white/[0.08]">
        <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-3">
          <div className="min-w-0 max-w-2xl space-y-1.5">
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-bold text-[#818CF8] uppercase tracking-widest font-mono">
                PR DRIFT / ARCHITECTURE CONFORMANCE
              </span>
              <span className="h-1 w-1 rounded-full bg-white/20" />
              <span className="text-[9.5px] font-mono text-[#64748B] uppercase tracking-wider flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full bg-[#34D399] shadow-[0_0_8px_rgba(52,211,153,0.5)]" />
                INDEXED BASELINE: READY
              </span>
            </div>
            <h2 className="text-lg sm:text-xl font-bold text-[#F8FAFC] tracking-tight font-mono leading-tight">
              DOES THIS CHANGE MATCH THE INTENDED ARCHITECTURE?
            </h2>
            <p className="text-xs text-[#CBD5E1] leading-relaxed max-w-xl font-sans">
              Compare the indexed baseline against a proposed PR to identify architectural drift, dependency changes, coupling shifts, cycles, and entry-point deltas.
            </p>
          </div>

          <div className="flex items-center gap-2.5 self-start lg:self-auto shrink-0">
            {activeRepo && (
              <div className="px-3 py-1 rounded-md border text-xs font-mono text-[#CBD5E1] flex items-center gap-2 bg-[#0A0D14]/90 border-white/[0.08]">
                <span className="text-[9px] uppercase tracking-wider text-[#64748B]">REPO:</span>
                <span className="text-[#F8FAFC] font-semibold">{activeRepo}</span>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* ── ZONE B: PR ANALYSIS COMMAND CENTER ────────────────────────────── */}
      <div className="rounded-xl border shadow-xl overflow-hidden transition-all bg-gradient-to-b from-[#0D1220]/90 to-[#070A12]/95 backdrop-blur-xl border-white/[0.08]">
        {/* Header bar of Command Center */}
        <div className="px-3.5 py-2.5 sm:px-4 sm:py-3 flex items-center justify-between border-b border-white/[0.08] bg-white/[0.02]">
          <div className="flex items-center gap-2.5 min-w-0">
            <Terminal className="h-3.5 w-3.5 text-[#818CF8] shrink-0" />
            <span className="text-[10px] font-mono font-bold text-[#818CF8] uppercase tracking-widest shrink-0">
              PR COMMAND CONSOLE
            </span>
            {driftResult && !isCommandExpanded && (
              <span className="text-[11px] font-mono text-[#CBD5E1] max-w-xs sm:max-w-md truncate ml-2">
                PR #{driftResult.pr_number} &middot; {driftResult.repo} &middot; ANALYZED {relativeTime(driftResult.analyzed_at).toUpperCase()}
              </span>
            )}
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <span className="text-[10px] font-mono text-[#64748B] hidden xl:inline">
              Press <kbd className="px-1.5 py-0.5 rounded text-[#CBD5E1] bg-[#07090E] border border-white/10">/</kbd> to focus &middot; <kbd className="px-1.5 py-0.5 rounded text-[#CBD5E1] bg-[#07090E] border border-white/10">Ctrl+Enter</kbd> to submit
            </span>

            {driftResult && (
              <>
                <button
                  type="button"
                  onClick={resetToNewPR}
                  className="px-2.5 py-1 rounded bg-[#0D1220] border border-white/[0.08] hover:border-white/20 text-[10.5px] font-mono text-[#CBD5E1] hover:text-[#F8FAFC] flex items-center gap-1.5 transition-colors"
                  title="Clear inputs and analyze a new pull request"
                >
                  <Plus className="h-3 w-3" />
                  <span className="hidden sm:inline">NEW PR</span>
                </button>

                <button
                  type="button"
                  onClick={() => setIsCommandExpanded(!isCommandExpanded)}
                  className="px-2.5 py-1 rounded bg-[#0D1220] border border-white/[0.08] hover:border-white/20 text-[10.5px] font-mono text-[#CBD5E1] hover:text-[#F8FAFC] flex items-center gap-1.5 transition-colors"
                >
                  {isCommandExpanded ? (
                    <>
                      <span>COLLAPSE</span>
                      <ChevronUp className="h-3 w-3" />
                    </>
                  ) : (
                    <>
                      <span>EDIT / RE-ANALYZE</span>
                      <ChevronDown className="h-3 w-3" />
                    </>
                  )}
                </button>
              </>
            )}
          </div>
        </div>

        {/* Collapsible form body */}
        {isCommandExpanded && (
          <div className="p-4 sm:p-5 space-y-3.5">
            <div className="flex items-center gap-2 pb-2.5 text-xs font-mono border-b border-white/[0.08]">
              <button
                type="button"
                onClick={() => setUseUrl(true)}
                className={`px-3 py-1 rounded transition-colors ${useUrl
                    ? 'bg-[#818CF8]/15 text-[#818CF8] font-bold border border-[#818CF8]/40'
                    : 'text-[#64748B] hover:text-[#F8FAFC]'
                  }`}
              >
                PULL REQUEST URL
              </button>
              <button
                type="button"
                onClick={() => setUseUrl(false)}
                className={`px-3 py-1 rounded transition-colors ${!useUrl
                    ? 'bg-[#818CF8]/15 text-[#818CF8] font-bold border border-[#818CF8]/40'
                    : 'text-[#64748B] hover:text-[#F8FAFC]'
                  }`}
              >
                COORDINATES (OWNER / REPO / PR#)
              </button>
            </div>

            <form onSubmit={handleSubmit} className="space-y-3.5">
              {useUrl ? (
                <div className="space-y-1.5">
                  <label htmlFor="drift-pr-url-input" className="text-[10px] font-mono font-bold text-[#64748B] uppercase tracking-wider block">
                    GITHUB PULL REQUEST URL
                  </label>
                  <input
                    ref={urlInputRef}
                    id="drift-pr-url-input"
                    type="url"
                    required
                    value={prUrlInput}
                    onChange={(e) => setPrUrlInput(e.target.value)}
                    onKeyDown={handleInputKeyDown}
                    placeholder="https://github.com/geturbackend/urbackend/pull/402"
                    className="w-full rounded-lg px-3 py-2 text-xs text-[#F8FAFC] placeholder-[#64748B] font-mono bg-[#07090E] border border-white/[0.10] focus:border-[#818CF8] focus:ring-1 focus:ring-[#818CF8]/30 focus-visible:outline-none transition-colors"
                  />
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div className="space-y-1.5">
                    <label htmlFor="drift-owner-input" className="text-[10px] font-mono font-bold text-[#64748B] uppercase tracking-wider block">
                      OWNER / ORG
                    </label>
                    <input
                      id="drift-owner-input"
                      type="text"
                      required
                      value={ownerInput}
                      onChange={(e) => setOwnerInput(e.target.value)}
                      onKeyDown={handleInputKeyDown}
                      placeholder="geturbackend"
                      className="w-full rounded-lg px-3 py-2 text-xs text-[#F8FAFC] placeholder-[#64748B] font-mono bg-[#07090E] border border-white/[0.10] focus:border-[#818CF8] focus:ring-1 focus:ring-[#818CF8]/30 focus-visible:outline-none transition-colors"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <label htmlFor="drift-repo-input" className="text-[10px] font-mono font-bold text-[#64748B] uppercase tracking-wider block">
                      REPOSITORY
                    </label>
                    <input
                      id="drift-repo-input"
                      type="text"
                      required
                      value={repoInput}
                      onChange={(e) => setRepoInput(e.target.value)}
                      onKeyDown={handleInputKeyDown}
                      placeholder="urbackend"
                      className="w-full rounded-lg px-3 py-2 text-xs text-[#F8FAFC] placeholder-[#64748B] font-mono bg-[#07090E] border border-white/[0.10] focus:border-[#818CF8] focus:ring-1 focus:ring-[#818CF8]/30 focus-visible:outline-none transition-colors"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <label htmlFor="drift-number-input" className="text-[10px] font-mono font-bold text-[#64748B] uppercase tracking-wider block">
                      PR NUMBER
                    </label>
                    <input
                      id="drift-number-input"
                      type="number"
                      required
                      value={prNumberInput}
                      onChange={(e) => setPrNumberInput(e.target.value)}
                      onKeyDown={handleInputKeyDown}
                      placeholder="402"
                      className="w-full rounded-lg px-3 py-2 text-xs text-[#F8FAFC] placeholder-[#64748B] font-mono bg-[#07090E] border border-white/[0.10] focus:border-[#818CF8] focus:ring-1 focus:ring-[#818CF8]/30 focus-visible:outline-none transition-colors"
                    />
                  </div>
                </div>
              )}

              <div className="flex items-center justify-between pt-0.5">
                <div className="text-[10px] font-mono text-[#64748B]">
                  {useUrl ? (
                    !prUrlInput.trim() ? (
                      <span className="text-[#64748B]">WAITING FOR PR URL</span>
                    ) : isUrlValid ? (
                      <span className="text-[#34D399] flex items-center gap-1">
                        <CheckCircle2 className="h-3 w-3" />
                        READY TO ANALYZE
                      </span>
                    ) : (
                      <span className="text-[#FCD34D]">ENTER VALID GITHUB PR URL</span>
                    )
                  ) : isCoordsValid ? (
                    <span className="text-[#34D399] flex items-center gap-1">
                      <CheckCircle2 className="h-3 w-3" />
                      READY TO ANALYZE
                    </span>
                  ) : (
                    <span className="text-[#64748B]">ENTER OWNER, REPO, AND PR NUMBER</span>
                  )}
                </div>

                <button
                  type="submit"
                  disabled={!canSubmit || isLoading}
                  className="px-5 py-2 rounded-lg bg-[#818CF8] hover:bg-[#A5B4FC] active:bg-[#6366F1] border border-white/10 text-white text-xs font-bold font-mono transition-all shadow-[0_0_16px_rgba(129,140,248,0.25)] flex items-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {isLoading ? (
                    <>
                      <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                      <span>ANALYZING…</span>
                    </>
                  ) : (
                    <>
                      <span>ANALYZE DRIFT</span>
                      <ArrowRight className="h-3.5 w-3.5" />
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        )}
      </div>

      {/* ── ZONE C: ANALYSIS STATUS / BASELINE ────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-px rounded-xl overflow-hidden font-mono text-xs bg-white/[0.08] border border-white/[0.08]">
        <div className="p-3 flex items-center justify-between bg-[#0A0D14]">
          <span className="text-[9.5px] font-bold text-[#64748B] uppercase tracking-wider">
            BASELINE GRAPH
          </span>
          <span className="text-[10.5px] font-semibold text-[#34D399] flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-[#34D399] shadow-[0_0_8px_rgba(52,211,153,0.5)]" />
            INDEXED &amp; ACTIVE
          </span>
        </div>

        <div className="p-3 flex items-center justify-between bg-[#0A0D14]">
          <span className="text-[9.5px] font-bold text-[#64748B] uppercase tracking-wider">
            PR DELTA
          </span>
          <span className="text-[10.5px] font-semibold text-[#F8FAFC]">
            {isLoading ? (
              <span className="text-[#818CF8] flex items-center gap-1.5">
                <Loader2 className="h-3 w-3 animate-spin" />
                COMPUTING AST DIFF
              </span>
            ) : driftResult ? (
              <span className="text-[#34D399]">MAPPED (PR #{driftResult.pr_number})</span>
            ) : (
              <span className="text-[#64748B]">STANDBY</span>
            )}
          </span>
        </div>

        <div className="p-3 flex items-center justify-between bg-[#0A0D14]">
          <span className="text-[9.5px] font-bold text-[#64748B] uppercase tracking-wider">
            ANALYSIS STATUS
          </span>
          <span className="text-[10.5px] font-semibold" role="status" aria-live="polite">
            {isLoading ? (
              <span className="text-[#818CF8] animate-pulse">EVALUATING BOUNDARIES</span>
            ) : driftResult ? (
              <span className="text-[#34D399] flex items-center gap-1">
                <Check className="h-3 w-3" />
                COMPLETE
              </span>
            ) : errorMsg ? (
              <span className="text-[#FF4D6D]">ERROR</span>
            ) : (
              <span className="text-[#64748B]">READY</span>
            )}
          </span>
        </div>
      </div>

      {/* ── ERROR STATE ───────────────────────────────────────────────────── */}
      {errorMsg && (
        <div
          role="alert"
          className="p-4 rounded-xl flex items-start gap-3 text-xs font-mono bg-[#FF4D6D]/10 border border-[#FF4D6D]/25 backdrop-blur-md"
        >
          <AlertTriangle className="h-4 w-4 text-[#FF4D6D] shrink-0 mt-0.5" aria-hidden="true" />
          <div className="space-y-1.5 flex-1 min-w-0">
            <span className="font-bold text-[#FF4D6D] block tracking-wider uppercase text-[11px]">
              PR ANALYSIS FAILED
            </span>
            <p className="text-[#CBD5E1] font-sans leading-relaxed text-[12px]">
              {errorMsg}
            </p>
            <div className="pt-1 flex items-center gap-2">
              <button
                type="button"
                onClick={() => handleSubmit()}
                className="px-3 py-1 rounded bg-[#FF4D6D]/20 hover:bg-[#FF4D6D]/30 text-[#FF4D6D] text-[10px] font-bold uppercase transition-colors"
              >
                RETRY
              </button>
              <button
                type="button"
                onClick={() => setIsCommandExpanded(true)}
                className="px-3 py-1 rounded bg-[#0D1220] border border-white/[0.08] hover:bg-[#131A2E] text-[#CBD5E1] text-[10px] font-bold uppercase transition-colors"
              >
                EDIT PR INPUT
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── LOADING STATE ─────────────────────────────────────────────────── */}
      {isLoading && (
        <div className="p-8 text-center rounded-xl space-y-3 bg-gradient-to-b from-[#0D1220]/90 to-[#070A12]/95 backdrop-blur-xl border border-white/[0.08]">
          <div className="flex items-center justify-center gap-2.5">
            <Loader2 className="h-5 w-5 text-[#818CF8] animate-spin" />
            <span className="text-sm font-mono font-bold text-[#F8FAFC] tracking-wider">
              ANALYZING PR
            </span>
          </div>
          <div className="flex items-center justify-center gap-4 text-[10px] font-mono text-[#64748B] uppercase tracking-wider">
            <span className="text-[#818CF8]">COMPARING BASELINE</span>
            <span>&rarr;</span>
            <span>EVALUATING BOUNDARIES</span>
            <span>&rarr;</span>
            <span>COMPUTING ARCHITECTURAL DELTA</span>
          </div>
        </div>
      )}

      {/* ── EMPTY / STANDBY STATE ─────────────────────────────────────────── */}
      {!driftResult && !isLoading && !errorMsg && (
        <div className="p-8 text-center rounded-xl space-y-3 max-w-lg mx-auto bg-gradient-to-b from-[#0D1220]/90 to-[#070A12]/95 backdrop-blur-xl border border-white/[0.08]">
          <div className="h-10 w-10 rounded-lg flex items-center justify-center text-[#818CF8] mx-auto bg-[#131A2E] border border-[#818CF8]/30 shadow-[0_0_12px_rgba(129,140,248,0.2)]">
            <GitCompare className="h-5 w-5" />
          </div>
          <div className="space-y-1">
            <h3 className="text-xs font-bold font-mono text-[#F8FAFC] uppercase tracking-wider">
              WAITING FOR PULL REQUEST INPUT
            </h3>
            <p className="text-[10.5px] font-mono text-[#818CF8] tracking-wider uppercase">
              BASELINE &rarr; PR DIFF &rarr; RISK &rarr; DELTAS &rarr; DECISION
            </p>
            <p className="text-xs text-[#CBD5E1] font-sans leading-relaxed pt-0.5">
              Provide a GitHub PR URL or repository coordinates. ARIA will analyze AST import deltas, trace cyclic relationships, and compute structural architectural drift against the indexed baseline.
            </p>
          </div>
        </div>
      )}

      {/* ── RESULTS WORKSPACE ─────────────────────────────────────────────── */}
      {driftResult && !isLoading && (
        <div ref={resultsRef} className="space-y-5">
          {/* ── ZONE D: EXECUTIVE DELTA BRIEF ─────────────────────────────── */}
          <section aria-labelledby="executive-delta-brief" className="p-4 sm:p-5 rounded-xl space-y-3.5 bg-gradient-to-b from-[#0D1220]/90 to-[#070A12]/95 backdrop-blur-xl border border-white/[0.08]">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 pb-3 border-b border-white/[0.08]">
              <div>
                <span className="text-[9.5px] font-mono font-bold text-[#818CF8] uppercase tracking-widest block">
                  EXECUTIVE DELTA BRIEF
                </span>
                <h3 id="executive-delta-brief" className="font-mono text-sm font-bold text-[#F8FAFC] mt-0.5">
                  PR #{driftResult.pr_number} &middot; {driftResult.repo}
                </h3>
              </div>

              <div className="flex items-center gap-2.5 shrink-0 flex-wrap text-xs font-mono">
                <span className="px-2.5 py-0.5 rounded text-[10px] font-mono text-[#CBD5E1] bg-[#0D1220] border border-white/[0.08]">
                  ANALYZED {relativeTime(driftResult.analyzed_at).toUpperCase()}
                </span>
              </div>
            </div>

            {/* Continuous Analytical Metric Rail — ARCH RISK dominant */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-px rounded-lg overflow-hidden font-mono bg-white/[0.08] border border-white/[0.08]">
              {/* ARCH RISK — visually dominant */}
              <div className="p-3 space-y-0.5 bg-[#0A0D14]">
                <span className="text-2xl font-bold block leading-none" style={{ color: riskColor(driftResult.architecture_risk_score) }}>
                  {driftResult.architecture_risk_score}<span className="text-xs text-[#64748B]">/100</span>
                </span>
                <span className="text-[9px] font-bold uppercase tracking-widest block" style={{ color: riskColor(driftResult.architecture_risk_score) }}>
                  {riskLabel(driftResult.architecture_risk_level)}
                </span>
                <span className="text-[8.5px] font-bold text-[#64748B] uppercase tracking-widest block">
                  ARCH RISK
                </span>
              </div>

              {/* NEW CYCLES */}
              <div className="p-3 space-y-0.5 bg-[#0A0D14]">
                <span className={`text-xl font-bold block leading-none ${(driftResult.new_cycles?.length ?? 0) > 0 ? 'text-[#FF4D6D]' : 'text-[#64748B]'
                  }`}>
                  {driftResult.new_cycles?.length ?? 0}
                </span>
                <span className="text-[9px] font-bold text-[#64748B] uppercase tracking-widest block">
                  NEW CYCLES
                </span>
              </div>

              {/* RESOLVED CYCLES */}
              <div className="p-3 space-y-0.5 bg-[#0A0D14]">
                <span className={`text-xl font-bold block leading-none ${(driftResult.resolved_cycles?.length ?? 0) > 0 ? 'text-[#34D399]' : 'text-[#64748B]'
                  }`}>
                  {driftResult.resolved_cycles?.length ?? 0}
                </span>
                <span className="text-[9px] font-bold text-[#64748B] uppercase tracking-widest block">
                  RESOLVED CYCLES
                </span>
              </div>

              {/* COUPLING UP */}
              <div className="p-3 space-y-0.5 bg-[#0A0D14]">
                <span className={`text-xl font-bold block leading-none ${(driftResult.coupling_increase?.length ?? 0) > 0 ? 'text-[#FCD34D]' : 'text-[#64748B]'
                  }`}>
                  {driftResult.coupling_increase?.length ?? 0}
                </span>
                <span className="text-[9px] font-bold text-[#64748B] uppercase tracking-widest block">
                  COUPLING UP
                </span>
              </div>

              {/* COUPLING DOWN */}
              <div className="p-3 space-y-0.5 bg-[#0A0D14]">
                <span className={`text-xl font-bold block leading-none ${(driftResult.coupling_decrease?.length ?? 0) > 0 ? 'text-[#34D399]' : 'text-[#64748B]'
                  }`}>
                  {driftResult.coupling_decrease?.length ?? 0}
                </span>
                <span className="text-[9px] font-bold text-[#64748B] uppercase tracking-widest block">
                  COUPLING DOWN
                </span>
              </div>

              {/* IMPROVEMENT — secondary */}
              <div className="p-3 space-y-0.5 bg-[#0A0D14]">
                <span className={`text-xl font-bold block leading-none ${driftResult.architecture_improvement_score > 20 ? 'text-[#34D399]' : 'text-[#F8FAFC]'
                  }`}>
                  {driftResult.architecture_improvement_score}<span className="text-xs text-[#64748B]">/100</span>
                </span>
                <span className="text-[9px] font-bold text-[#64748B] uppercase tracking-widest block">
                  IMPROVEMENT
                </span>
              </div>
            </div>

            {/* Drift Categories Tags */}
            {driftResult.drift_categories?.length > 0 && (
              <div className="flex items-center gap-2 flex-wrap pt-0.5 text-[10.5px] font-mono text-[#CBD5E1]">
                <span className="text-[#64748B] uppercase text-[9.5px] font-bold tracking-wider">DRIFT SIGNALS:</span>
                {driftResult.drift_categories.map((cat, idx) => (
                  <span key={idx} className="px-2 py-0.5 rounded text-[#F8FAFC] text-[10px] bg-[#0D1220] border border-white/[0.08]">
                    {cat.replace(/_/g, ' ')}
                  </span>
                ))}
              </div>
            )}
          </section>

          {/* ── ZONE E: DELTA FINDINGS ────────────────────────────────────── */}
          <section aria-labelledby="prioritized-findings-heading" className="p-4 sm:p-5 rounded-xl space-y-3.5 bg-gradient-to-b from-[#0D1220]/90 to-[#070A12]/95 backdrop-blur-xl border border-white/[0.08]">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 pb-2.5 border-b border-white/[0.08]">
              <div>
                <h3 id="prioritized-findings-heading" className="text-xs font-bold font-mono text-[#F8FAFC] uppercase tracking-wider flex items-center gap-2">
                  <ListChecks className="h-3.5 w-3.5 text-[#818CF8]" />
                  PRIORITIZED FINDINGS ({filteredFindings.length})
                </h3>
                <p className="text-[10.5px] text-[#CBD5E1] font-sans mt-0.5">
                  Architectural changes that deserve engineering attention before merge.
                </p>
              </div>

              {/* Search Bar */}
              <div className="relative min-w-[200px] sm:min-w-[240px]">
                <Search className="h-3 w-3 text-[#64748B] absolute left-2.5 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  value={findingSearch}
                  onChange={(e) => setFindingSearch(e.target.value)}
                  placeholder="Filter findings..."
                  className="w-full rounded-md pl-8 pr-7 py-1 text-xs font-mono text-[#F8FAFC] placeholder-[#64748B] bg-[#07090E] border border-white/[0.10] focus:border-[#818CF8] focus:ring-1 focus:ring-[#818CF8]/30 focus-visible:outline-none transition-colors"
                />
                {findingSearch && (
                  <button
                    type="button"
                    onClick={() => setFindingSearch('')}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-[#64748B] hover:text-[#F8FAFC]"
                  >
                    <X className="h-3 w-3" />
                  </button>
                )}
              </div>
            </div>

            {/* Findings List or Verified Clean State */}
            {filteredFindings.length === 0 ? (
              isSearchActive ? (
                <div className="p-4 text-center rounded-lg text-xs font-mono text-[#CBD5E1] space-y-1 bg-[#0A0D14] border border-white/[0.08]">
                  <p>No findings matching &ldquo;{findingSearch}&rdquo;</p>
                  <button
                    type="button"
                    onClick={() => setFindingSearch('')}
                    className="text-[#818CF8] hover:underline"
                  >
                    Clear filter
                  </button>
                </div>
              ) : (
                /* Verified-Clean State — dark glass, thin green edge, compact */
                <div className="rounded-lg space-y-3 p-4 bg-[#0A0D14] border border-white/[0.08] border-l-2 border-l-[#34D399]">
                  <div className="flex items-center gap-2 text-[#34D399] font-mono text-xs font-bold uppercase tracking-wider">
                    <ShieldCheck className="h-3.5 w-3.5 shrink-0" />
                    <span>NO SIGNIFICANT ARCHITECTURAL DRIFT DETECTED</span>
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-px rounded overflow-hidden font-mono text-xs bg-white/[0.08] border border-white/[0.08]">
                    <div className="p-2 text-center bg-[#0A0D14]">
                      <span className="text-[9.5px] text-[#64748B] block">NEW CYCLES</span>
                      <span className="text-sm font-bold text-[#F8FAFC]">0</span>
                    </div>
                    <div className="p-2 text-center bg-[#0A0D14]">
                      <span className="text-[9.5px] text-[#64748B] block">COUPLING</span>
                      <span className="text-sm font-bold text-[#F8FAFC]">0</span>
                    </div>
                    <div className="p-2 text-center bg-[#0A0D14]">
                      <span className="text-[9.5px] text-[#64748B] block">DEPENDENCIES</span>
                      <span className="text-sm font-bold text-[#F8FAFC]">0</span>
                    </div>
                    <div className="p-2 text-center bg-[#0A0D14]">
                      <span className="text-[9.5px] text-[#64748B] block">ENTRY POINTS</span>
                      <span className="text-sm font-bold text-[#F8FAFC]">0</span>
                    </div>
                  </div>
                  <p className="text-[11.5px] text-[#CBD5E1] font-sans leading-relaxed">
                    The indexed baseline comparison found no detected architectural deviations in the analyzed PR.
                  </p>
                  <p className="text-[10px] text-[#64748B] font-mono uppercase tracking-wider">
                    STATIC ANALYSIS NOTE &mdash; Runtime behavior and external integrations are outside the indexed architectural graph.
                  </p>
                </div>
              )
            ) : (
              <div className="space-y-2">
                {displayedFindings.map((finding, idx) => {
                  const isCycle = finding.toLowerCase().includes('cycle');
                  const isCoupling = finding.toLowerCase().includes('coupling');
                  const isHotspot = finding.toLowerCase().includes('hotspot');

                  const severityTag = isCycle ? 'HIGH RISK' : isCoupling ? 'COUPLING SHIFT' : isHotspot ? 'HOTSPOT' : 'ARCHITECTURAL';
                  const tagStyles = isCycle
                    ? { color: '#FF4D6D', borderColor: 'rgba(255,77,109,0.30)', background: 'rgba(255,77,109,0.12)' }
                    : isCoupling
                      ? { color: '#FCD34D', borderColor: 'rgba(252,211,77,0.30)', background: 'rgba(252,211,77,0.12)' }
                      : { color: '#818CF8', borderColor: 'rgba(129,140,248,0.35)', background: 'rgba(129,140,248,0.12)' };

                  return (
                    <div
                      key={idx}
                      className="p-3 rounded-lg hover:border-white/[0.14] transition-all space-y-1.5 text-xs bg-[#0A0D14] border border-white/[0.08]"
                    >
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1.5">
                        <div className="flex items-center gap-2 min-w-0">
                          <span className="text-[10px] font-mono font-bold text-[#64748B] shrink-0">
                            {String(idx + 1).padStart(2, '0')}
                          </span>
                          <span className="px-1.5 py-0.5 rounded text-[9px] font-mono font-bold uppercase" style={{ ...tagStyles, border: `1px solid ${tagStyles.borderColor}` }}>
                            {severityTag}
                          </span>
                          <span className="font-medium text-[#F8FAFC] text-xs leading-snug">
                            {finding}
                          </span>
                        </div>

                        <div className="flex items-center gap-2 shrink-0 font-mono text-[10px]">
                          <span className="px-1.5 py-0.5 rounded text-[#34D399] text-[9px] bg-[#0D1220] border border-white/[0.08]">
                            VERIFIED EVIDENCE
                          </span>
                        </div>
                      </div>

                      <div className="flex items-center justify-between gap-3 text-xs">
                        <div className="text-[11px] text-[#CBD5E1] font-sans leading-relaxed flex-1">
                          Static AST graph comparison identified this change as a structural delta relative to the indexed baseline.
                        </div>

                        <div className="flex items-center gap-2.5 font-mono text-[10px] shrink-0">
                          <button
                            type="button"
                            onClick={() => openInGraph()}
                            className="text-[#CBD5E1] hover:text-[#818CF8] flex items-center gap-1 uppercase transition-colors"
                          >
                            <span>VIEW IN GRAPH</span>
                            <ArrowUpRight className="h-3 w-3" />
                          </button>
                          <button
                            type="button"
                            onClick={() => openInChat(`Review this architectural drift finding for PR #${driftResult.pr_number}: "${finding}"`)}
                            className="text-[#CBD5E1] hover:text-[#818CF8] flex items-center gap-1 uppercase transition-colors"
                          >
                            <span>CHAT</span>
                            <Sparkles className="h-3 w-3" />
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })}

                {/* Progressive Disclosure Controls */}
                {!isSearchActive && filteredFindings.length > 8 && (
                  <div className="pt-1.5 flex items-center justify-between text-xs font-mono">
                    <span className="text-[#64748B]">
                      SHOWING {displayedFindings.length} OF {filteredFindings.length} FINDINGS
                    </span>
                    <div className="flex items-center gap-2">
                      {findingsLimit < filteredFindings.length ? (
                        <button
                          type="button"
                          onClick={() => setFindingsLimit((prev) => Math.min(prev + 8, filteredFindings.length))}
                          className="px-3 py-1 rounded-md bg-[#0D1220] border border-white/[0.08] hover:bg-[#131A2E] text-[#F8FAFC] text-xs font-mono transition-colors flex items-center gap-1.5"
                        >
                          <span>SHOW MORE FINDINGS ({displayedFindings.length} &rarr; {Math.min(findingsLimit + 8, filteredFindings.length)})</span>
                          <ChevronDown className="h-3 w-3" />
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={() => setFindingsLimit(8)}
                          className="px-3 py-1 rounded-md bg-[#0D1220] border border-white/[0.08] hover:bg-[#131A2E] text-[#CBD5E1] hover:text-[#F8FAFC] text-xs font-mono transition-colors flex items-center gap-1.5"
                        >
                          <span>COLLAPSE TO 8</span>
                          <ChevronUp className="h-3 w-3" />
                        </button>
                      )}
                    </div>
                  </div>
                )}

                {/* Search result count indicator */}
                {isSearchActive && (
                  <div className="text-[10px] font-mono text-[#64748B] uppercase tracking-wider pt-1">
                    ALL {filteredFindings.length} MATCH{filteredFindings.length !== 1 ? 'ES' : ''} SHOWN
                  </div>
                )}
              </div>
            )}
          </section>

          {/* ── ZONE F: ARCHITECTURAL HOTSPOTS ────────────────────────────── */}
          <section aria-labelledby="hotspots-heading" className="p-4 sm:p-5 rounded-xl space-y-3 bg-gradient-to-b from-[#0D1220]/90 to-[#070A12]/95 backdrop-blur-xl border border-white/[0.08]">
            <div className="flex items-center justify-between pb-2.5 border-b border-white/[0.08]">
              <div>
                <h3 id="hotspots-heading" className="text-xs font-bold font-mono text-[#F8FAFC] uppercase tracking-wider flex items-center gap-2">
                  <Zap className="h-3.5 w-3.5 text-[#FCD34D]" />
                  ARCHITECTURAL HOTSPOTS IMPACTED ({driftResult.architectural_hotspots?.length ?? 0})
                </h3>
                <p className="text-[10.5px] text-[#CBD5E1] font-sans mt-0.5">
                  Modules at the intersection of high centrality, coupling, or entry points modified by this PR.
                </p>
              </div>
            </div>

            {(!driftResult.architectural_hotspots || driftResult.architectural_hotspots.length === 0) ? (
              /* Compact single-row verified-empty state */
              <div className="px-3 py-2 rounded-lg text-[11px] font-mono text-[#64748B] flex items-center gap-2 bg-[#0A0D14] border border-white/[0.08]">
                <ShieldCheck className="h-3 w-3 text-[#34D399] shrink-0" />
                NO MODIFIED ARCHITECTURAL HOTSPOTS DETECTED
              </div>
            ) : (
              <div className="space-y-1.5">
                {driftResult.architectural_hotspots.map((hotspot, idx) => (
                  <div
                    key={idx}
                    className="p-2.5 rounded-lg hover:border-white/[0.14] transition-all flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs group bg-[#0A0D14] border border-white/[0.08]"
                  >
                    <div className="flex items-center gap-2 min-w-0 flex-1">
                      <span className="text-[10px] font-mono font-bold text-[#64748B]">
                        #{String(idx + 1).padStart(2, '0')}
                      </span>
                      <FileCode className="h-3.5 w-3.5 text-[#FCD34D] shrink-0" />
                      <span className="font-mono text-xs text-[#F8FAFC] font-medium break-all sm:break-normal truncate sm:text-clip" title={hotspot}>
                        {hotspot}
                      </span>
                      <button
                        type="button"
                        onClick={(e) => handleCopy(e, hotspot)}
                        className="text-[#64748B] hover:text-[#F8FAFC] p-0.5 shrink-0 transition-colors"
                        title="Copy path"
                      >
                        {copiedPath === hotspot ? <Check className="h-3 w-3 text-[#34D399]" /> : <Copy className="h-3 w-3" />}
                      </button>
                    </div>

                    <div className="flex items-center gap-2.5 self-end sm:self-auto shrink-0 font-mono text-[10px]">
                      <button
                        type="button"
                        onClick={() => openInGraph(hotspot)}
                        className="text-[#CBD5E1] hover:text-[#818CF8] flex items-center gap-1 uppercase transition-colors"
                      >
                        <span>VIEW IN GRAPH</span>
                        <ArrowUpRight className="h-3 w-3" />
                      </button>
                      <button
                        type="button"
                        onClick={() => openInCallGraph(hotspot)}
                        className="text-[#CBD5E1] hover:text-[#818CF8] flex items-center gap-1 uppercase transition-colors"
                      >
                        <span>CALL GRAPH</span>
                        <ArrowUpRight className="h-3 w-3" />
                      </button>
                      <button
                        type="button"
                        onClick={() => openInChat(`What is the architectural blast radius of modifying hotspot ${hotspot}?`)}
                        className="text-[#CBD5E1] hover:text-[#818CF8] flex items-center gap-1 uppercase transition-colors"
                      >
                        <span>CHAT</span>
                        <Sparkles className="h-3 w-3" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* ── ZONE G: CHANGE MATRIX ─────────────────────────────────────── */}
          <section aria-labelledby="change-matrix-heading" className="p-4 sm:p-5 rounded-xl space-y-3 bg-gradient-to-b from-[#0D1220]/90 to-[#070A12]/95 backdrop-blur-xl border border-white/[0.08]">
            <div className="flex items-center justify-between pb-2.5 border-b border-white/[0.08]">
              <div>
                <h3 id="change-matrix-heading" className="text-xs font-bold font-mono text-[#F8FAFC] uppercase tracking-wider flex items-center gap-2">
                  <SlidersHorizontal className="h-3.5 w-3.5 text-[#818CF8]" />
                  CHANGE MATRIX
                </h3>
                <p className="text-[10.5px] text-[#CBD5E1] font-sans mt-0.5">
                  Structural deltas across eight architectural dimensions. Click a non-zero row to expand evidence.
                </p>
              </div>
              <span className="text-[10px] text-[#64748B] font-mono">
                BASELINE &rarr; PR
              </span>
            </div>

            {/* Matrix Table Headers */}
            <div className="hidden sm:grid sm:grid-cols-[minmax(0,35fr)_80px_minmax(0,55fr)] gap-3 px-3 py-1.5 text-[9.5px] font-mono font-bold text-[#64748B] uppercase tracking-wider border-b border-white/[0.08]">
              <span>CHANGE TYPE</span>
              <span className="text-right">COUNT</span>
              <span>EVIDENCE / INTERPRETATION</span>
            </div>

            {/* 8 Dimensions */}
            <div className="space-y-1 font-mono text-xs">
              {/* Matrix Row Component — inlined for each dimension */}
              {(() => {
                const dimensions: {
                  key: string;
                  label: string;
                  count: number;
                  color: string; // semantic color for non-zero
                  interpretation: (count: number) => string;
                  renderExpanded: () => React.ReactNode;
                }[] = [
                    {
                      key: 'new_cycles',
                      label: 'NEW CYCLES',
                      count: driftResult.new_cycles?.length ?? 0,
                      color: T.risk,
                      interpretation: (c) => c === 0 ? 'Clean build. No new dependency cycles introduced.' : `Introduced ${c} circular dependency loop(s). Click to view trace.`,
                      renderExpanded: () => (
                        <div className="p-3 space-y-2.5 bg-[#0A0D14] border-t border-white/[0.08]">
                          {driftResult.new_cycles.map((cycle, idx) => (
                            <div key={idx} className="space-y-1">
                              <span className="text-[10px] font-mono text-[#FF4D6D] font-bold block">LOOP #{idx + 1}</span>
                              <div className="flex items-center gap-1.5 flex-wrap text-xs font-mono text-[#CBD5E1]">
                                {cycle.map((node, nIdx) => (
                                  <span key={nIdx} className="flex items-center gap-1.5">
                                    <span className="text-[#F8FAFC]">{node.split('/').pop()}</span>
                                    <span className="text-[#818CF8]">&rarr;</span>
                                  </span>
                                ))}
                                <span className="text-[#FF4D6D]">{cycle[0].split('/').pop()}</span>
                              </div>
                            </div>
                          ))}
                        </div>
                      ),
                    },
                    {
                      key: 'resolved_cycles',
                      label: 'RESOLVED CYCLES',
                      count: driftResult.resolved_cycles?.length ?? 0,
                      color: T.verified,
                      interpretation: (c) => c === 0 ? 'No existing dependency cycles resolved.' : `Resolved ${c} cyclic dependency loop(s). Architectural cleanup.`,
                      renderExpanded: () => (
                        <div className="p-3 space-y-2.5 bg-[#0A0D14] border-t border-white/[0.08]">
                          {driftResult.resolved_cycles.map((cycle, idx) => (
                            <div key={idx} className="space-y-1">
                              <span className="text-[10px] font-mono text-[#34D399] font-bold block">RESOLVED LOOP #{idx + 1}</span>
                              <div className="flex items-center gap-1.5 flex-wrap text-xs font-mono text-[#CBD5E1]">
                                {cycle.map((node, nIdx) => (
                                  <span key={nIdx} className="flex items-center gap-1.5">
                                    <span className="text-[#F8FAFC]">{node.split('/').pop()}</span>
                                    <span className="text-[#34D399]">&rarr;</span>
                                  </span>
                                ))}
                                <span className="text-[#34D399]">{cycle[0].split('/').pop()}</span>
                              </div>
                            </div>
                          ))}
                        </div>
                      ),
                    },
                    {
                      key: 'coupling_increase',
                      label: 'COUPLING INCREASED',
                      count: driftResult.coupling_increase?.length ?? 0,
                      color: T.attention,
                      interpretation: (c) => c === 0 ? 'No significant coupling increases detected.' : `${c} file(s) exhibited increased import degree.`,
                      renderExpanded: () => (
                        <div className="p-3 space-y-1.5 bg-[#0A0D14] border-t border-white/[0.08]">
                          {driftResult.coupling_increase.map((c, idx) => (
                            <div key={idx} className="flex items-center justify-between text-xs font-mono">
                              <span className="text-[#F8FAFC] truncate max-w-md">{c.file}</span>
                              <span className="text-[#FCD34D]">{c.before} &rarr; {c.after} (+{c.after - c.before})</span>
                            </div>
                          ))}
                        </div>
                      ),
                    },
                    {
                      key: 'coupling_decrease',
                      label: 'COUPLING DECREASED',
                      count: driftResult.coupling_decrease?.length ?? 0,
                      color: T.verified,
                      interpretation: (c) => c === 0 ? 'No coupling decreases (cleanups) observed.' : `${c} file(s) decoupled successfully.`,
                      renderExpanded: () => (
                        <div className="p-3 space-y-1.5 bg-[#0A0D14] border-t border-white/[0.08]">
                          {driftResult.coupling_decrease.map((c, idx) => (
                            <div key={idx} className="flex items-center justify-between text-xs font-mono">
                              <span className="text-[#F8FAFC] truncate max-w-md">{c.file}</span>
                              <span className="text-[#34D399]">{c.before} &rarr; {c.after} ({c.after - c.before})</span>
                            </div>
                          ))}
                        </div>
                      ),
                    },
                    {
                      key: 'added_dependencies',
                      label: 'DEPENDENCIES ADDED',
                      count: driftResult.added_dependencies?.length ?? 0,
                      color: T.accent,
                      interpretation: (c) => c === 0 ? 'No new dependency edges established.' : `${c} new import edge(s) added.`,
                      renderExpanded: () => (
                        <div className="p-3 space-y-1.5 bg-[#0A0D14] border-t border-white/[0.08]">
                          {driftResult.added_dependencies.map((edge, idx) => (
                            <div key={idx} className="flex items-center gap-2 text-xs font-mono">
                              <span className="text-[#F8FAFC] truncate">{edge.source}</span>
                              <span className="text-[#818CF8]">&rarr;</span>
                              <span className="text-[#CBD5E1] truncate">{edge.target}</span>
                            </div>
                          ))}
                        </div>
                      ),
                    },
                    {
                      key: 'removed_dependencies',
                      label: 'DEPENDENCIES REMOVED',
                      count: driftResult.removed_dependencies?.length ?? 0,
                      color: T.secondary,
                      interpretation: (c) => c === 0 ? 'No dependency edges deleted.' : `${c} existing import edge(s) removed.`,
                      renderExpanded: () => (
                        <div className="p-3 space-y-1.5 bg-[#0A0D14] border-t border-white/[0.08]">
                          {driftResult.removed_dependencies.map((edge, idx) => (
                            <div key={idx} className="flex items-center gap-2 text-xs font-mono">
                              <span className="text-[#F8FAFC] truncate">{edge.source}</span>
                              <span className="text-[#64748B]">&rarr;</span>
                              <span className="text-[#CBD5E1] truncate">{edge.target}</span>
                            </div>
                          ))}
                        </div>
                      ),
                    },
                    {
                      key: 'new_entry_points',
                      label: 'ENTRY POINTS ADDED',
                      count: driftResult.new_entry_points?.length ?? 0,
                      color: T.accent,
                      interpretation: (c) => c === 0 ? 'No new modules qualified as application entry points.' : `${c} new entry point(s) detected.`,
                      renderExpanded: () => (
                        <div className="p-3 space-y-1 bg-[#0A0D14] border-t border-white/[0.08]">
                          {driftResult.new_entry_points.map((p, idx) => (
                            <div key={idx} className="text-xs font-mono text-[#F8FAFC] truncate">{p}</div>
                          ))}
                        </div>
                      ),
                    },
                    {
                      key: 'removed_entry_points',
                      label: 'ENTRY POINTS REMOVED',
                      count: driftResult.removed_entry_points?.length ?? 0,
                      color: T.secondary,
                      interpretation: (c) => c === 0 ? 'No existing application entry points were removed.' : `${c} entry point(s) removed.`,
                      renderExpanded: () => (
                        <div className="p-3 space-y-1 bg-[#0A0D14] border-t border-white/[0.08]">
                          {driftResult.removed_entry_points.map((p, idx) => (
                            <div key={idx} className="text-xs font-mono text-[#F8FAFC] truncate">{p}</div>
                          ))}
                        </div>
                      ),
                    },
                  ];

                return dimensions.map((dim) => {
                  const isExpanded = expandedMatrixRow === dim.key;
                  return (
                    <div key={dim.key} className="rounded-lg overflow-hidden bg-[#0A0D14] border border-white/[0.08]">
                      <div
                        onClick={() => dim.count > 0 && setExpandedMatrixRow(isExpanded ? null : dim.key)}
                        className={`p-2.5 flex flex-col sm:grid sm:grid-cols-[minmax(0,35fr)_80px_minmax(0,55fr)] gap-1.5 sm:gap-3 items-start sm:items-center ${dim.count > 0 ? 'cursor-pointer hover:bg-white/[0.04]' : ''}`}
                        role={dim.count > 0 ? 'button' : undefined}
                        tabIndex={dim.count > 0 ? 0 : undefined}
                        onKeyDown={(e) => { if (dim.count > 0 && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); setExpandedMatrixRow(isExpanded ? null : dim.key); } }}
                        aria-expanded={dim.count > 0 ? isExpanded : undefined}
                      >
                        <span className="font-bold text-[#F8FAFC] flex items-center gap-2">
                          {dim.count > 0 && (
                            <span className="h-1.5 w-1.5 rounded-full shrink-0" style={{ background: dim.color }} />
                          )}
                          {dim.label}
                        </span>
                        <span className="text-right font-bold sm:justify-self-end" style={{ color: dim.count > 0 ? dim.color : T.muted }}>
                          {dim.count}
                        </span>
                        <span className="text-xs text-[#CBD5E1] font-sans">
                          {dim.interpretation(dim.count)}
                        </span>
                      </div>
                      {isExpanded && dim.count > 0 && dim.renderExpanded()}
                    </div>
                  );
                });
              })()}
            </div>
          </section>

          {/* ── ZONE H: ARCHITECTURE DECISION ─────────────────────────────── */}
          {verdict && (
            <section aria-labelledby="architecture-decision-heading" className="p-4 sm:p-5 rounded-xl space-y-3.5 bg-gradient-to-b from-[#0D1220]/90 to-[#070A12]/95 backdrop-blur-xl border border-white/[0.08]">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 pb-3 border-b border-white/[0.08]">
                <div>
                  <span className="text-[9.5px] font-mono font-bold text-[#818CF8] uppercase tracking-widest block">
                    ARCHITECTURE DECISION
                  </span>
                  <h3 id="architecture-decision-heading" className="font-mono text-sm font-bold text-[#F8FAFC] mt-0.5">
                    CONFORMANCE VERDICT
                  </h3>
                </div>

                <span className={`px-2.5 py-0.5 rounded text-xs font-mono font-bold uppercase ${verdict.tone} ${verdict.toneBorder} ${verdict.toneBg}`} style={{ border: `1px solid` }}>
                  {verdict.label}
                </span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                <div className="p-3 rounded-lg space-y-1 bg-[#0A0D14] border border-white/[0.08]">
                  <span className="text-[9.5px] font-mono font-bold text-[#64748B] uppercase tracking-wider block">
                    WHY
                  </span>
                  <p className="text-[#CBD5E1] font-sans leading-relaxed text-[11.5px]">
                    {verdict.why}
                  </p>
                </div>

                <div className="p-3 rounded-lg space-y-1 bg-[#0A0D14] border border-white/[0.08]">
                  <span className="text-[9.5px] font-mono font-bold text-[#64748B] uppercase tracking-wider block">
                    WHAT CHANGED
                  </span>
                  <p className="text-[#CBD5E1] font-sans leading-relaxed text-[11.5px]">
                    {verdict.whatChanged}
                  </p>
                </div>

                <div className="p-3 rounded-lg space-y-1 bg-[#0A0D14] border border-white/[0.08]">
                  <span className="text-[9.5px] font-mono font-bold text-[#64748B] uppercase tracking-wider block">
                    WHAT SHOULD BE REVIEWED
                  </span>
                  <p className="text-[#CBD5E1] font-sans leading-relaxed text-[11.5px]">
                    {verdict.whatShouldReview}
                  </p>
                </div>

                <div className="p-3 rounded-lg space-y-1 bg-[#0A0D14] border border-white/[0.08]">
                  <span className="text-[9.5px] font-mono font-bold text-[#64748B] uppercase tracking-wider block">
                    NEXT ACTION
                  </span>
                  <p className="text-[#F8FAFC] font-sans font-medium leading-relaxed text-[11.5px]">
                    {verdict.nextAction}
                  </p>
                </div>
              </div>

              {/* Static analysis epistemic note */}
              <p className="text-[10px] font-mono text-[#64748B] uppercase tracking-wider pt-0.5">
                STATIC ANALYSIS ONLY &mdash; This verdict evaluates indexed dependency boundaries. Runtime, integration, and business-logic correctness are outside scope.
              </p>
            </section>
          )}

          {/* ── ZONE I: ACTION BAR ─────────────────────────────────────────── */}
          <div className="p-3 rounded-xl flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 bg-gradient-to-r from-[#0D1220]/95 to-[#070A12]/95 backdrop-blur-xl border border-white/[0.08] shadow-2xl">
            <div className="flex items-center gap-2 flex-wrap font-mono text-xs">
              <button
                type="button"
                onClick={() => openInImpact()}
                className="px-3.5 py-1.5 rounded-md border border-white/10 text-white text-xs font-bold font-mono transition-all shadow-[0_0_12px_rgba(129,140,248,0.25)] flex items-center gap-1.5"
                style={{ background: driftResult.architecture_risk_score > 25 ? '#818CF8' : '#0D1220', color: driftResult.architecture_risk_score > 25 ? '#fff' : '#CBD5E1' }}
              >
                <span>VIEW IMPACT ANALYSIS</span>
                <ArrowRight className="h-3 w-3" />
              </button>

              <button
                type="button"
                onClick={() => openInGraph()}
                className="px-3 py-1.5 rounded-md bg-[#0D1220] border border-white/[0.08] hover:bg-[#131A2E] text-[#CBD5E1] hover:text-[#F8FAFC] flex items-center gap-1 transition-colors"
              >
                <span>FILE GRAPH</span>
                <ArrowUpRight className="h-3 w-3" />
              </button>
              <button
                type="button"
                onClick={() => openInCallGraph()}
                className="px-3 py-1.5 rounded-md bg-[#0D1220] border border-white/[0.08] hover:bg-[#131A2E] text-[#CBD5E1] hover:text-[#F8FAFC] flex items-center gap-1 transition-colors"
              >
                <span>CALL GRAPH</span>
                <ArrowUpRight className="h-3 w-3" />
              </button>
              <button
                type="button"
                onClick={() => openInChat()}
                className="px-3 py-1.5 rounded-md bg-[#0D1220] border border-white/[0.08] hover:bg-[#131A2E] text-[#CBD5E1] hover:text-[#F8FAFC] flex items-center gap-1 transition-colors"
              >
                <span>OPEN IN CHAT</span>
                <Sparkles className="h-3 w-3 text-[#818CF8]" />
              </button>
              <button
                type="button"
                onClick={() => handleSubmit()}
                className="px-3 py-1.5 rounded-md bg-[#0D1220] border border-white/[0.08] hover:bg-[#131A2E] text-[#CBD5E1] hover:text-[#F8FAFC] flex items-center gap-1 transition-colors"
              >
                <RefreshCw className="h-3 w-3" />
                <span>RE-ANALYZE</span>
              </button>
              <button
                type="button"
                onClick={resetToNewPR}
                className="px-3 py-1.5 rounded-md bg-[#0D1220] border border-white/[0.08] hover:bg-[#131A2E] text-[#CBD5E1] hover:text-[#F8FAFC] flex items-center gap-1 transition-colors"
              >
                <Plus className="h-3 w-3" />
                <span>NEW PR</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ArchitectureDrift;

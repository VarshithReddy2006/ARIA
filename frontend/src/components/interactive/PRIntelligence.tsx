/**
 * PRIntelligence — ARIA PR Risk & Change Safety Console
 *
 * Answers the core engineering question:
 * "HOW RISKY IS THIS PROPOSED CHANGE?"
 *
 * Experience Flow:
 *   PR INPUT → ANALYSIS READINESS → EXECUTIVE RISK BRIEF → RISK FACTORS →
 *   AFFECTED ARCHITECTURE → TEST EXPOSURE → ENGINEERING VERDICT → ACTION RAIL
 *
 * Pure soft-black glass system, strict epistemic discipline, precision metrics.
 */

import React, { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { apiUrl, extractErrorMessage } from '../../lib/api';
import { FilePath } from '../ui/FilePath';
import {
  AlertTriangle,
  ArrowRight,
  ArrowUpRight,
  Check,
  ChevronDown,
  ChevronUp,
  Copy,
  Cpu,
  ExternalLink,
  FileCode2,
  GitCommit,
  GitPullRequest,
  HelpCircle,
  Layers,
  ListChecks,
  Loader2,
  Plus,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Terminal,
  TestTube,
  Workflow,
  X,
} from 'lucide-react';
import { usePrerequisites } from './pr/usePrerequisites';

// ── Master Dark Glass Design Tokens ───────────────────────────────────────────
const T = {
  canvas: '#050608',
  surface: '#0A0D14',
  elevated: '#0D1220',
  strongElevated: '#131A2E',
  glassCard: 'rgba(13, 18, 32, 0.90)',
  inputBg: '#07090E',
  inputBorder: 'rgba(255, 255, 255, 0.10)',
  hairline: 'rgba(255, 255, 255, 0.08)',
  hairlineStrong: 'rgba(255, 255, 255, 0.14)',
  textPrimary: '#F8FAFC',
  textSecondary: '#CBD5E1',
  textMuted: '#94A3B8',
  textSubtle: '#64748B',
  accent: '#818CF8',
  accentHover: '#A5B4FC',
  accentPressed: '#6366F1',
  rowNormal: '#0A0D14',
  rowHover: '#0D1220',
  rowSelected: '#131A2E',
  // Risk semantics
  low: '#34D399',
  medium: '#FCD34D',
  high: '#FF758F',
  critical: '#FF4D6D',
  unknown: '#94A3B8',
};

// ── Data Models ──────────────────────────────────────────────────────────────
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

function getRiskTone(level: string) {
  const l = (level || '').toUpperCase();
  if (l === 'LOW') return { text: '#34D399', bg: 'rgba(16, 185, 129, 0.12)', border: 'rgba(16, 185, 129, 0.30)' };
  if (l === 'MEDIUM') return { text: '#FCD34D', bg: 'rgba(255, 184, 0, 0.12)', border: 'rgba(255, 184, 0, 0.30)' };
  if (l === 'HIGH') return { text: '#FF758F', bg: 'rgba(255, 77, 109, 0.12)', border: 'rgba(255, 77, 109, 0.30)' };
  if (l === 'CRITICAL') return { text: '#FF4D6D', bg: 'rgba(255, 77, 109, 0.16)', border: 'rgba(255, 77, 109, 0.40)' };
  return { text: '#94A3B8', bg: '#0A0D14', border: 'rgba(255, 255, 255, 0.08)' };
}

const PIPELINE_STAGES = [
  { id: 'pr', num: '01', name: 'PR', desc: 'Metadata & Target' },
  { id: 'files', num: '02', name: 'FILES', desc: 'Diff & AST Mapping' },
  { id: 'symbols', num: '03', name: 'SYMBOLS', desc: 'Symbol Index Query' },
  { id: 'deps', num: '04', name: 'DEPENDENCIES', desc: 'Import Traversal' },
  { id: 'impact', num: '05', name: 'IMPACT', desc: 'Blast Radius & Hotspots' },
  { id: 'risk', num: '06', name: 'RISK', desc: 'Engineering Verdict' },
];

export const PRIntelligence: React.FC<PRIntelligenceProps> = ({ repoName }) => {
  const [activeRepo, setActiveRepo] = useState(() => resolveRepo(repoName));
  const { healthStatus, hasPrerequisites, isRepairing, repair, refresh: refreshPrereqs } = usePrerequisites(activeRepo);

  // Command input mode: URL vs Coordinates
  const [useUrl, setUseUrl] = useState(true);
  const [prUrlInput, setPrUrlInput] = useState('');
  const [ownerInput, setOwnerInput] = useState('');
  const [repoInput, setRepoInput] = useState('');
  const [prNumberInput, setPrNumberInput] = useState('');

  // UI States
  const [isCommandExpanded, setIsCommandExpanded] = useState(true);
  const [isLoading, setIsLoading] = useState(false);
  const [currentStageIdx, setCurrentStageIdx] = useState(0);
  const [analysisResult, setAnalysisResult] = useState<PRAnalysisResult | null>(null);
  const [errorMsg, setErrorMsg] = useState('');
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [copiedPath, setCopiedPath] = useState<string | null>(null);

  // Progressive Disclosure & Search for Affected Files
  const [filesLimit, setFilesLimit] = useState(8);
  const [fileSearch, setFileSearch] = useState('');

  const inputRef = useRef<HTMLInputElement>(null);
  const resultsRef = useRef<HTMLDivElement>(null);

  // Synchronize repo changes
  useEffect(() => {
    const nextRepo = resolveRepo(repoName);
    if (nextRepo !== activeRepo) {
      setActiveRepo(nextRepo);
      setAnalysisResult(null);
      setSelectedFile(null);
      setErrorMsg('');
      setIsCommandExpanded(true);
      setFilesLimit(8);
      setFileSearch('');
    }
  }, [repoName]);

  // Global repository events
  useEffect(() => {
    const handleRepoChanged = (e: Event) => {
      const customEvent = e as CustomEvent<string>;
      if (customEvent.detail && customEvent.detail !== activeRepo) {
        setActiveRepo(customEvent.detail);
        setAnalysisResult(null);
        setSelectedFile(null);
        setErrorMsg('');
        setIsCommandExpanded(true);
      }
    };
    const handleRepoCleared = () => {
      setActiveRepo('');
      setAnalysisResult(null);
      setSelectedFile(null);
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

  // Keyboard Shortcuts: '/' focuses URL input, 'Escape' blurs focus
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (
        e.key === '/' &&
        document.activeElement !== inputRef.current &&
        !(document.activeElement instanceof HTMLInputElement || document.activeElement instanceof HTMLTextAreaElement)
      ) {
        e.preventDefault();
        setIsCommandExpanded(true);
        setTimeout(() => inputRef.current?.focus(), 50);
      } else if (e.key === 'Escape') {
        if (document.activeElement instanceof HTMLElement) {
          document.activeElement.blur();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Validation state
  const isFormValid = useMemo(() => {
    if (useUrl) return Boolean(prUrlInput.trim());
    return Boolean(ownerInput.trim() && repoInput.trim() && prNumberInput.trim());
  }, [useUrl, prUrlInput, ownerInput, repoInput, prNumberInput]);

  /**
   * State of *this* pull-request job. Kept separate from the display label so
   * styling never has to string-compare user-facing copy.
   */
  const validationState: 'loading' | 'failed' | 'complete' | 'ready' | 'waiting' =
    useMemo(() => {
      if (isLoading) return 'loading';
      if (errorMsg) return 'failed';
      if (analysisResult) return 'complete';
      if (isFormValid) return 'ready';
      return 'waiting';
    }, [isLoading, errorMsg, analysisResult, isFormValid]);

  // Labels are scoped to "PR" because this reports the pull-request job, not
  // repository indexing. The bare phrase "ANALYSIS COMPLETE" is reserved for the
  // dashboard shell's single authoritative repository-level indicator.
  const validationStatus = useMemo(
    () =>
      ({
        loading: 'ANALYZING PR…',
        failed: 'PR ANALYSIS FAILED',
        complete: 'PR ANALYSIS COMPLETE',
        ready: 'READY TO ANALYZE',
        waiting: 'WAITING FOR PULL REQUEST',
      })[validationState],
    [validationState],
  );

  // Submit PR analysis
  const handleSubmit = async (e?: React.FormEvent, overrideUrl?: string) => {
    if (e) e.preventDefault();
    if (isLoading) return;

    const urlToSubmit = overrideUrl !== undefined ? overrideUrl : prUrlInput;
    if (overrideUrl !== undefined) {
      setPrUrlInput(overrideUrl);
      setUseUrl(true);
    }

    setIsLoading(true);
    setCurrentStageIdx(0);
    setErrorMsg('');
    setAnalysisResult(null);
    setSelectedFile(null);

    const payload: any = {};
    if (useUrl || overrideUrl !== undefined) {
      if (!urlToSubmit.trim()) {
        setErrorMsg('Please enter a GitHub Pull Request URL.');
        setIsLoading(false);
        return;
      }
      payload.pr_url = urlToSubmit.trim();
    } else {
      if (!ownerInput.trim() || !repoInput.trim() || !prNumberInput.trim()) {
        setErrorMsg('Please specify Owner, Repository, and PR Number.');
        setIsLoading(false);
        return;
      }
      payload.owner = ownerInput.trim();
      payload.repo = repoInput.trim();
      payload.pr_number = parseInt(prNumberInput.trim(), 10);
    }

    // Stage progress animation timer
    const stageTimer = setInterval(() => {
      setCurrentStageIdx((prev) => (prev < 5 ? prev + 1 : prev));
    }, 450);

    try {
      const res = await fetch(apiUrl('/api/v1/pr/analyze'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      clearInterval(stageTimer);

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(extractErrorMessage(errorData) || 'Pull request risk calculation could not be completed.');
      }

      const data: PRAnalysisResult = await res.json();
      setAnalysisResult(data);
      if (data.repo) setActiveRepo(data.repo);
      setIsCommandExpanded(false);
      setFilesLimit(8);

      const firstFile = data.changed_files[0]?.filename || data.affected_files[0] || null;
      setSelectedFile(firstFile);

      setTimeout(() => {
        resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }, 150);
    } catch (err: any) {
      clearInterval(stageTimer);
      setErrorMsg(extractErrorMessage(err) || 'GitHub API or analysis pipeline failed.');
    } finally {
      setIsLoading(false);
    }
  };

  // Ctrl+Enter shortcut handler on input
  const handleKeyDownInput = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      handleSubmit();
    }
  };

  // Reset to new PR
  const resetToNewPR = useCallback(() => {
    setPrUrlInput('');
    setOwnerInput('');
    setRepoInput('');
    setPrNumberInput('');
    setAnalysisResult(null);
    setSelectedFile(null);
    setErrorMsg('');
    setIsCommandExpanded(true);
    setFilesLimit(8);
    setFileSearch('');
    setTimeout(() => inputRef.current?.focus(), 50);
  }, []);

  // Copy helper
  const handleCopy = (e: React.MouseEvent, text: string) => {
    e.stopPropagation();
    navigator.clipboard.writeText(text);
    setCopiedPath(text);
    setTimeout(() => setCopiedPath(null), 1500);
  };

  // Cross-Surface Navigation: File Graph
  const openInGraph = (file?: string) => {
    const target = file || selectedFile || analysisResult?.changed_files[0]?.filename || '';
    const [owner, repo] = (analysisResult?.repo || activeRepo || '').split('/');
    window.dispatchEvent(
      new CustomEvent('aria-open-graph', {
        detail: { owner: owner || undefined, repo: repo || undefined, file: target, path: target, source: 'pr_risk' },
      })
    );
    window.dispatchEvent(new CustomEvent('aria-navigate-tab', { detail: { tab: 'graph', file: target } }));
  };

  // Cross-Surface Navigation: Call Graph
  const openInCallGraph = (file?: string) => {
    const target = file || selectedFile || analysisResult?.changed_files[0]?.filename || '';
    window.dispatchEvent(new CustomEvent('aria-navigate-tab', { detail: { tab: 'call_graph', file: target } }));
  };

  // Cross-Surface Navigation: Impact Analysis
  const openInImpact = () => {
    if (!analysisResult) return;
    const firstChanged = analysisResult.changed_files[0]?.filename || '';
    window.dispatchEvent(
      new CustomEvent('aria-open-impact', {
        detail: {
          repo: analysisResult.repo,
          file: firstChanged,
          query: `Assess blast radius for PR #${analysisResult.pr_number}: ${analysisResult.pr_title}`,
        },
      })
    );
    window.dispatchEvent(new CustomEvent('aria-navigate-tab', { detail: { tab: 'impact_analysis' } }));
  };

  // Cross-Surface Navigation: ARIA Chat
  const openInChat = (customPrompt?: string) => {
    if (!analysisResult) return;
    const [owner, repo] = (analysisResult.repo || activeRepo || '').split('/');
    const prompt =
      customPrompt ||
      `Provide an architectural risk evaluation for PR #${analysisResult.pr_number} (${analysisResult.pr_title}) in ${analysisResult.repo}:
Risk Score: ${analysisResult.risk_score} / 100 (${analysisResult.risk_level} RISK)
Blast Radius: ${analysisResult.blast_radius} (${analysisResult.impact_radius} files reachable)
Changed Files (${analysisResult.changed_files.length}):
${analysisResult.changed_files.slice(0, 5).map((f) => `- ${f.filename} (+${f.additions}/-${f.deletions})`).join('\n')}

What specific architectural review focus, test gaps, and merge risks should be considered?`;

    window.dispatchEvent(
      new CustomEvent('aria-open-chat', {
        detail: { prompt, owner, repo, source: 'pr_risk' },
      })
    );
    window.dispatchEvent(new CustomEvent('aria-navigate-tab', { detail: { tab: 'chat' } }));
  };

  // File selection helper.
  //
  // Uses the shared 'aria-workspace-file-select' contract (payload `{ path }`,
  // consumed by AnalysisDashboard) rather than the panel-private
  // 'aria-pr-file-selected', which had no listener anywhere.
  const selectFile = useCallback((filePath: string) => {
    setSelectedFile(filePath);
    window.dispatchEvent(
      new CustomEvent('aria-workspace-file-select', {
        detail: { path: filePath },
      })
    );
  }, []);

  // Filtered files derived list
  const filteredFiles = useMemo(() => {
    if (!analysisResult) return [];
    const files = analysisResult.changed_files;
    if (!fileSearch.trim()) return files;
    const q = fileSearch.toLowerCase();
    return files.filter(
      (f) =>
        f.filename.toLowerCase().includes(q) ||
        f.status.toLowerCase().includes(q)
    );
  }, [analysisResult, fileSearch]);

  const isSearchActive = Boolean(fileSearch.trim());
  const displayedFiles = useMemo(() => {
    if (isSearchActive) return filteredFiles;
    return filteredFiles.slice(0, filesLimit);
  }, [filteredFiles, isSearchActive, filesLimit]);

  // Synchronize selection safely when search filters update
  useEffect(() => {
    if (selectedFile && filteredFiles.length > 0) {
      const exists = filteredFiles.some((f) => f.filename === selectedFile);
      if (!exists) {
        setSelectedFile(filteredFiles[0]?.filename || null);
      }
    } else if (!selectedFile && filteredFiles.length > 0) {
      setSelectedFile(filteredFiles[0]?.filename || null);
    } else if (filteredFiles.length === 0) {
      setSelectedFile(null);
    }
  }, [filteredFiles, selectedFile]);

  // Derived Engineering Verdict
  const engineeringVerdict = useMemo(() => {
    if (!analysisResult) return null;
    const score = analysisResult.risk_score;
    const hasCoreTouches = analysisResult.changed_core_files.length > 0;
    const hasEntryTouches = analysisResult.changed_entry_points.length > 0;
    const hasHighCoupling = analysisResult.changed_high_coupling_files.length > 0;
    const blast = (analysisResult.blast_radius || 'LOW').toUpperCase();

    if (score > 80 || (blast === 'EXTREME' && hasCoreTouches)) {
      return {
        status: 'BLOCK MERGE',
        tone: T.critical,
        why: 'Critical architectural exposure. Modifications alter central core modules with deep transitive ripple chains.',
        reviewFocus: 'Require senior architect sign-off, run comprehensive system regression, and verify public APIs.',
        nextAction: 'Decompose this PR into staged micro-PRs to isolate subsystem risk before considering merge.',
      };
    }
    if (score >= 61 || hasCoreTouches || hasEntryTouches) {
      return {
        status: 'HIGH RISK',
        tone: T.high,
        why: `Elevated blast radius (${analysisResult.impact_radius} downstream files) touches core or public entry-point files.`,
        reviewFocus: 'Deep code review of modified entry points and contract validation across downstream consumers.',
        nextAction: 'Run targeted integration suites and obtain code-owner approvals from affected subsystems.',
      };
    }
    if (score >= 30 || hasHighCoupling || blast === 'MEDIUM') {
      return {
        status: 'REVIEW REQUIRED',
        tone: T.medium,
        why: 'Moderate coupling change. Modifications extend beyond isolated modules but stay within known package boundaries.',
        reviewFocus: 'Check affected test callers and confirm no circular dependency introductions.',
        nextAction: 'Proceed with standard team review and verify test execution on modified behavior.',
      };
    }
    return {
      status: 'SAFE TO PROCEED',
      tone: T.low,
      why: 'No significant architectural drift or hotspot regressions detected. Blast radius is strictly contained.',
      reviewFocus: 'Standard review of diff formatting and localized logic verification.',
      nextAction: 'Proceed with standard code review and merge upon CI pass.',
    };
  }, [analysisResult]);

  // Test exposure calculation
  const testExposure = useMemo(() => {
    if (!analysisResult) return null;
    const testPattern = /(test|spec|__tests__|tests\/)/i;
    const changedTests = analysisResult.changed_files.filter((f) => testPattern.test(f.filename));
    const affectedTests = analysisResult.affected_files.filter((f) => testPattern.test(f));

    return {
      changedTests,
      affectedTests,
      hasDirectTests: changedTests.length > 0,
      totalDetected: changedTests.length + affectedTests.length,
    };
  }, [analysisResult]);

  // Risk factors combined list
  const riskFactors = useMemo(() => {
    if (!analysisResult) return [];
    const factors: Array<{ name: string; score: number; detail: string; severity: string; tone: string }> = [];

    (analysisResult.risk_breakdown || []).forEach((rb) => {
      let severity = 'LOW';
      let tone = T.low;
      if (rb.score >= 25) {
        severity = 'CRITICAL';
        tone = T.critical;
      } else if (rb.score >= 15) {
        severity = 'HIGH';
        tone = T.high;
      } else if (rb.score >= 8) {
        severity = 'MODERATE';
        tone = T.medium;
      }
      factors.push({ name: rb.factor, score: rb.score, detail: rb.detail, severity, tone });
    });

    return factors;
  }, [analysisResult]);

  const riskTone = analysisResult ? getRiskTone(analysisResult.risk_level) : getRiskTone('UNKNOWN');

  return (
    <div className="flex flex-col text-[#F5F7FA] min-w-0 space-y-4 font-sans">
      {/* ── ZONE 1: PAGE HEADER ─────────────────────────────────────────── */}
      <header className="min-w-0 pb-3" style={{ borderBottom: `1px solid ${T.hairline}` }}>
        <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-3">
          <div className="min-w-0 max-w-2xl space-y-1">
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-bold text-[#818CF8] uppercase tracking-widest font-mono">
                PR RISK / CHANGE SAFETY
              </span>
              <span className="h-1 w-1 rounded-full bg-white/20" />
              <span className="text-[9.5px] font-mono text-[#94A3B8] uppercase tracking-wider flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full bg-[#34D399] shadow-[0_0_8px_rgba(52,211,153,0.5)]" />
                INDEXED BASELINE: READY
              </span>
            </div>
            <h2 className="text-lg sm:text-xl font-bold text-[#F8FAFC] tracking-tight font-mono leading-tight">
              HOW RISKY IS THIS PROPOSED CHANGE?
            </h2>
            <p className="text-xs text-[#CBD5E1] leading-relaxed max-w-xl font-sans">
              Assess blast radius, structural exposure, affected components, test exposure, and review risk before merging.
            </p>
          </div>

          <div className="flex items-center gap-2.5 self-start lg:self-auto shrink-0">
            {activeRepo && (
              <div
                className="px-2.5 py-1 rounded-md border text-xs font-mono text-[#CBD5E1] flex items-center gap-2"
                style={{ background: T.surface, borderColor: T.hairline }}
              >
                <span className="text-[9px] uppercase tracking-wider text-[#94A3B8]">REPO:</span>
                <span className="text-[#F8FAFC] font-semibold">{activeRepo}</span>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* ── ZONE 2: PR COMMAND CENTER & READINESS RAIL ────────────────── */}
      <div
        className="rounded-xl border shadow-lg overflow-hidden transition-all bg-gradient-to-b from-[#0D1220]/90 to-[#070A12]/95 backdrop-blur-xl"
        style={{ borderColor: T.hairline }}
      >
        {/* Command Center Header Bar */}
        <div
          className="px-3.5 py-2.5 sm:px-4 sm:py-3 flex items-center justify-between"
          style={{ borderBottom: `1px solid ${T.hairline}` }}
        >
          <div className="flex items-center gap-2.5 min-w-0">
            <GitPullRequest className="h-3.5 w-3.5 text-[#818CF8] shrink-0" />
            <span className="text-[10px] font-mono font-bold text-[#818CF8] uppercase tracking-widest shrink-0">
              PR COMMAND CENTER
            </span>
            <span className="h-1 w-1 rounded-full bg-white/20 hidden sm:inline" />
            <span
              className="text-[9px] font-mono px-2 py-0.5 rounded font-bold uppercase tracking-wider"
              style={{
                background:
                  validationState === 'loading'
                    ? 'rgba(129,140,248,0.15)'
                    : validationState === 'complete'
                      ? 'rgba(52,211,153,0.15)'
                      : validationState === 'failed'
                        ? 'rgba(255,77,109,0.15)'
                        : T.elevated,
                color:
                  validationState === 'loading'
                    ? '#818CF8'
                    : validationState === 'complete'
                      ? '#34D399'
                      : validationState === 'failed'
                        ? '#FF758F'
                        : '#CBD5E1',
                border: '1px solid rgba(255,255,255,0.07)',
              }}
            >
              {validationStatus}
            </span>

            {analysisResult && !isCommandExpanded && (
              <span className="text-[11px] font-mono text-[#CBD5E1] max-w-xs sm:max-w-md truncate ml-2">
                PR #{analysisResult.pr_number} &middot; {analysisResult.repo} &middot; ANALYZED{' '}
                {relativeTime(analysisResult.analyzed_at).toUpperCase()}
              </span>
            )}
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <span className="text-[10px] font-mono text-[#94A3B8] hidden xl:inline">
              Press{' '}
              <kbd className="px-1.5 py-0.5 rounded text-[#CBD5E1]" style={{ background: T.inputBg, border: `1px solid ${T.inputBorder}` }}>
                /
              </kbd>{' '}
              to focus &middot;{' '}
              <kbd className="px-1.5 py-0.5 rounded text-[#CBD5E1]" style={{ background: T.inputBg, border: `1px solid ${T.inputBorder}` }}>
                Ctrl+Enter
              </kbd>{' '}
              to analyze
            </span>

            {analysisResult && (
              <>
                <button
                  type="button"
                  onClick={resetToNewPR}
                  className="px-2.5 py-1 rounded hover:bg-[#131A2E] text-[10.5px] font-mono text-[#CBD5E1] hover:text-[#F8FAFC] flex items-center gap-1.5 transition-colors"
                  style={{ background: T.elevated, border: '1px solid rgba(255,255,255,0.07)' }}
                  title="Clear inputs and start a new PR analysis"
                >
                  <Plus className="h-3 w-3" />
                  <span className="hidden sm:inline">NEW PR</span>
                </button>

                <button
                  type="button"
                  onClick={() => setIsCommandExpanded(!isCommandExpanded)}
                  className="px-2.5 py-1 rounded hover:bg-[#131A2E] text-[10.5px] font-mono text-[#CBD5E1] hover:text-[#F8FAFC] flex items-center gap-1.5 transition-colors"
                  style={{ background: T.elevated, border: '1px solid rgba(255,255,255,0.07)' }}
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

        {/* Collapsible Form Body */}
        {isCommandExpanded && (
          <div className="p-4 sm:p-5 space-y-4">
            {/* Mode Switcher */}
            <div className="flex items-center gap-6 border-b border-white/[0.055] pb-2">
              <button
                type="button"
                onClick={() => setUseUrl(true)}
                className={`font-mono text-xs uppercase tracking-wider pb-1.5 transition-colors relative ${useUrl ? 'text-[#F8FAFC] font-bold' : 'text-[#94A3B8] hover:text-[#CBD5E1]'
                  }`}
              >
                PR URL
                {useUrl && <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-[#818CF8]" />}
              </button>
              <button
                type="button"
                onClick={() => setUseUrl(false)}
                className={`font-mono text-xs uppercase tracking-wider pb-1.5 transition-colors relative ${!useUrl ? 'text-[#F8FAFC] font-bold' : 'text-[#94A3B8] hover:text-[#CBD5E1]'
                  }`}
              >
                REPOSITORY COORDINATES
                {!useUrl && <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-[#818CF8]" />}
              </button>
            </div>

            {/* Inputs */}
            {useUrl ? (
              <div className="space-y-1.5">
                <label htmlFor="pr-url-input" className="text-[10px] font-mono font-bold text-[#94A3B8] uppercase tracking-wider block">
                  GITHUB PULL REQUEST URL
                </label>
                <div className="relative">
                  <input
                    ref={inputRef}
                    id="pr-url-input"
                    type="text"
                    value={prUrlInput}
                    onChange={(e) => setPrUrlInput(e.target.value)}
                    onKeyDown={handleKeyDownInput}
                    placeholder="https://github.com/owner/repo/pull/123"
                    className="w-full rounded-lg px-3 py-2 text-xs text-[#F8FAFC] placeholder-[#64748B] font-mono focus:border-[#818CF8] focus-visible:outline-none transition-colors leading-relaxed"
                    style={{ background: T.inputBg, border: `1px solid ${T.inputBorder}` }}
                  />
                  {prUrlInput && (
                    <button
                      type="button"
                      onClick={() => setPrUrlInput('')}
                      className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[#94A3B8] hover:text-[#F8FAFC]"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="space-y-1">
                  <label htmlFor="pr-owner-input" className="text-[10px] font-mono font-bold text-[#94A3B8] uppercase tracking-wider block">
                    OWNER
                  </label>
                  <input
                    id="pr-owner-input"
                    type="text"
                    value={ownerInput}
                    onChange={(e) => setOwnerInput(e.target.value)}
                    placeholder="geturbackend"
                    className="w-full rounded-lg px-3 py-1.5 text-xs text-[#F8FAFC] placeholder-[#64748B] font-mono focus:border-[#818CF8] focus-visible:outline-none"
                    style={{ background: T.inputBg, border: `1px solid ${T.inputBorder}` }}
                  />
                </div>
                <div className="space-y-1">
                  <label htmlFor="pr-repo-input" className="text-[10px] font-mono font-bold text-[#94A3B8] uppercase tracking-wider block">
                    REPOSITORY
                  </label>
                  <input
                    id="pr-repo-input"
                    type="text"
                    value={repoInput}
                    onChange={(e) => setRepoInput(e.target.value)}
                    placeholder="urbackend"
                    className="w-full rounded-lg px-3 py-1.5 text-xs text-[#F8FAFC] placeholder-[#64748B] font-mono focus:border-[#818CF8] focus-visible:outline-none"
                    style={{ background: T.inputBg, border: `1px solid ${T.inputBorder}` }}
                  />
                </div>
                <div className="space-y-1">
                  <label htmlFor="pr-number-input" className="text-[10px] font-mono font-bold text-[#94A3B8] uppercase tracking-wider block">
                    PR NUMBER
                  </label>
                  <input
                    id="pr-number-input"
                    type="text"
                    value={prNumberInput}
                    onChange={(e) => setPrNumberInput(e.target.value)}
                    placeholder="402"
                    className="w-full rounded-lg px-3 py-1.5 text-xs text-[#F8FAFC] placeholder-[#64748B] font-mono focus:border-[#818CF8] focus-visible:outline-none"
                    style={{ background: T.inputBg, border: `1px solid ${T.inputBorder}` }}
                  />
                </div>
              </div>
            )}

            {/* Compact System Readiness Rail (Section 6) */}
            <div
              className="p-2.5 rounded-lg grid grid-cols-2 sm:grid-cols-4 gap-2 text-[10px] font-mono"
              style={{ background: T.surface, border: `1px solid ${T.hairline}` }}
            >
              <div className="flex items-center justify-between px-2 py-1 rounded bg-[#050609] border border-white/[0.04]">
                <span className="text-[#94A3B8]">GITHUB AUTH:</span>
                <span className={healthStatus?.github_auth ? 'text-[#34D399] font-bold' : 'text-[#FF758F] font-bold'}>
                  {healthStatus?.github_auth ? '● ACTIVE' : '● UNAVAILABLE'}
                </span>
              </div>
              <div className="flex items-center justify-between px-2 py-1 rounded bg-[#050609] border border-white/[0.04]">
                <span className="text-[#94A3B8]">DEPENDENCY GRAPH:</span>
                <span className={healthStatus?.graph_available ? 'text-[#34D399] font-bold' : 'text-[#FF758F] font-bold'}>
                  {healthStatus?.graph_available ? '● READY' : '● UNAVAILABLE'}
                </span>
              </div>
              <div className="flex items-center justify-between px-2 py-1 rounded bg-[#050609] border border-white/[0.04]">
                <span className="text-[#94A3B8]">SYMBOL INDEX:</span>
                <span className={healthStatus?.symbol_index_available ? 'text-[#34D399] font-bold' : 'text-[#FF758F] font-bold'}>
                  {healthStatus?.symbol_index_available ? '● READY' : '● UNAVAILABLE'}
                </span>
              </div>
              <div className="flex items-center justify-between px-2 py-1 rounded bg-[#050609] border border-white/[0.04]">
                <span className="text-[#94A3B8]">BASELINE GRAPH:</span>
                <span className={healthStatus?.analysis_exists ? 'text-[#34D399] font-bold' : 'text-[#FF758F] font-bold'}>
                  {healthStatus?.analysis_exists ? '● READY' : '● UNAVAILABLE'}
                </span>
              </div>
            </div>

            {/* Prerequisite warning banner if missing */}
            {!hasPrerequisites && (
              <div
                className="p-3 rounded-lg flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 text-xs font-mono"
                style={{ background: 'rgba(252,211,77,0.08)', border: '1px solid rgba(252,211,77,0.3)', color: '#FCD34D' }}
              >
                <div className="flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4 shrink-0" />
                  <span>Repository baseline is missing dependency graph or symbol index. Run indexing before analyzing PR risk.</span>
                </div>
                <button
                  type="button"
                  onClick={repair}
                  disabled={isRepairing}
                  className="px-3 py-1 rounded bg-[#FCD34D]/20 hover:bg-[#FCD34D]/30 text-[#F8FAFC] text-xs font-bold uppercase transition-colors shrink-0"
                >
                  {isRepairing ? 'REPAIRING BASELINE…' : 'REPAIR BASELINE'}
                </button>
              </div>
            )}

            {/* Presets & Primary CTA bar */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-1">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[10px] font-mono font-bold text-[#94A3B8] uppercase tracking-wider shrink-0">
                  EXAMPLE PRS:
                </span>
                <button
                  type="button"
                  onClick={() => handleSubmit(undefined, 'https://github.com/geturbackend/urbackend/pull/402')}
                  className="px-2.5 py-1 rounded hover:bg-[#131A2E] text-[11px] font-mono text-[#CBD5E1] hover:text-[#F8FAFC] transition-colors"
                  style={{ background: T.elevated, border: '1px solid rgba(255,255,255,0.07)' }}
                >
                  geturbackend #402 (OAuth)
                </button>
                <button
                  type="button"
                  onClick={() => handleSubmit(undefined, 'https://github.com/geturbackend/urbackend/pull/415')}
                  className="px-2.5 py-1 rounded hover:bg-[#131A2E] text-[11px] font-mono text-[#CBD5E1] hover:text-[#F8FAFC] transition-colors"
                  style={{ background: T.elevated, border: '1px solid rgba(255,255,255,0.07)' }}
                >
                  geturbackend #415 (DB Query)
                </button>
              </div>

              <button
                type="button"
                onClick={() => handleSubmit()}
                disabled={isLoading || !isFormValid}
                className="px-5 py-2 rounded-lg bg-[#818CF8] hover:bg-[#A5B4FC] active:bg-[#6366F1] shadow-[0_0_20px_rgba(129,140,248,0.25)] disabled:opacity-40 disabled:cursor-not-allowed text-white text-xs font-bold font-mono tracking-wider transition-colors flex items-center justify-center gap-2 shrink-0 cursor-pointer"
              >
                {isLoading ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    <span>ANALYZING PULL REQUEST…</span>
                  </>
                ) : (
                  <>
                    <span>ANALYZE PULL REQUEST</span>
                    <ArrowRight className="h-3 w-3" />
                  </>
                )}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* ── ZONE 3: 6-STAGE ANALYSIS PIPELINE ───────────────────────────── */}
      <div
        className="p-3.5 rounded-xl border font-mono text-xs bg-gradient-to-b from-[#0D1220]/90 to-[#070A12]/95 backdrop-blur-xl"
        style={{ borderColor: T.hairline }}
      >
        <div className="flex items-center justify-between pb-2.5 border-b border-white/[0.055]">
          <span className="text-[10px] font-bold text-[#94A3B8] uppercase tracking-widest flex items-center gap-2">
            <Workflow className="h-3.5 w-3.5 text-[#818CF8]" />
            PR RISK ANALYSIS PIPELINE
          </span>
          <span className="text-[9px] text-[#94A3B8] uppercase tracking-wider">
            6 FORENSIC STAGES
          </span>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2 pt-3">
          {PIPELINE_STAGES.map((stage, idx) => {
            let status = 'STANDBY';
            let dotColor = '#475569';
            let isComplete = false;
            let isActive = false;

            if (analysisResult) {
              status = 'COMPLETE';
              dotColor = '#34D399';
              isComplete = true;
            } else if (isLoading) {
              if (idx < currentStageIdx) {
                status = 'COMPLETE';
                dotColor = '#34D399';
                isComplete = true;
              } else if (idx === currentStageIdx) {
                status = 'ACTIVE';
                dotColor = '#818CF8';
                isActive = true;
              }
            } else if (errorMsg && idx === currentStageIdx) {
              status = 'FAILED';
              dotColor = '#FF758F';
            }

            return (
              <div
                key={stage.id}
                className={`p-2 rounded-lg space-y-1 transition-all ${isActive ? 'border-[#818CF8] bg-[#131A2E]' : 'border-white/[0.055] bg-[#0A0D14]'
                  }`}
                style={{ border: `1px solid ${isActive ? '#818CF8' : T.hairline}` }}
              >
                <div className="flex items-center justify-between">
                  <span className="text-[9px] text-[#94A3B8] font-bold">{stage.num}</span>
                  {isComplete ? (
                    <Check className="h-3 w-3 text-[#34D399]" />
                  ) : isActive ? (
                    <Loader2 className="h-3 w-3 text-[#818CF8] animate-spin" />
                  ) : (
                    <span className="h-1.5 w-1.5 rounded-full" style={{ background: dotColor }} />
                  )}
                </div>
                <span className="text-[11px] font-bold text-[#F8FAFC] block truncate">{stage.name}</span>
                <span className="text-[9px] text-[#94A3B8] block truncate">{stage.desc}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* ── ERROR DISPLAY ───────────────────────────────────────────────── */}
      {errorMsg && (
        <div
          role="alert"
          className="p-4 rounded-xl border flex items-start gap-3 text-xs font-mono"
          style={{ background: 'rgba(255,77,109,0.08)', borderColor: 'rgba(255,77,109,0.3)', color: '#F8FAFC' }}
        >
          <AlertTriangle className="h-4 w-4 text-[#FF758F] shrink-0 mt-0.5" />
          <div className="space-y-1">
            <span className="text-xs font-bold text-[#FF758F] uppercase block">
              PR ANALYSIS FAILED
            </span>
            <p className="text-[#CBD5E1] font-sans leading-relaxed">{errorMsg}</p>
            <button
              type="button"
              onClick={() => handleSubmit()}
              className="mt-2 px-3 py-1 rounded bg-[#FF758F]/20 hover:bg-[#FF758F]/30 text-[#FF758F] text-[10px] font-bold uppercase transition-colors"
            >
              RETRY ANALYSIS
            </button>
          </div>
        </div>
      )}

      {/* ── ZONE 4 & 5: RESULTS WORKSPACE ───────────────────────────────── */}
      {analysisResult && (
        <div ref={resultsRef} className="space-y-4">
          {/* ── ZONE 4: EXECUTIVE PR RISK BRIEF ─────────────────────────── */}
          <section
            aria-labelledby="pr-executive-brief"
            className="p-4 sm:p-5 rounded-xl space-y-3.5 bg-gradient-to-b from-[#0D1220]/90 to-[#070A12]/95 backdrop-blur-xl"
            style={{ border: `1px solid ${T.hairline}` }}
          >
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 pb-3 border-b border-white/[0.055]">
              <div>
                <span className="text-[9.5px] font-mono font-bold text-[#818CF8] uppercase tracking-widest block">
                  EXECUTIVE PR RISK BRIEF
                </span>
                <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                  <h3 id="pr-executive-brief" className="font-mono text-sm sm:text-base font-bold text-[#F8FAFC]">
                    PR #{analysisResult.pr_number} &middot; {analysisResult.pr_title}
                  </h3>
                  <span
                    className="px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase"
                    style={{ background: riskTone.bg, color: riskTone.text, border: `1px solid ${riskTone.border}` }}
                  >
                    {analysisResult.risk_level} RISK
                  </span>
                </div>
                <p className="text-[11px] font-mono text-[#94A3B8] mt-0.5">
                  {analysisResult.repo} &middot; ANALYZED {relativeTime(analysisResult.analyzed_at).toUpperCase()}
                </p>
              </div>

              <div className="flex items-center gap-2 shrink-0">
                <a
                  href={analysisResult.pr_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="px-3 py-1.5 rounded-md hover:bg-[#131A2E] text-[#CBD5E1] hover:text-[#F8FAFC] text-xs font-mono transition-colors flex items-center gap-1.5"
                  style={{ background: T.elevated, border: '1px solid rgba(255,255,255,0.07)' }}
                >
                  <span>VIEW ON GITHUB</span>
                  <ExternalLink className="h-3 w-3" />
                </a>
              </div>
            </div>

            {/* Continuous Analytical Metric Rail with Clear Dominant Hierarchy */}
            <div
              className="rounded-lg overflow-hidden font-mono divide-y divide-white/[0.06]"
              style={{ border: `1px solid ${T.hairline}`, background: T.surface }}
            >
              {/* Primary Dominant Tier */}
              <div className="grid grid-cols-1 sm:grid-cols-3 divide-y sm:divide-y-0 sm:divide-x divide-white/[0.06]">
                {/* 1. RISK SCORE (Dominant) */}
                <div className="p-3.5 space-y-1" style={{ background: T.surface }}>
                  <div className="flex items-baseline justify-between">
                    <span className="text-3xl font-bold tracking-tight tabular-nums" style={{ color: riskTone.text }}>
                      {analysisResult.risk_score}
                      <span className="text-sm text-[#94A3B8] font-normal"> / 100</span>
                    </span>
                    <span className="text-[10px] font-mono font-bold uppercase tracking-widest" style={{ color: riskTone.text }}>
                      {analysisResult.risk_level} RISK
                    </span>
                  </div>
                  <span className="text-[9px] font-mono text-[#94A3B8] uppercase tracking-wider block">
                    {analysisResult.risk_score < 30
                      ? 'LOCALIZED DIFF · LOW DRIFT'
                      : analysisResult.risk_score < 60
                        ? 'MODERATE CHURN · REVIEW SUGGESTED'
                        : 'ELEVATED REGRESSION EXPOSURE'}
                  </span>
                </div>

                {/* 2. AFFECTED FILES (Dominant) */}
                <div className="p-3.5 space-y-1" style={{ background: T.surface }}>
                  <div className="flex items-baseline justify-between">
                    <span className="text-3xl font-bold tracking-tight text-[#F8FAFC] tabular-nums">
                      {analysisResult.affected_files.length || analysisResult.changed_files.length}
                    </span>
                    <span className="text-[10px] font-mono font-bold uppercase tracking-widest text-[#818CF8]">
                      AFFECTED FILES
                    </span>
                  </div>
                  <span className="text-[9px] font-mono text-[#94A3B8] uppercase tracking-wider block">
                    TOTAL REACHABLE IN REPO
                  </span>
                </div>

                {/* 3. DOWNSTREAM REACH (Dominant) */}
                <div className="p-3.5 space-y-1" style={{ background: T.surface }}>
                  <div className="flex items-baseline justify-between">
                    <span className="text-3xl font-bold tracking-tight text-[#FCD34D] tabular-nums">
                      {analysisResult.impact_radius}
                    </span>
                    <span className="text-[10px] font-mono font-bold uppercase tracking-widest text-[#FCD34D]">
                      {analysisResult.blast_radius}
                    </span>
                  </div>
                  <span className="text-[9px] font-mono text-[#94A3B8] uppercase tracking-wider block">
                    TRANSITIVE DOWNSTREAM REACH
                  </span>
                </div>
              </div>

              {/* Secondary Supporting Tier */}
              <div className="grid grid-cols-2 sm:grid-cols-4 divide-x divide-white/[0.06] text-xs">
                {/* 4. FILES CHANGED */}
                <div className="p-2.5 px-3 space-y-0.5" style={{ background: T.elevated }}>
                  <div className="flex items-baseline justify-between">
                    <span className="text-lg font-bold text-[#F8FAFC] tabular-nums">
                      {analysisResult.changed_files.length}
                    </span>
                    <span className="text-[8.5px] font-mono font-bold text-[#94A3B8] uppercase tracking-widest">
                      FILES
                    </span>
                  </div>
                  <span className="text-[8.5px] font-mono text-[#94A3B8] uppercase block">
                    <span className="text-[#34D399]">+{analysisResult.total_additions}</span> /{' '}
                    <span className="text-[#FF758F]">-{analysisResult.total_deletions}</span>
                  </span>
                </div>

                {/* 5. SYMBOLS TOUCHED */}
                <div className="p-2.5 px-3 space-y-0.5" style={{ background: T.elevated }}>
                  <div className="flex items-baseline justify-between">
                    <span className="text-lg font-bold text-[#F8FAFC] tabular-nums">
                      {analysisResult.added_symbols.length +
                        analysisResult.modified_symbols.length +
                        analysisResult.removed_symbols.length}
                    </span>
                    <span className="text-[8.5px] font-mono font-bold text-[#94A3B8] uppercase tracking-widest">
                      SYMBOLS
                    </span>
                  </div>
                  <span className="text-[8.5px] font-mono text-[#94A3B8] uppercase block">
                    {analysisResult.modified_symbols.length} MODIFIED &middot; {analysisResult.added_symbols.length} ADDED
                  </span>
                </div>

                {/* 6. TEST EXPOSURE */}
                <div className="p-2.5 px-3 space-y-0.5" style={{ background: T.elevated }}>
                  <div className="flex items-baseline justify-between">
                    <span
                      className={`text-lg font-bold tabular-nums ${testExposure?.hasDirectTests ? 'text-[#34D399]' : 'text-[#FCD34D]'
                        }`}
                    >
                      {testExposure?.changedTests.length || 0}
                    </span>
                    <span className="text-[8.5px] font-mono font-bold text-[#94A3B8] uppercase tracking-widest">
                      TEST IMPACT
                    </span>
                  </div>
                  <span className="text-[8.5px] font-mono text-[#94A3B8] uppercase block truncate">
                    {testExposure?.hasDirectTests ? 'DIRECT TESTS MODIFIED' : 'NO DIRECT TESTS'}
                  </span>
                </div>

                {/* 7. PR SIZE */}
                <div className="p-2.5 px-3 space-y-0.5" style={{ background: T.elevated }}>
                  <div className="flex items-baseline justify-between">
                    <span className="text-lg font-bold text-[#818CF8] tabular-nums">
                      {analysisResult.pr_size}
                    </span>
                    <span className="text-[8.5px] font-mono font-bold text-[#818CF8] uppercase tracking-widest">
                      PR SIZE
                    </span>
                  </div>
                  <span className="text-[8.5px] font-mono text-[#94A3B8] uppercase block">
                    MAX DEPTH {analysisResult.max_depth} HOPS
                  </span>
                </div>
              </div>
            </div>
          </section>

          {/* ── ZONE 5: RISK FACTOR FORENSIC ANALYSIS (Section 10) ────────── */}
          <section
            aria-labelledby="pr-risk-factors"
            className="p-4 sm:p-5 rounded-xl space-y-3.5 bg-gradient-to-b from-[#0D1220]/90 to-[#070A12]/95 backdrop-blur-xl"
            style={{ border: `1px solid ${T.hairline}` }}
          >
            <div className="flex items-center justify-between pb-2.5 border-b border-white/[0.055]">
              <div>
                <h3 id="pr-risk-factors" className="text-xs font-bold font-mono text-[#F8FAFC] uppercase tracking-wider flex items-center gap-2">
                  <Cpu className="h-3.5 w-3.5 text-[#818CF8]" />
                  RISK FACTORS ({riskFactors.length})
                </h3>
                <p className="text-[10.5px] text-[#CBD5E1] font-sans mt-0.5">
                  Forensic evaluation of PR impact vectors and weighted regression scores.
                </p>
              </div>

              {analysisResult.top_risks.length > 0 && (
                <span className="text-[9px] font-mono text-[#FF758F] uppercase px-2 py-0.5 rounded bg-[#FF758F]/10 border border-[#FF758F]/30 font-bold">
                  {analysisResult.top_risks.length} CRITICAL VECTOR(S)
                </span>
              )}
            </div>

            <div className="space-y-1.5 font-mono text-xs">
              {riskFactors.map((factor, idx) => (
                <div
                  key={idx}
                  className="p-3 rounded-lg flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 transition-colors hover:bg-[#131A2E]"
                  style={{ background: T.surface, border: `1px solid ${T.hairline}` }}
                >
                  <div className="space-y-0.5 min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-[9px] font-bold text-[#94A3B8] shrink-0">
                        {String(idx + 1).padStart(2, '0')}
                      </span>
                      <span className="text-xs font-bold text-[#F8FAFC] uppercase tracking-wider">
                        {factor.name}
                      </span>
                      <span
                        className="text-[8.5px] font-bold px-1.5 py-0.2 rounded uppercase"
                        style={{ color: factor.tone, background: `${factor.tone}15`, border: `1px solid ${factor.tone}35` }}
                      >
                        {factor.severity}
                      </span>
                    </div>
                    <p className="text-[11px] text-[#CBD5E1] font-sans leading-relaxed">{factor.detail}</p>
                  </div>

                  <div className="flex items-center gap-2 shrink-0 self-end sm:self-center text-xs">
                    <span className="text-[10px] text-[#94A3B8]">WEIGHT:</span>
                    <span className="text-[11px] font-bold text-[#F8FAFC] px-2 py-0.5 rounded bg-[#050609] border border-white/[0.07] tabular-nums">
                      {factor.score} PTS
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* ── ZONE 6: AFFECTED ARCHITECTURE & HOTSPOTS (Section 11) ──────── */}
          <section
            aria-labelledby="pr-architecture-heading"
            className="p-4 sm:p-5 rounded-xl space-y-3.5 bg-gradient-to-b from-[#0D1220]/90 to-[#070A12]/95 backdrop-blur-xl"
            style={{ border: `1px solid ${T.hairline}` }}
          >
            <div className="flex items-center justify-between pb-2.5 border-b border-white/[0.055]">
              <div>
                <h3 id="pr-architecture-heading" className="text-xs font-bold font-mono text-[#F8FAFC] uppercase tracking-wider flex items-center gap-2">
                  <Layers className="h-3.5 w-3.5 text-[#818CF8]" />
                  AFFECTED ARCHITECTURE & HOTSPOTS
                </h3>
                <p className="text-[10.5px] text-[#CBD5E1] font-sans mt-0.5">
                  Subsystem boundaries, entry points, and high-coupling nodes touched by this diff.
                </p>
              </div>
            </div>

            {/* Hotspots Breakdown */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 font-mono text-xs">
              {/* Entry Points */}
              <div
                className="p-3.5 rounded-lg space-y-2"
                style={{
                  background: T.surface,
                  border: `1px solid ${analysisResult.changed_entry_points.length > 0 ? 'rgba(255,117,143,0.3)' : T.hairline}`,
                  borderLeft: analysisResult.changed_entry_points.length > 0 ? `2px solid #FF758F` : undefined,
                }}
              >
                <div className="flex items-center justify-between">
                  <span className="text-[10.5px] font-bold text-[#F8FAFC] uppercase tracking-wider">
                    ENTRY POINTS CHANGED
                  </span>
                  <span
                    className={`text-[9.5px] font-bold ${analysisResult.changed_entry_points.length > 0 ? 'text-[#FF758F]' : 'text-[#34D399]'
                      }`}
                  >
                    {analysisResult.changed_entry_points.length}
                  </span>
                </div>
                {analysisResult.changed_entry_points.length === 0 ? (
                  <p className="text-[11px] text-[#94A3B8] font-sans">No public entry-point files modified.</p>
                ) : (
                  <ul className="space-y-1">
                    {analysisResult.changed_entry_points.map((file, idx) => (
                      <li key={idx} className="text-[11px] text-[#FF758F] truncate flex items-center justify-between">
                        <span className="truncate">{file}</span>
                        <button type="button" onClick={() => openInGraph(file)} className="text-[#94A3B8] hover:text-[#F8FAFC]">
                          <ArrowUpRight className="h-3 w-3" />
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              {/* Core Files */}
              <div
                className="p-3.5 rounded-lg space-y-2"
                style={{
                  background: T.surface,
                  border: `1px solid ${analysisResult.changed_core_files.length > 0 ? 'rgba(252,211,77,0.3)' : T.hairline}`,
                  borderLeft: analysisResult.changed_core_files.length > 0 ? `2px solid #FCD34D` : undefined,
                }}
              >
                <div className="flex items-center justify-between">
                  <span className="text-[10.5px] font-bold text-[#F8FAFC] uppercase tracking-wider">
                    CORE FILES CHANGED
                  </span>
                  <span
                    className={`text-[9.5px] font-bold ${analysisResult.changed_core_files.length > 0 ? 'text-[#FCD34D]' : 'text-[#34D399]'
                      }`}
                  >
                    {analysisResult.changed_core_files.length}
                  </span>
                </div>
                {analysisResult.changed_core_files.length === 0 ? (
                  <p className="text-[11px] text-[#94A3B8] font-sans">No core architectural modules modified.</p>
                ) : (
                  <ul className="space-y-1">
                    {analysisResult.changed_core_files.map((file, idx) => (
                      <li key={idx} className="text-[11px] text-[#FCD34D] truncate flex items-center justify-between">
                        <span className="truncate">{file}</span>
                        <button type="button" onClick={() => openInGraph(file)} className="text-[#94A3B8] hover:text-[#F8FAFC]">
                          <ArrowUpRight className="h-3 w-3" />
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              {/* High Coupling */}
              <div
                className="p-3.5 rounded-lg space-y-2"
                style={{
                  background: T.surface,
                  border: `1px solid ${analysisResult.changed_high_coupling_files.length > 0 ? 'rgba(252,211,77,0.3)' : T.hairline}`,
                  borderLeft: analysisResult.changed_high_coupling_files.length > 0 ? `2px solid #FCD34D` : undefined,
                }}
              >
                <div className="flex items-center justify-between">
                  <span className="text-[10.5px] font-bold text-[#F8FAFC] uppercase tracking-wider">
                    HIGH-COUPLING FILES
                  </span>
                  <span
                    className={`text-[9.5px] font-bold ${analysisResult.changed_high_coupling_files.length > 0 ? 'text-[#FCD34D]' : 'text-[#34D399]'
                      }`}
                  >
                    {analysisResult.changed_high_coupling_files.length}
                  </span>
                </div>
                {analysisResult.changed_high_coupling_files.length === 0 ? (
                  <p className="text-[11px] text-[#94A3B8] font-sans">No high-coupling nodes modified.</p>
                ) : (
                  <ul className="space-y-1">
                    {analysisResult.changed_high_coupling_files.map((file, idx) => (
                      <li key={idx} className="text-[11px] text-[#FCD34D] truncate flex items-center justify-between">
                        <span className="truncate">{file}</span>
                        <button type="button" onClick={() => openInGraph(file)} className="text-[#94A3B8] hover:text-[#F8FAFC]">
                          <ArrowUpRight className="h-3 w-3" />
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>

            {/* Zero Hotspots Restrained Notice */}
            {analysisResult.changed_entry_points.length === 0 &&
              analysisResult.changed_core_files.length === 0 &&
              analysisResult.changed_high_coupling_files.length === 0 && (
                <div
                  className="p-3 rounded-lg flex items-center gap-2.5 text-xs font-mono"
                  style={{ background: T.surface, border: `1px dashed ${T.hairline}` }}
                >
                  <ShieldCheck className="h-4 w-4 text-[#34D399] shrink-0" />
                  <span className="text-[#CBD5E1]">
                    <strong className="text-[#34D399] uppercase font-bold">NO ARCHITECTURAL HOTSPOTS IMPACTED</strong> &mdash; The
                    diff does not modify entry points, high-centrality files, or high-coupling modules.
                  </span>
                </div>
              )}

            {/* Affected Subsystems */}
            {analysisResult.affected_components.length > 0 && (
              <div className="pt-1">
                <span className="text-[10px] font-mono font-bold text-[#94A3B8] uppercase tracking-wider block mb-2">
                  AFFECTED SUBSYSTEMS ({analysisResult.affected_components.length})
                </span>
                <div className="flex items-center gap-2 flex-wrap">
                  {analysisResult.affected_components.map((comp, idx) => (
                    <span
                      key={idx}
                      className="px-2.5 py-1 rounded text-xs font-mono font-semibold uppercase"
                      style={{ background: T.elevated, border: '1px solid rgba(255,255,255,0.07)', color: '#F8FAFC' }}
                    >
                      {comp}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </section>

          {/* ── ZONE 7: AFFECTED FILES REGISTRY (Section 12) ────────────────── */}
          <section
            aria-labelledby="pr-affected-files-heading"
            className="p-4 sm:p-5 rounded-xl space-y-3.5 bg-gradient-to-b from-[#0D1220]/90 to-[#070A12]/95 backdrop-blur-xl"
            style={{ border: `1px solid ${T.hairline}` }}
          >
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 pb-2.5 border-b border-white/[0.055]">
              <div>
                <h3 id="pr-affected-files-heading" className="text-xs font-bold font-mono text-[#F8FAFC] uppercase tracking-wider flex items-center gap-2">
                  <ListChecks className="h-3.5 w-3.5 text-[#818CF8]" />
                  AFFECTED FILES ({filteredFiles.length})
                </h3>
                <p className="text-[10.5px] text-[#CBD5E1] font-sans mt-0.5">
                  Files modified in this PR or affected by downstream dependency propagation.
                </p>
              </div>

              {/* Client-side Search */}
              <div className="relative min-w-[200px] sm:min-w-[240px]">
                <Search className="h-3 w-3 text-[#94A3B8] absolute left-2.5 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  value={fileSearch}
                  onChange={(e) => setFileSearch(e.target.value)}
                  placeholder="Filter affected files..."
                  className="w-full rounded-md pl-8 pr-7 py-1 text-xs font-mono text-[#F8FAFC] placeholder-[#64748B] focus:border-[#818CF8] focus-visible:outline-none transition-colors"
                  style={{ background: T.inputBg, border: `1px solid ${T.inputBorder}` }}
                />
                {fileSearch && (
                  <button
                    type="button"
                    onClick={() => setFileSearch('')}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-[#94A3B8] hover:text-[#F8FAFC]"
                  >
                    <X className="h-3 w-3" />
                  </button>
                )}
              </div>
            </div>

            {/* File Rows List */}
            {filteredFiles.length === 0 ? (
              <div className="p-4 text-center rounded-lg text-xs font-mono text-[#CBD5E1] space-y-1" style={{ border: `1px solid ${T.hairline}`, background: T.surface }}>
                <p>No affected files matching &ldquo;{fileSearch}&rdquo;</p>
                <button type="button" onClick={() => setFileSearch('')} className="text-[#818CF8] hover:underline">
                  Clear filter
                </button>
              </div>
            ) : (
              <div className="space-y-1.5">
                {displayedFiles.map((file, idx) => {
                  const isSelected = selectedFile === file.filename;
                  const isAdded = file.status === 'added';
                  const isDeleted = file.status === 'removed' || file.status === 'deleted';

                  return (
                    <div
                      key={file.filename}
                      onClick={() => selectFile(file.filename)}
                      className={`p-3 rounded-lg transition-all space-y-1.5 text-xs cursor-pointer ${isSelected ? 'border-[#818CF8]/50' : 'hover:border-white/[0.09] hover:bg-[#131A2E]'
                        }`}
                      style={{
                        border: `1px solid ${isSelected ? 'rgba(129,140,248,0.5)' : T.hairline}`,
                        borderLeft: isSelected ? `2px solid ${T.accent}` : undefined,
                        background: isSelected ? T.rowSelected : T.rowNormal,
                        boxShadow: isSelected ? '0 0 14px rgba(129,140,248,0.18)' : undefined,
                      }}
                    >
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1.5">
                        <div className="flex items-center gap-2 min-w-0">
                          <span className="text-[10px] font-mono font-bold text-[#94A3B8] shrink-0">
                            {String(idx + 1).padStart(2, '0')}
                          </span>
                          <span
                            className="px-1.5 py-0.5 rounded text-[9px] font-mono font-bold uppercase shrink-0"
                            style={{
                              color: isAdded ? '#34D399' : isDeleted ? '#FF758F' : '#818CF8',
                              background: isAdded ? 'rgba(52,211,153,0.1)' : isDeleted ? 'rgba(255,117,143,0.1)' : 'rgba(129,140,248,0.1)',
                              border: `1px solid ${isAdded ? 'rgba(52,211,153,0.3)' : isDeleted ? 'rgba(255,117,143,0.3)' : 'rgba(129,140,248,0.3)'}`,
                            }}
                          >
                            {file.status.toUpperCase()}
                          </span>
                          <FilePath
                            path={file.filename}
                            tone="primary"
                            size="sm"
                            active={isSelected}
                            className="min-w-0"
                          />
                          <button
                            type="button"
                            onClick={(e) => handleCopy(e, file.filename)}
                            className="text-[#94A3B8] hover:text-[#F8FAFC] p-0.5 shrink-0 transition-colors"
                            title="Copy path"
                          >
                            {copiedPath === file.filename ? <Check className="h-3 w-3 text-[#34D399]" /> : <Copy className="h-3 w-3" />}
                          </button>
                        </div>

                        <div className="flex items-center gap-2 shrink-0 font-mono text-[10px]">
                          <span className="text-[#34D399] font-bold">+{file.additions}</span>
                          <span className="text-[#94A3B8]">/</span>
                          <span className="text-[#FF758F] font-bold">-{file.deletions}</span>
                          <span className="px-1.5 py-0.5 rounded text-[#34D399]" style={{ background: T.elevated, border: '1px solid rgba(255,255,255,0.07)' }}>
                            VERIFIED
                          </span>
                        </div>
                      </div>

                      <div className="flex items-center justify-between gap-3 text-xs">
                        <div className="text-[11px] text-[#CBD5E1] font-sans leading-relaxed flex-1 truncate">
                          Total {file.changes} line changes across AST body.
                        </div>

                        <div className="flex items-center gap-2.5 font-mono text-[10px] shrink-0">
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              openInGraph(file.filename);
                            }}
                            className="text-[#CBD5E1] hover:text-[#818CF8] flex items-center gap-1 uppercase transition-colors"
                          >
                            <span>VIEW IN GRAPH</span>
                            <ArrowUpRight className="h-3 w-3" />
                          </button>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              openInCallGraph(file.filename);
                            }}
                            className="text-[#CBD5E1] hover:text-[#818CF8] flex items-center gap-1 uppercase transition-colors"
                          >
                            <span>CALL GRAPH</span>
                            <ArrowUpRight className="h-3 w-3" />
                          </button>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              openInChat(`Explain the blast radius of modifying ${file.filename} in PR #${analysisResult.pr_number}`);
                            }}
                            className="text-[#CBD5E1] hover:text-[#818CF8] flex items-center gap-1 uppercase transition-colors"
                          >
                            <span>CHAT</span>
                            <Sparkles className="h-3 w-3 text-[#818CF8]" />
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })}

                {/* Progressive Disclosure Controls */}
                {!isSearchActive && filteredFiles.length > 8 && (
                  <div className="pt-1.5 flex items-center justify-between text-xs font-mono">
                    <span className="text-[#94A3B8]">
                      SHOWING {displayedFiles.length} OF {filteredFiles.length} AFFECTED FILES
                    </span>
                    <div className="flex items-center gap-2">
                      {filesLimit < filteredFiles.length ? (
                        <button
                          type="button"
                          onClick={() => setFilesLimit((prev) => Math.min(prev + 8, filteredFiles.length))}
                          className="px-3 py-1 rounded-md hover:bg-[#131A2E] text-[#F8FAFC] text-xs font-mono transition-colors flex items-center gap-1.5"
                          style={{ background: T.elevated, border: '1px solid rgba(255,255,255,0.07)' }}
                        >
                          <span>
                            SHOW MORE AFFECTED FILES ({displayedFiles.length} &rarr;{' '}
                            {Math.min(filesLimit + 8, filteredFiles.length)})
                          </span>
                          <ChevronDown className="h-3 w-3" />
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={() => setFilesLimit(8)}
                          className="px-3 py-1 rounded-md hover:bg-[#131A2E] text-[#CBD5E1] hover:text-[#F8FAFC] text-xs font-mono transition-colors flex items-center gap-1.5"
                          style={{ background: T.elevated, border: '1px solid rgba(255,255,255,0.07)' }}
                        >
                          <span>COLLAPSE TO 8</span>
                          <ChevronUp className="h-3 w-3" />
                        </button>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}
          </section>

          {/* ── ZONE 8: TEST EXPOSURE (Section 13) ─────────────────────────── */}
          <section
            aria-labelledby="pr-test-exposure-heading"
            className="p-4 sm:p-5 rounded-xl space-y-3.5 bg-gradient-to-b from-[#0D1220]/90 to-[#070A12]/95 backdrop-blur-xl"
            style={{ border: `1px solid ${T.hairline}` }}
          >
            <div className="flex items-center justify-between pb-2.5 border-b border-white/[0.055]">
              <div>
                <h3 id="pr-test-exposure-heading" className="text-xs font-bold font-mono text-[#F8FAFC] uppercase tracking-wider flex items-center gap-2">
                  <TestTube className="h-3.5 w-3.5 text-[#818CF8]" />
                  TEST EXPOSURE
                </h3>
                <p className="text-[10.5px] text-[#CBD5E1] font-sans mt-0.5">
                  Evaluating whether tests were modified alongside application changes.
                </p>
              </div>

              <span
                className="text-[9.5px] font-mono uppercase tracking-wider px-2 py-0.5 rounded font-bold"
                style={{
                  background: testExposure?.hasDirectTests ? 'rgba(52,211,153,0.1)' : 'rgba(252,211,77,0.1)',
                  color: testExposure?.hasDirectTests ? '#34D399' : '#FCD34D',
                  border: `1px solid ${testExposure?.hasDirectTests ? 'rgba(52,211,153,0.3)' : 'rgba(252,211,77,0.3)'}`,
                }}
              >
                {testExposure?.hasDirectTests ? 'TESTS INCLUDED' : 'NO DIRECT TEST UPDATES'}
              </span>
            </div>

            {testExposure?.hasDirectTests ? (
              <div className="space-y-1.5 font-mono text-xs">
                {testExposure.changedTests.map((test, idx) => (
                  <div
                    key={idx}
                    className="p-3 rounded-lg flex items-center justify-between gap-2 hover:bg-[#131A2E] transition-colors"
                    style={{ background: T.surface, border: `1px solid ${T.hairline}` }}
                  >
                    <div className="flex items-center gap-2 truncate">
                      <span className="text-[9px] font-bold text-[#34D399] px-1.5 py-0.5 rounded bg-[#34D399]/10 border border-[#34D399]/30 uppercase">
                        TEST FILE
                      </span>
                      <FilePath path={test.filename} tone="secondary" size="sm" />
                    </div>
                    <div className="flex items-center gap-2 text-[10px] shrink-0">
                      <span className="text-[#34D399]">+{test.additions}</span>
                      <span className="text-[#FF758F]">-{test.deletions}</span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div
                className="p-3.5 rounded-lg flex items-center gap-3 text-xs font-mono"
                style={{ background: T.surface, border: `1px dashed ${T.hairline}` }}
              >
                <ShieldAlert className="h-4 w-4 text-[#FCD34D] shrink-0" />
                <div>
                  <span className="font-mono text-xs font-bold text-[#FCD34D] uppercase block">
                    NO DIRECT TEST IMPACT DETECTED
                  </span>
                  <p className="text-[11px] text-[#CBD5E1] font-sans mt-0.5">
                    No test files were modified in this pull request. If this PR alters behavioral contracts, dedicated regression tests should be added.
                  </p>
                </div>
              </div>
            )}
          </section>

          {/* ── ZONE 9: RISK INTERPRETATION & EPISTEMIC NOTICE (14 & 15) ───── */}
          <section
            aria-labelledby="pr-interpretation-heading"
            className="p-4 sm:p-5 rounded-xl space-y-3.5 bg-gradient-to-b from-[#0D1220]/90 to-[#070A12]/95 backdrop-blur-xl"
            style={{ border: `1px solid ${T.hairline}` }}
          >
            <div className="flex items-center justify-between pb-2.5 border-b border-white/[0.055]">
              <div>
                <h3 id="pr-interpretation-heading" className="text-xs font-bold font-mono text-[#F8FAFC] uppercase tracking-wider flex items-center gap-2">
                  <Cpu className="h-3.5 w-3.5 text-[#818CF8]" />
                  RISK INTERPRETATION & EPISTEMIC NOTICE
                </h3>
                <p className="text-[10.5px] text-[#CBD5E1] font-sans mt-0.5">
                  Forensic reasoning and static analysis boundaries.
                </p>
              </div>
            </div>

            {/* Two-Column Interpretation */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs font-sans">
              <div className="p-3.5 rounded-lg space-y-1.5" style={{ background: T.surface, border: `1px solid ${T.hairline}` }}>
                <span className="text-[9.5px] font-mono font-bold text-[#818CF8] uppercase tracking-wider block">
                  WHY THIS RISK LEVEL
                </span>
                <p className="text-[#CBD5E1] leading-relaxed text-[11.5px]">
                  {analysisResult.risk_score <= 25
                    ? `The indexed dependency graph shows bounded downstream propagation (${analysisResult.impact_radius} reachable files at max depth ${analysisResult.max_depth}) and no critical entry point or core architecture violations.`
                    : analysisResult.risk_score <= 50
                      ? `Moderate change surface touching ${analysisResult.changed_files.length} files across ${analysisResult.affected_components.length} subsystem(s). Transitive ripple reaches ${analysisResult.impact_radius} downstream files.`
                      : `Elevated risk driven by ${analysisResult.top_risks.slice(0, 2).join(' and ') || 'broad change surface'}. High-coupling or core architectural components reside directly in the blast path.`}
                </p>
              </div>

              <div className="p-3.5 rounded-lg space-y-1.5" style={{ background: T.surface, border: `1px solid ${T.hairline}` }}>
                <span className="text-[9.5px] font-mono font-bold text-[#818CF8] uppercase tracking-wider block">
                  WHAT THIS MEANS
                </span>
                <p className="text-[#CBD5E1] leading-relaxed text-[11.5px]">
                  {analysisResult.risk_score <= 25
                    ? 'Standard peer review and automated CI validation are sufficient for this change.'
                    : analysisResult.risk_score <= 50
                      ? 'Verify interface contracts with downstream consumers before merge. Validate that test suites cover updated edge cases.'
                      : 'Requires senior architectural sign-off and staged deployment to isolate possible runtime regression.'}
                </p>
              </div>
            </div>

            {/* Epistemic Notice Banner (Section 15) */}
            <div
              className="p-3 rounded-lg space-y-1 text-xs font-mono"
              style={{ background: 'rgba(129,140,248,0.06)', border: '1px solid rgba(129,140,248,0.2)' }}
            >
              <div className="flex items-center gap-2 text-[#818CF8] font-bold uppercase text-[10px]">
                <HelpCircle className="h-3.5 w-3.5 shrink-0" />
                <span>STATIC ANALYSIS &ne; COMPLETE RUNTIME RISK</span>
              </div>
              <p className="text-[10.5px] text-[#CBD5E1] font-sans leading-relaxed">
                Static AST analysis cannot fully establish dynamic imports, reflection, runtime registration, external consumer contracts, or feature-flag branches. Treat this analysis as a structural baseline.
              </p>
            </div>
          </section>

          {/* ── ZONE 10: ENGINEERING VERDICT (Section 16) ───────────────────── */}
          {engineeringVerdict && (
            <section
              aria-labelledby="pr-verdict-heading"
              className="p-4 sm:p-5 rounded-xl space-y-3.5 bg-gradient-to-b from-[#0D1220]/90 to-[#070A12]/95 backdrop-blur-xl"
              style={{ border: `1px solid ${T.hairline}` }}
            >
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 pb-2.5 border-b border-white/[0.055]">
                <div>
                  <span className="text-[9.5px] font-mono font-bold text-[#818CF8] uppercase tracking-widest block">
                    DECISION LAYER
                  </span>
                  <h3 id="pr-verdict-heading" className="font-mono text-sm font-bold text-[#F8FAFC] mt-0.5">
                    ENGINEERING VERDICT
                  </h3>
                </div>

                <span
                  className="px-2.5 py-0.5 rounded text-xs font-mono font-bold uppercase"
                  style={{
                    color: engineeringVerdict.tone,
                    background: `${engineeringVerdict.tone}15`,
                    border: `1px solid ${engineeringVerdict.tone}35`,
                  }}
                >
                  {engineeringVerdict.status}
                </span>
              </div>

              {/* Compact Evidence Row */}
              <div className="flex items-center gap-2 flex-wrap text-[10.5px] font-mono text-[#CBD5E1]">
                <span className="text-[#F8FAFC] font-bold">
                  {analysisResult.risk_score} / 100 ({analysisResult.risk_level} RISK)
                </span>
                <span className="text-[#94A3B8]">&middot;</span>
                <span className="text-[#818CF8] font-bold">{analysisResult.changed_files.length} FILES CHANGED</span>
                <span className="text-[#94A3B8]">&middot;</span>
                <span className="text-[#FCD34D] font-bold">{analysisResult.impact_radius} DOWNSTREAM REACH</span>
                <span className="text-[#94A3B8]">&middot;</span>
                <span className={testExposure?.hasDirectTests ? 'text-[#34D399] font-bold' : 'text-[#94A3B8]'}>
                  {testExposure?.hasDirectTests ? 'TESTS COVERED' : 'NO DIRECT TESTS'}
                </span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-1 text-xs font-mono">
                <div className="p-3 rounded-lg space-y-1" style={{ background: T.surface, border: `1px solid ${T.hairline}` }}>
                  <span className="text-[9px] font-bold text-[#94A3B8] uppercase block">WHY</span>
                  <p className="text-[11px] text-[#CBD5E1] font-sans leading-relaxed">{engineeringVerdict.why}</p>
                </div>
                <div className="p-3 rounded-lg space-y-1" style={{ background: T.surface, border: `1px solid ${T.hairline}` }}>
                  <span className="text-[9px] font-bold text-[#94A3B8] uppercase block">WHAT TO REVIEW</span>
                  <p className="text-[11px] text-[#CBD5E1] font-sans leading-relaxed">{engineeringVerdict.reviewFocus}</p>
                </div>
                <div className="p-3 rounded-lg space-y-1" style={{ background: T.surface, border: `1px solid ${T.hairline}` }}>
                  <span className="text-[9px] font-bold text-[#94A3B8] uppercase block">NEXT ACTION</span>
                  <p className="text-[11px] text-[#CBD5E1] font-sans leading-relaxed">{engineeringVerdict.nextAction}</p>
                </div>
              </div>
            </section>
          )}

          {/* ── ZONE 11: PERSISTENT ACTION BAR (Section 17) ─────────────────── */}
          <div
            className="p-3 rounded-xl flex flex-col sm:flex-row sm:items-center justify-between gap-2.5"
            style={{
              borderTop: '1px solid rgba(255,255,255,0.06)',
              background: 'rgba(7,8,11,0.94)',
              backdropFilter: 'blur(14px)',
              border: `1px solid ${T.hairline}`,
            }}
          >
            <div className="flex items-center gap-2 flex-wrap font-mono text-xs">
              {selectedFile && (
                <div className="px-2 py-1 rounded text-[10.5px] font-mono text-[#CBD5E1] flex items-center gap-1.5 border border-white/[0.07] bg-[#050609] max-w-[220px] sm:max-w-xs truncate">
                  <span className="text-[9px] uppercase text-[#818CF8] font-bold shrink-0">SELECTED:</span>
                  <span className="truncate text-[#F8FAFC]">{selectedFile}</span>
                </div>
              )}
              <button
                type="button"
                onClick={openInImpact}
                className="px-3 py-1.5 rounded-md bg-[#818CF8] hover:bg-[#A5B4FC] active:bg-[#6366F1] border border-white/10 text-white text-xs font-bold font-mono transition-colors shadow-[0_0_16px_rgba(129,140,248,0.2)] flex items-center gap-1.5"
              >
                <span>VIEW IMPACT ANALYSIS</span>
                <ArrowRight className="h-3 w-3" />
              </button>
              <button
                type="button"
                onClick={() => openInGraph(selectedFile || undefined)}
                className="px-3 py-1.5 rounded-md hover:bg-[#131A2E] text-[#CBD5E1] hover:text-[#F8FAFC] flex items-center gap-1 transition-colors"
                style={{ background: T.elevated, border: '1px solid rgba(255,255,255,0.07)' }}
              >
                <span>FILE GRAPH</span>
                <ArrowUpRight className="h-3 w-3" />
              </button>
              <button
                type="button"
                onClick={() => openInCallGraph(selectedFile || undefined)}
                className="px-3 py-1.5 rounded-md hover:bg-[#131A2E] text-[#CBD5E1] hover:text-[#F8FAFC] flex items-center gap-1 transition-colors"
                style={{ background: T.elevated, border: '1px solid rgba(255,255,255,0.07)' }}
              >
                <span>CALL GRAPH</span>
                <ArrowUpRight className="h-3 w-3" />
              </button>
              <button
                type="button"
                onClick={() => openInChat(selectedFile ? `Assess risk of modifying ${selectedFile} in PR #${analysisResult.pr_number}` : undefined)}
                className="px-3 py-1.5 rounded-md hover:bg-[#131A2E] text-[#CBD5E1] hover:text-[#F8FAFC] flex items-center gap-1 transition-colors"
                style={{ background: T.elevated, border: '1px solid rgba(255,255,255,0.07)' }}
              >
                <span>OPEN IN CHAT</span>
                <Sparkles className="h-3 w-3 text-[#818CF8]" />
              </button>
              <button
                type="button"
                onClick={() => handleSubmit()}
                className="px-3 py-1.5 rounded-md hover:bg-[#131A2E] text-[#CBD5E1] hover:text-[#F8FAFC] flex items-center gap-1 transition-colors"
                style={{ background: T.elevated, border: '1px solid rgba(255,255,255,0.07)' }}
              >
                <RefreshCw className="h-3 w-3" />
                <span>RE-ANALYZE</span>
              </button>
              <button
                type="button"
                onClick={resetToNewPR}
                className="px-3 py-1.5 rounded-md hover:bg-[#131A2E] text-[#CBD5E1] hover:text-[#F8FAFC] flex items-center gap-1 transition-colors"
                style={{ background: T.elevated, border: '1px solid rgba(255,255,255,0.07)' }}
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

export default PRIntelligence;

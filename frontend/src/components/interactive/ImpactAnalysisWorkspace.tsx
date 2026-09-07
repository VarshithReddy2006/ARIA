/**
 * ImpactAnalysisWorkspace — ARIA Predictive Impact Analysis & Change Intelligence
 *
 * Final 10/10 Production-Grade Engineering Investigation Console
 *
 * Core narrative:
 * PROPOSED CHANGE
 * → RESOLUTION
 * → DIRECT IMPACT
 * → DOWNSTREAM CASCADE
 * → COMPONENTS
 * → CALLERS / DEPENDENCIES
 * → TEST IMPACT
 * → RISK
 * → RECOMMENDED ACTION
 *
 * Visual System:
 * - Canvas: #020204 | Surface: #07090C | Elevated: rgba(16,18,23,0.74) | Higher: rgba(20,23,29,0.82)
 * - Hairline: rgba(255,255,255,0.06) / #1A1A1E | Strong Border: rgba(255,255,255,0.10)
 * - Primary Text: #F3F4F6 | Secondary: #A5AAB4 | Muted: #6F7681
 * - Impact Accent (ARIA Blue): #7C83FF (Hover: #9AA0FF, Active: #636BEF, Soft: rgba(124,131,255,0.12), Border: #7C83FF)
 * - Verified: #35D6A3 | Attention: #F0B429 | High Risk: #F27781 | Critical: #FF5C69 | Unknown: #727A86
 */

import React, { useState, useEffect, useRef, useMemo, useCallback, lazy, Suspense } from 'react';
import { apiUrl, extractErrorMessage } from '../../lib/api';
import {
  AlertTriangle, ArrowRight, Loader2, Zap, ShieldCheck, ShieldAlert,
  Copy, Check, Sparkles, Network, Layers, FileCode,
  SlidersHorizontal, Terminal, ArrowUpRight, ListChecks,
  CheckCircle2, Circle, GitBranch, ChevronDown, ChevronUp,
  FolderGit2, CornerDownRight, CheckSquare, Square, Plus,
  GitCompare, Search, RefreshCw, X, Target, TestTube, AlertCircle,
  Activity, ArrowDown, HelpCircle, Compass
} from 'lucide-react';
import { FilePath } from '../ui/FilePath';

// Lazy-load the ReactFlow propagation visualizer
const ImpactAnalysisGraph = lazy(() => import('./ImpactAnalysisGraph'));

// ── Design Tokens ───────────────────────────────────────────────────────────

const T = {
  canvas: '#050608',
  surface: '#0A0D14',
  glassCard: 'rgba(13, 18, 32, 0.90)',
  glassSurface: 'rgba(13, 18, 32, 0.90)',
  glassHover: 'rgba(19, 26, 46, 0.92)',
  glassActive: 'rgba(25, 34, 60, 0.96)',
  elevated: '#0D1220',
  strongElevated: '#131A2E',
  inputBg: '#07090E',
  inputBorder: 'rgba(255, 255, 255, 0.10)',
  inputFocus: '#818CF8',
  placeholder: '#64748B',
  inspectorBg: '#0A0D14',
  innerBlock: '#07090E',
  rowNormal: '#0A0D14',
  rowHover: '#0D1220',
  rowSelected: '#131A2E',
  graphBg: '#050608',
  actionBarBg: 'rgba(13, 18, 32, 0.94)',
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
  accentGlass: 'rgba(129, 140, 248, 0.12)',
  accentBorder: 'rgba(129, 140, 248, 0.35)',
  verified: '#34D399',
  attention: '#FCD34D',
  risk: '#FF758F',
  critical: '#FF4D6D',
  cyan: '#38BDF8',
  unknown: '#94A3B8',
} as const;

// ── Types ───────────────────────────────────────────────────────────────────

export interface DependencyPath {
  path: string[];
}

// Impact-analysis contract types live in one place so this workspace and
// ImpactAnalysisGraph cannot drift apart. See frontend/src/lib/impactTypes.ts.
import type {
  ApiExposureInfo,
  CallerInfo,
  EvidenceItem,
  ImpactAnalysisData,
  ImpactedFileDetail,
  TestImpactItem,
} from '../../lib/impactTypes';

export type {
  ApiExposureInfo,
  CallerInfo,
  EvidenceItem,
  ImpactAnalysisData,
  ImpactedFileDetail,
  TestImpactItem,
};

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

function relativeTime(iso?: string | number | null): string {
  if (!iso) return 'just now';
  try {
    const timeMs = typeof iso === 'number' ? iso : new Date(iso).getTime();
    const diff = Math.round((Date.now() - timeMs) / 60000);
    if (diff < 1) return 'just now';
    if (diff < 60) return `${diff} min ago`;
    return `${Math.round(diff / 60)}h ago`;
  } catch {
    return 'just now';
  }
}

// ── Preset Scenarios ────────────────────────────────────────────────────────

const PRESET_SCENARIOS = [
  'Add GitHub OAuth Login',
  'Fix SQLite Timeout Issue',
  'Refactor Duplicate HTML Templates',
];

// ── Main Component ──────────────────────────────────────────────────────────

export const ImpactAnalysisWorkspace: React.FC<Props> = ({ repoName }) => {
  const [activeRepo, setActiveRepo] = useState(() => resolveRepo(repoName));
  const [scenarioInput, setScenarioInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [impactData, setImpactData] = useState<ImpactAnalysisData | null>(null);
  const [errorMsg, setErrorMsg] = useState('');
  const [isCommandExpanded, setIsCommandExpanded] = useState(true);
  const [analyzedTimestamp, setAnalyzedTimestamp] = useState<number | null>(null);

  // Progressive disclosure & search for affected files
  const [filesLimit, setFilesLimit] = useState(8);
  const [fileSearch, setFileSearch] = useState('');
  const [copiedPath, setCopiedPath] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const resultsRef = useRef<HTMLDivElement>(null);

  // Sync activeRepo with repoName prop changes and clear stale results
  useEffect(() => {
    const nextRepo = resolveRepo(repoName);
    if (nextRepo !== activeRepo) {
      setActiveRepo(nextRepo);
      setImpactData(null);
      setSelectedFile(null);
      setErrorMsg('');
      setIsCommandExpanded(true);
      setFilesLimit(8);
      setFileSearch('');
    }
  }, [repoName]);

  // Sync global active-repo events
  useEffect(() => {
    const handleRepoChanged = (e: Event) => {
      const customEvent = e as CustomEvent<string>;
      if (customEvent.detail && customEvent.detail !== activeRepo) {
        setActiveRepo(customEvent.detail);
        setImpactData(null);
        setSelectedFile(null);
        setErrorMsg('');
        setIsCommandExpanded(true);
      }
    };
    const handleRepoCleared = () => {
      setActiveRepo('');
      setImpactData(null);
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

  // Handle incoming aria-open-impact events from other tabs (Graph, Chat, Architecture Drift)
  useEffect(() => {
    const handleOpenImpact = (e: Event) => {
      const customEvent = e as CustomEvent<{ file?: string; query?: string; repo?: string }>;
      if (customEvent.detail) {
        if (customEvent.detail.repo && customEvent.detail.repo !== activeRepo) {
          setActiveRepo(customEvent.detail.repo);
        }
        const text = customEvent.detail.query || (customEvent.detail.file ? `Refactor and assess downstream impact of ${customEvent.detail.file}` : '');
        if (text) {
          setScenarioInput(text);
          setIsCommandExpanded(true);
          setTimeout(() => textareaRef.current?.focus(), 50);
        }
      }
    };
    window.addEventListener('aria-open-impact', handleOpenImpact);
    return () => window.removeEventListener('aria-open-impact', handleOpenImpact);
  }, [activeRepo]);

  // Keyboard shortcut: '/' focuses scenario input, Escape blurs focus
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (
        e.key === '/' &&
        document.activeElement !== textareaRef.current &&
        !(document.activeElement instanceof HTMLInputElement || document.activeElement instanceof HTMLTextAreaElement)
      ) {
        e.preventDefault();
        setIsCommandExpanded(true);
        setTimeout(() => textareaRef.current?.focus(), 50);
      } else if (e.key === 'Escape') {
        if (document.activeElement instanceof HTMLElement) {
          document.activeElement.blur();
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Validation
  const canSubmit = !isLoading && scenarioInput.trim().length > 0;

  // Submit analysis
  const handleSubmit = async (overrideQuery?: string) => {
    const query = overrideQuery !== undefined ? overrideQuery : scenarioInput;
    if (!query.trim() || isLoading) return;

    if (overrideQuery !== undefined) {
      setScenarioInput(overrideQuery);
    }

    setIsLoading(true);
    setErrorMsg('');
    setImpactData(null);

    const targetRepo = activeRepo || resolveRepo();
    if (!targetRepo) {
      setErrorMsg('No repository selected. Please select a repository from the navbar.');
      setIsLoading(false);
      return;
    }

    try {
      const res = await fetch(apiUrl('/api/v1/impact-analysis'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          repo: targetRepo,
          issue: query.trim(),
        }),
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(extractErrorMessage(errorData) || 'Failed to calculate change impact analysis.');
      }

      const data: ImpactAnalysisData = await res.json();
      setImpactData(data);
      setAnalyzedTimestamp(Date.now());
      setIsCommandExpanded(false); // Compress input so evidence dominates!
      setFilesLimit(8);
      setTimeout(() => {
        resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }, 150);
    } catch (err: any) {
      setErrorMsg(extractErrorMessage(err) || 'Network error encountered during impact analysis.');
    } finally {
      setIsLoading(false);
    }
  };

  // Ctrl+Enter handler
  const handleKeyDownInput = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      handleSubmit();
    }
  };

  // Reset helper for "New Scenario"
  const resetToNewScenario = useCallback(() => {
    setScenarioInput('');
    setImpactData(null);
    setSelectedFile(null);
    setErrorMsg('');
    setIsCommandExpanded(true);
    setFilesLimit(8);
    setFileSearch('');
    setTimeout(() => textareaRef.current?.focus(), 50);
  }, []);

  // File selection helper with event synchronization.
  //
  // Uses the shared 'aria-workspace-file-select' contract (payload `{ path }`,
  // consumed by AnalysisDashboard) rather than the panel-private
  // 'aria-impact-file-selected', which had no listener anywhere — so selecting a
  // file here never synchronised the workspace explorer the way the file graph does.
  const selectFile = useCallback((filePath: string) => {
    setSelectedFile(filePath);
    window.dispatchEvent(
      new CustomEvent('aria-workspace-file-select', {
        detail: { path: filePath },
      })
    );
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
    const targetFile = file || selectedFile || impactData?.directly_affected_files?.[0] || '';
    const [owner, repo] = (activeRepo || '').split('/');
    window.dispatchEvent(
      new CustomEvent('aria-open-graph', {
        detail: {
          owner: owner || undefined,
          repo: repo || undefined,
          file: targetFile,
          path: targetFile,
          source: 'impact_analysis',
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
    const targetFile = file || selectedFile || impactData?.directly_affected_files?.[0] || '';
    window.dispatchEvent(
      new CustomEvent('aria-navigate-tab', {
        detail: { tab: 'call_graph', file: targetFile },
      })
    );
  };

  // Cross-Surface Navigation: ARIA Chat
  const openInChat = (customPrompt?: string) => {
    if (!impactData) return;
    const [owner, repo] = (activeRepo || '').split('/');
    const prompt =
      customPrompt ||
      `Explain the architectural and functional blast radius of this proposed change in ${activeRepo}:
"${impactData.issue_text}"

Blast Radius: ${impactData.blast_radius_category || 'UNKNOWN'} (${impactData.risk_level.toUpperCase()} RISK)
Confidence: ${impactData.confidence}%
Directly Affected Files (${impactData.directly_affected_files.length}):
${impactData.directly_affected_files.slice(0, 5).map(f => `- ${f}`).join('\n')}

Downstream Cascade (${impactData.indirectly_affected_files.length} files):
${impactData.indirectly_affected_files.slice(0, 5).map(f => `- ${f}`).join('\n')}

What precautions, testing strategy, or refactoring steps should be taken?`;

    window.dispatchEvent(
      new CustomEvent('aria-open-chat', {
        detail: {
          prompt,
          owner,
          repo,
          source: 'impact_analysis',
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

  // ── Derived Data Computations ──────────────────────────────────────────────

  // All affected files unified list
  const allAffectedFiles = useMemo(() => {
    if (!impactData) return [];
    const directSet = new Set(impactData.directly_affected_files || []);
    const indirectSet = new Set(impactData.indirectly_affected_files || []);

    const files: Array<{
      path: string;
      isDirect: boolean;
      confidenceScore: number;
      confidenceTier: 'HIGH' | 'MEDIUM' | 'LOW';
      reason: string;
      evidenceStrength?: string;
    }> = [];

    // Details lookup map
    const detailsMap = new Map<string, ImpactedFileDetail>();
    (impactData.impacted_file_details || []).forEach(d => detailsMap.set(d.file_path, d));

    directSet.forEach(path => {
      const detail = detailsMap.get(path);
      files.push({
        path,
        isDirect: true,
        confidenceScore: detail?.confidence_score ?? 0.95,
        confidenceTier: detail?.confidence_tier ?? 'HIGH',
        reason: detail?.reason || 'Directly matches or implements proposed change targets',
        evidenceStrength: detail?.evidence_strength || 'LEVEL_1_EXACT_SYMBOL',
      });
    });

    indirectSet.forEach(path => {
      if (!directSet.has(path)) {
        const detail = detailsMap.get(path);
        files.push({
          path,
          isDirect: false,
          confidenceScore: detail?.confidence_score ?? 0.70,
          confidenceTier: detail?.confidence_tier ?? 'MEDIUM',
          reason: detail?.reason || 'Reachable via downstream import or caller chain',
          evidenceStrength: detail?.evidence_strength || 'LEVEL_6_MODULE_DEPENDENCY',
        });
      }
    });

    return files;
  }, [impactData]);

  // Filtered files derived list
  const filteredFiles = useMemo(() => {
    if (!fileSearch.trim()) return allAffectedFiles;
    const q = fileSearch.toLowerCase();
    return allAffectedFiles.filter(f =>
      f.path.toLowerCase().includes(q) ||
      (f.isDirect ? 'direct target' : 'downstream cascade').includes(q) ||
      f.reason.toLowerCase().includes(q) ||
      f.confidenceTier.toLowerCase().includes(q)
    );
  }, [allAffectedFiles, fileSearch]);

  const isSearchActive = Boolean(fileSearch.trim());
  const displayedFiles = useMemo(() => {
    if (isSearchActive) return filteredFiles;
    return filteredFiles.slice(0, filesLimit);
  }, [filteredFiles, isSearchActive, filesLimit]);

  // Synchronize file selection when search filter changes or data updates
  useEffect(() => {
    if (selectedFile && filteredFiles.length > 0) {
      const exists = filteredFiles.some(f => f.path === selectedFile);
      if (!exists) {
        setSelectedFile(filteredFiles[0]?.path || null);
      }
    } else if (!selectedFile && filteredFiles.length > 0) {
      setSelectedFile(filteredFiles[0]?.path || null);
    } else if (filteredFiles.length === 0) {
      setSelectedFile(null);
    }
  }, [filteredFiles, selectedFile]);

  // Blast radius interpretation
  const blastRadiusInfo = useMemo(() => {
    if (!impactData) return null;
    const totalFiles = impactData.estimated_file_count || allAffectedFiles.length;
    const category = impactData.blast_radius_category || (
      totalFiles <= 2 ? 'XS' : totalFiles <= 5 ? 'S' : totalFiles <= 12 ? 'M' : totalFiles <= 25 ? 'L' : 'XL'
    );
    const risk = (impactData.risk_level || 'low').toLowerCase();

    let label = 'CONTAINED BLAST RADIUS';
    // Explicit `string`: `T.*` are literal-typed const tokens, so inference
    // would pin this to T.verified's literal and reject the reassignments below.
    let toneColor: string = T.verified;
    let badge = `${category} · LOW RISK`;

    if (risk === 'extreme' || category === 'XL' || totalFiles > 25) {
      label = 'EXTREME BLAST RADIUS';
      toneColor = T.critical;
      badge = `${category} · CRITICAL RISK`;
    } else if (risk === 'high' || category === 'L' || totalFiles > 12) {
      label = 'HIGH BLAST RADIUS';
      toneColor = T.risk;
      badge = `${category} · HIGH RISK`;
    } else if (risk === 'medium' || category === 'M' || totalFiles > 5) {
      label = 'MODERATE BLAST RADIUS';
      toneColor = T.attention;
      badge = `${category} · MODERATE RISK`;
    }

    return { category, risk, label, toneColor, badge, totalFiles };
  }, [impactData, allAffectedFiles]);

  // Compact semantic relationships for executive brief
  const blastRadiusSemantic = useMemo(() => {
    if (!blastRadiusInfo) return 'UNKNOWN';
    const { category, risk } = blastRadiusInfo;
    if (risk === 'extreme' || category === 'XL') return `${category} · HIGH CHANGE SURFACE`;
    if (risk === 'high' || category === 'L') return `${category} · ELEVATED CHANGE SURFACE`;
    if (risk === 'medium' || category === 'M') return `${category} · MODERATE CHANGE SURFACE`;
    return `${category} · LOCALIZED CHANGE SURFACE`;
  }, [blastRadiusInfo]);

  const confidenceSemantic = useMemo(() => {
    if (!impactData) return 'UNKNOWN';
    const c = impactData.confidence;
    if (c >= 85) return `${c}% · STRONG EVIDENCE`;
    if (c >= 65) return `${c}% · MODERATE EVIDENCE`;
    return `${c}% · PRELIMINARY EVIDENCE`;
  }, [impactData]);

  // Recommended Action derived computation
  const recommendedAction = useMemo(() => {
    if (!impactData || !blastRadiusInfo) return null;
    const { risk, totalFiles } = blastRadiusInfo;
    const hasTests = (impactData.affected_tests?.length ?? 0) > 0;

    if (risk === 'extreme' || totalFiles > 25) {
      return {
        title: 'DECOMPOSE CHANGE',
        tone: T.critical,
        description: 'The change impacts extensive repository subsystems and deep transitive chains. Split the change into staged micro-PRs to isolate risk.',
        actionLabel: 'Review Subsystems in Graph',
      };
    } else if (risk === 'high' || totalFiles > 12) {
      return {
        title: 'HIGH IMPACT — STAGE CHANGE',
        tone: T.risk,
        description: 'Broad ripple effect across core modules. Review downstream consumers and run targeted integration tests before staging.',
        actionLabel: 'Inspect Downstream Callers',
      };
    } else if (risk === 'medium' || totalFiles > 5) {
      return {
        title: 'REVIEW DOWNSTREAM CONSUMERS',
        tone: T.attention,
        description: 'Moderate cascade confined to related packages. Verify public interface contracts and validate caller test coverage.',
        actionLabel: 'Check Affected Tests',
      };
    } else if (!hasTests && impactData.confidence < 60) {
      return {
        title: 'ADDITIONAL EVIDENCE REQUIRED',
        tone: T.unknown,
        description: 'Limited static caller evidence or unknown test relationship. Manually inspect dynamic usage before modifications.',
        actionLabel: 'Ask in Chat',
      };
    } else {
      return {
        title: 'SAFE TO PROCEED',
        tone: T.verified,
        description: 'Impact is localized to direct targets with minimal downstream propagation. Standard code review and test execution recommended.',
        actionLabel: 'View Implementation Order',
      };
    }
  }, [impactData, blastRadiusInfo]);

  return (
    <div className="flex flex-col text-[#F8FAFC] min-w-0 space-y-5 font-sans">
      {/* ── ZONE A: HEADER ────────────────────────────────────────────────── */}
      <header className="min-w-0 pb-4" style={{ borderBottom: `1px solid ${T.hairline}` }}>
        <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-3">
          <div className="min-w-0 max-w-2xl space-y-1.5">
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-bold text-[#818CF8] uppercase tracking-widest font-mono">
                IMPACT ANALYSIS / CHANGE INTELLIGENCE
              </span>
              <span className="h-1 w-1 rounded-full bg-white/20" />
              <span className="text-[9.5px] font-mono text-[#64748B] uppercase tracking-wider flex items-center gap-1.5">
                <span className="h-1.5 w-1.5 rounded-full bg-[#34D399] shadow-[0_0_8px_rgba(52,211,153,0.5)]" />
                INDEXED BASELINE: READY
              </span>
            </div>
            <h2 className="text-lg sm:text-xl font-bold text-[#F8FAFC] tracking-tight font-mono leading-tight">
              WHAT IS AFFECTED BY THIS CHANGE?
            </h2>
            <p className="text-xs text-[#CBD5E1] leading-relaxed max-w-xl font-sans">
              Describe a proposed modification, refactor, bug fix, feature, or architectural change to estimate its repository blast radius.
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

      {/* ── ZONE B: SCENARIO COMMAND CENTER ───────────────────────────────── */}
      <div className="rounded-xl border shadow-xl overflow-hidden transition-all bg-gradient-to-b from-[#0D1220]/90 to-[#070A12]/95 backdrop-blur-xl border-white/[0.08]">
        {/* Header bar */}
        <div className="px-3.5 py-2.5 sm:px-4 sm:py-3 flex items-center justify-between border-b border-white/[0.08] bg-white/[0.02]">
          <div className="flex items-center gap-2.5 min-w-0">
            <Terminal className="h-3.5 w-3.5 text-[#818CF8] shrink-0" />
            <span className="text-[10px] font-mono font-bold text-[#818CF8] uppercase tracking-widest shrink-0">
              CHANGE SCENARIO COMMAND CENTER
            </span>
            {impactData && !isCommandExpanded && (
              <span className="text-[11px] font-mono text-[#CBD5E1] max-w-xs sm:max-w-md truncate ml-2">
                &ldquo;{impactData.issue_text}&rdquo; &middot; ANALYZED {relativeTime(analyzedTimestamp).toUpperCase()}
              </span>
            )}
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <span className="text-[10px] font-mono text-[#64748B] hidden xl:inline">
              Press <kbd className="px-1.5 py-0.5 rounded text-[#CBD5E1] bg-[#07090E] border border-white/10">/</kbd> to focus &middot; <kbd className="px-1.5 py-0.5 rounded text-[#CBD5E1] bg-[#07090E] border border-white/10">Ctrl+Enter</kbd> to run
            </span>

            {impactData && (
              <>
                <button
                  type="button"
                  onClick={resetToNewScenario}
                  className="px-2.5 py-1 rounded bg-[#0D1220] border border-white/[0.08] hover:border-white/20 text-[10.5px] font-mono text-[#CBD5E1] hover:text-[#F8FAFC] flex items-center gap-1.5 transition-colors"
                  title="Clear inputs and start a new scenario"
                >
                  <Plus className="h-3 w-3" />
                  <span className="hidden sm:inline">NEW SCENARIO</span>
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
            <div className="space-y-1.5">
              <label htmlFor="impact-scenario-input" className="text-[10px] font-mono font-bold text-[#64748B] uppercase tracking-wider block">
                DESCRIBE THE PROPOSED CHANGE
              </label>
              <textarea
                ref={textareaRef}
                id="impact-scenario-input"
                rows={2}
                value={scenarioInput}
                onChange={(e) => setScenarioInput(e.target.value)}
                onKeyDown={handleKeyDownInput}
                placeholder="e.g., Add GitHub OAuth Login, or Fix SQLite Timeout Issue, or Refactor Duplicate HTML Templates"
                className="w-full rounded-lg px-3 py-2 text-xs text-[#F8FAFC] placeholder-[#64748B] font-mono bg-[#07090E] border border-white/[0.10] focus:border-[#818CF8] focus:ring-1 focus:ring-[#818CF8]/40 focus-visible:outline-none transition-all resize-none leading-relaxed"
              />
            </div>

            {/* Presets & Submit button bar */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-0.5">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[10px] font-mono font-bold text-[#64748B] uppercase tracking-wider shrink-0">
                  QUICK SCENARIOS:
                </span>
                {PRESET_SCENARIOS.map((preset) => (
                  <button
                    key={preset}
                    type="button"
                    onClick={() => {
                      setScenarioInput(preset);
                      textareaRef.current?.focus();
                    }}
                    className="px-2.5 py-1 rounded text-[10.5px] font-mono text-[#CBD5E1] hover:text-[#F8FAFC] hover:border-[#818CF8]/50 hover:bg-[#131A2E] transition-colors bg-[#0D1220] border border-white/[0.08]"
                  >
                    {preset}
                  </button>
                ))}
              </div>

              <button
                type="button"
                onClick={() => handleSubmit()}
                disabled={!canSubmit || isLoading}
                className="px-5 py-2 rounded-lg bg-[#818CF8] hover:bg-[#A5B4FC] active:bg-[#6366F1] border border-white/10 text-white text-xs font-bold font-mono transition-all shadow-[0_0_16px_rgba(129,140,248,0.25)] flex items-center justify-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed shrink-0"
              >
                {isLoading ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
                    <span>CALCULATING IMPACT…</span>
                  </>
                ) : (
                  <>
                    <span>RUN IMPACT ANALYSIS</span>
                    <ArrowRight className="h-3.5 w-3.5" />
                  </>
                )}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* ── ZONE C: EMPTY-STATE PREVIEW (IMPACT PIPELINE) ─────────────────── */}
      {!impactData && !isLoading && !errorMsg && (
        <div className="space-y-4">
          <div className="p-4 sm:p-5 rounded-xl space-y-3 bg-gradient-to-b from-[#0D1220]/90 to-[#070A12]/95 backdrop-blur-xl border border-white/[0.08]">
            <div className="flex items-center justify-between pb-2 border-b border-white/[0.08]">
              <span className="text-[10px] font-mono font-bold text-[#818CF8] uppercase tracking-widest block">
                IMPACT PIPELINE
              </span>
              <span className="text-[10px] font-mono text-[#64748B] uppercase tracking-wider">
                7 FORENSIC STAGES
              </span>
            </div>

            <p className="text-xs text-[#CBD5E1] font-sans leading-relaxed">
              When an impact query is submitted, ARIA executes deterministic symbol resolution, call graph BFS, and import traversal to map the repository blast radius:
            </p>

            <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2 pt-1 font-mono text-xs">
              {[
                { step: '01', title: 'CHANGE', desc: 'Intent & Token Extraction' },
                { step: '02', title: 'TARGET SYMBOLS', desc: 'Exact Symbol Index Query' },
                { step: '03', title: 'AFFECTED FILES', desc: 'Direct File AST Matching' },
                { step: '04', title: 'DOWNSTREAM', desc: 'Transitive Import Chains' },
                { step: '05', title: 'COMPONENTS', desc: 'Subsystem Boundaries' },
                { step: '06', title: 'TEST IMPACT', desc: 'Test Callers & Suites' },
                { step: '07', title: 'RISK', desc: 'Blast Radius Decision' },
              ].map((p, idx) => (
                <div
                  key={idx}
                  className="p-2.5 rounded-lg space-y-1 bg-[#0A0D14] border border-white/[0.08]"
                >
                  <span className="text-[9.5px] font-mono font-bold text-[#818CF8] block">
                    {p.step} {p.title}
                  </span>
                  <span className="text-[10px] text-[#64748B] block leading-snug font-sans">
                    {p.desc}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── ERROR STATE ───────────────────────────────────────────────────── */}
      {errorMsg && (
        <div
          role="alert"
          className="p-4 rounded-xl flex items-start gap-3 text-xs font-mono bg-[#FF4D6D]/10 border border-[#FF4D6D]/25 backdrop-blur-md"
        >
          <AlertTriangle className="h-4 w-4 text-[#FF4D6D] shrink-0 mt-0.5" aria-hidden="true" />
          <div className="space-y-1.5 flex-1 min-w-0">
            <span className="font-bold text-[#FF4D6D] block tracking-wider uppercase text-[11px]">
              IMPACT ANALYSIS FAILED
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
                EDIT SCENARIO
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
              ANALYZING CHANGE IMPACT
            </span>
          </div>
          <div className="flex items-center justify-center gap-3 text-[10px] font-mono text-[#64748B] uppercase tracking-wider flex-wrap">
            <span className="text-[#818CF8]">PARSING SCENARIO</span>
            <span>&rarr;</span>
            <span>WALKING DEPENDENCY GRAPH</span>
            <span>&rarr;</span>
            <span>TRACING CALLERS</span>
            <span>&rarr;</span>
            <span>COMPUTING BLAST RADIUS</span>
          </div>
        </div>
      )}

      {/* ── RESULTS WORKSPACE ─────────────────────────────────────────────── */}
      {impactData && !isLoading && (
        <div ref={resultsRef} className="space-y-5">
          {/* ── ZONE D: EXECUTIVE IMPACT BRIEF ────────────────────────────── */}
          <section aria-labelledby="executive-impact-brief" className="p-4 sm:p-5 rounded-xl space-y-3.5 bg-gradient-to-b from-[#0D1220]/90 to-[#070A12]/95 backdrop-blur-xl border border-white/[0.08]">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 pb-3 border-b border-white/[0.08]">
              <div>
                <span className="text-[9.5px] font-mono font-bold text-[#818CF8] uppercase tracking-widest block">
                  EXECUTIVE IMPACT BRIEF
                </span>
                <h3 id="executive-impact-brief" className="font-mono text-sm font-bold text-[#F8FAFC] mt-0.5 truncate max-w-xl">
                  &ldquo;{impactData.issue_text}&rdquo;
                </h3>
              </div>

              <div className="flex items-center gap-2.5 shrink-0 flex-wrap text-xs font-mono">
                <span className="px-2.5 py-0.5 rounded text-[10.5px] font-mono font-bold uppercase" style={{ background: `${blastRadiusInfo?.toneColor}18`, color: blastRadiusInfo?.toneColor, border: `1px solid ${blastRadiusInfo?.toneColor}40` }}>
                  {blastRadiusInfo?.badge}
                </span>

                <span className="px-2 py-0.5 rounded text-[10px] font-mono text-[#CBD5E1] bg-[#0D1220] border border-white/[0.08]">
                  {impactData.confidence}% CONFIDENCE
                </span>

                <span className="px-2 py-0.5 rounded text-[10px] font-mono text-[#64748B] bg-[#0D1220] border border-white/[0.08]">
                  ANALYZED {relativeTime(analyzedTimestamp).toUpperCase()}
                </span>
              </div>
            </div>

            {/* Continuous Analytical Metric Rail with Clear Dominant Hierarchy */}
            <div className="rounded-lg overflow-hidden font-mono divide-y divide-white/[0.08] bg-[#0A0D14] border border-white/[0.08]">
              {/* Primary Dominant Tier: Total Affected Files, Downstream Reach, Blast Radius */}
              <div className="grid grid-cols-1 sm:grid-cols-3 divide-y sm:divide-y-0 sm:divide-x divide-white/[0.08]">
                {/* 1. AFFECTED FILES (Dominant) */}
                <div className="p-3.5 space-y-1 bg-[#0A0D14]">
                  <div className="flex items-baseline justify-between">
                    <span className="text-3xl font-bold tracking-tight text-[#F8FAFC] tabular-nums">
                      {impactData.estimated_file_count || allAffectedFiles.length}
                    </span>
                    <span className="text-[10px] font-mono font-bold uppercase tracking-widest text-[#818CF8]">
                      TOTAL FILES
                    </span>
                  </div>
                  <span className="text-[9px] font-mono text-[#64748B] uppercase tracking-wider block">
                    DIRECT &middot; DOWNSTREAM IMPACTED
                  </span>
                </div>

                {/* 2. DOWNSTREAM REACH (Dominant) */}
                <div className="p-3.5 space-y-1 bg-[#0A0D14]">
                  <div className="flex items-baseline justify-between">
                    <span className={`text-3xl font-bold tracking-tight tabular-nums ${impactData.indirectly_affected_files.length > 0 ? 'text-[#FCD34D]' : 'text-[#64748B]'}`}>
                      {impactData.indirectly_affected_files.length}
                    </span>
                    <span className="text-[10px] font-mono font-bold uppercase tracking-widest text-[#FCD34D]">
                      DOWNSTREAM
                    </span>
                  </div>
                  <span className="text-[9px] font-mono text-[#64748B] uppercase tracking-wider block">
                    TRANSITIVE CONSUMERS REACHABLE
                  </span>
                </div>

                {/* 3. BLAST RADIUS (Dominant with Semantic Relationship) */}
                <div className="p-3.5 space-y-1 bg-[#0A0D14]">
                  <div className="flex items-baseline justify-between">
                    <span className="text-2xl font-bold tracking-tight" style={{ color: blastRadiusInfo?.toneColor }}>
                      {blastRadiusInfo?.category}
                    </span>
                    <span className="text-[10px] font-mono font-bold uppercase tracking-widest" style={{ color: blastRadiusInfo?.toneColor }}>
                      {impactData.risk_level.toUpperCase()}
                    </span>
                  </div>
                  <span className="text-[10px] font-mono font-bold text-[#F8FAFC] uppercase tracking-wider block truncate">
                    {blastRadiusSemantic}
                  </span>
                </div>
              </div>

              {/* Secondary Supporting Tier: Symbols, Components, Test Impact, Confidence */}
              <div className="grid grid-cols-2 sm:grid-cols-4 divide-x divide-white/[0.08] text-xs">
                {/* 4. AFFECTED SYMBOLS */}
                <div className="p-2.5 px-3 space-y-0.5 bg-[#0D1220]/70">
                  <div className="flex items-baseline justify-between">
                    <span className="text-lg font-bold text-[#F8FAFC] tabular-nums">
                      {impactData.affected_symbols?.length ?? 0}
                    </span>
                    <span className="text-[8.5px] font-mono font-bold text-[#64748B] uppercase tracking-widest">
                      SYMBOLS
                    </span>
                  </div>
                  <span className="text-[8.5px] font-mono text-[#64748B] uppercase block">
                    RESOLVED TARGETS
                  </span>
                </div>

                {/* 5. COMPONENTS */}
                <div className="p-2.5 px-3 space-y-0.5 bg-[#0D1220]/70">
                  <div className="flex items-baseline justify-between">
                    <span className="text-lg font-bold text-[#F8FAFC] tabular-nums">
                      {impactData.affected_components?.length ?? 0}
                    </span>
                    <span className="text-[8.5px] font-mono font-bold text-[#64748B] uppercase tracking-widest">
                      COMPONENTS
                    </span>
                  </div>
                  <span className="text-[8.5px] font-mono text-[#64748B] uppercase block">
                    SUBSYSTEM BOUNDARIES
                  </span>
                </div>

                {/* 6. TEST IMPACT (Preserves UNKNOWN) */}
                <div className="p-2.5 px-3 space-y-0.5 bg-[#0D1220]/70">
                  <div className="flex items-baseline justify-between">
                    <span className={`text-lg font-bold tabular-nums ${impactData.affected_tests && impactData.affected_tests.length > 0 ? 'text-[#34D399]' : 'text-[#64748B]'
                      }`}>
                      {impactData.affected_tests ? impactData.affected_tests.length : 'UNKNOWN'}
                    </span>
                    <span className="text-[8.5px] font-mono font-bold text-[#64748B] uppercase tracking-widest">
                      TEST IMPACT
                    </span>
                  </div>
                  <span className="text-[8.5px] font-mono text-[#64748B] uppercase block">
                    {impactData.affected_tests ? 'VERIFIED CALLERS' : 'UNMAPPED'}
                  </span>
                </div>

                {/* 7. CONFIDENCE (Separated with Semantic Relationship) */}
                <div className="p-2.5 px-3 space-y-0.5 bg-[#0D1220]/70">
                  <div className="flex items-baseline justify-between">
                    <span className="text-lg font-bold text-[#34D399] tabular-nums">
                      {impactData.confidence}%
                    </span>
                    <span className="text-[8.5px] font-mono font-bold text-[#34D399] uppercase tracking-widest">
                      CONFIDENCE
                    </span>
                  </div>
                  <span className="text-[8.5px] font-mono text-[#64748B] uppercase block truncate">
                    {confidenceSemantic}
                  </span>
                </div>
              </div>
            </div>
          </section>

          {/* ── ZONE E: PRIMARY IMPACT SUMMARY & ENGINEERING INTERPRETATION ── */}
          <section aria-labelledby="primary-impact-summary" className="p-4 sm:p-5 rounded-xl space-y-3.5 bg-gradient-to-b from-[#0D1220]/90 to-[#070A12]/95 backdrop-blur-xl border border-white/[0.08]">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 pb-2.5 border-b border-white/[0.08]">
              <div className="flex items-center gap-2">
                <Compass className="h-4 w-4 text-[#818CF8]" />
                <h3 id="primary-impact-summary" className="text-xs font-bold font-mono text-[#F8FAFC] uppercase tracking-wider">
                  IMPACT SUMMARY &amp; FORENSIC INTERPRETATION
                </h3>
              </div>
              <span className="text-[10px] font-mono text-[#64748B] uppercase tracking-wider">
                EVIDENCE-DRIVEN REASONING
              </span>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3.5 text-xs">
              <div className="p-3.5 rounded-lg space-y-2 bg-[#0A0D14] border border-white/[0.08]">
                <div className="flex items-center gap-2">
                  <span className="px-2 py-0.5 rounded text-[9.5px] font-mono font-bold uppercase" style={{ background: `${blastRadiusInfo?.toneColor}18`, color: blastRadiusInfo?.toneColor, border: `1px solid ${blastRadiusInfo?.toneColor}30` }}>
                    {blastRadiusInfo?.label}
                  </span>
                </div>
                <p className="text-[#F8FAFC] font-medium leading-relaxed text-[12.5px]">
                  Affected modules span {impactData.affected_components.length || 1} repository subsystem(s) with {impactData.indirectly_affected_files.length} downstream consumer(s) reachable via import edges.
                </p>
                <div className="space-y-1 pt-1">
                  <span className="text-[9.5px] font-mono font-bold text-[#64748B] uppercase tracking-wider block">
                    WHY THIS MATTERS
                  </span>
                  <p className="text-[#CBD5E1] font-sans leading-relaxed text-[11.5px]">
                    Changing the proposed target modifies core definitions. Downstream callers and importers rely on interface contracts that may experience ripple effects across subsystem boundaries.
                  </p>
                </div>
              </div>

              <div className="p-3.5 rounded-lg space-y-2 bg-[#0A0D14] border border-white/[0.08]">
                <span className="text-[9.5px] font-mono font-bold text-[#818CF8] uppercase tracking-wider block">
                  WHAT THIS MEANS
                </span>
                <p className="text-[#CBD5E1] font-sans leading-relaxed text-[11.5px]">
                  {impactData.risk_level === 'high' || impactData.risk_level === 'extreme'
                    ? 'This change crosses critical architectural boundaries. Stage changes incrementally and verify downstream imports before merging.'
                    : 'The change is localized with bounded downstream reach. Standard PR review with focused regression testing is adequate.'}
                </p>

                <div className="space-y-1 pt-1">
                  <span className="text-[9.5px] font-mono font-bold text-[#64748B] uppercase tracking-wider block">
                    WHAT STATIC ANALYSIS CANNOT PROVE
                  </span>
                  <p className="text-[10px] font-mono text-[#64748B] leading-relaxed">
                    Dynamic imports &middot; Runtime registration &middot; Reflection &middot; External consumers &middot; Feature flags
                  </p>
                </div>
              </div>
            </div>
          </section>

          {/* ── ZONE F: DIRECT VS DOWNSTREAM CASCADE ──────────────────────── */}
          <section aria-labelledby="direct-vs-downstream-heading" className="p-4 sm:p-5 rounded-xl space-y-3.5 bg-gradient-to-b from-[#0D1220]/90 to-[#070A12]/95 backdrop-blur-xl border border-white/[0.08]">
            <div className="flex items-center justify-between pb-2.5 border-b border-white/[0.08]">
              <div>
                <h3 id="direct-vs-downstream-heading" className="text-xs font-bold font-mono text-[#F8FAFC] uppercase tracking-wider flex items-center gap-2">
                  <Activity className="h-3.5 w-3.5 text-[#818CF8]" />
                  DIRECT IMPACT VS DOWNSTREAM CASCADE
                </h3>
                <p className="text-[10.5px] text-[#CBD5E1] font-sans mt-0.5">
                  Separating files directly matched from downstream dependents reachable via dependency propagation.
                </p>
              </div>

              <div className="hidden sm:flex items-center gap-2 text-[10px] font-mono text-[#64748B]">
                <span>TARGET</span>
                <span>&rarr;</span>
                <span>DEPENDENT</span>
                <span>&rarr;</span>
                <span>DOWNSTREAM</span>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 font-mono text-xs">
              {/* Direct Impact Bucket */}
              <div className="p-3.5 rounded-lg space-y-2 bg-[#0A0D14] border border-white/[0.08] border-l-2 border-l-[#FF758F]">
                <div className="flex items-center justify-between">
                  <span className="text-[10.5px] font-bold text-[#FF758F] uppercase tracking-wider flex items-center gap-1.5">
                    <span className="h-1.5 w-1.5 rounded-full bg-[#FF758F]" />
                    DIRECT IMPACT ({impactData.directly_affected_files.length})
                  </span>
                  <span className="text-[9.5px] text-[#64748B]">MODIFICATION TARGETS</span>
                </div>
                <div className="space-y-1 max-h-44 overflow-y-auto pr-1">
                  {impactData.directly_affected_files.length === 0 ? (
                    <p className="text-[11px] text-[#64748B] italic">No direct files matched.</p>
                  ) : (
                    impactData.directly_affected_files.map((file, idx) => {
                      const isSelected = selectedFile === file;
                      return (
                        <div
                          key={idx}
                          onClick={() => selectFile(file)}
                          className={`p-1.5 rounded flex items-center justify-between gap-2 cursor-pointer transition-colors text-[11px] ${isSelected
                              ? 'bg-[#131A2E] text-[#F8FAFC] border-l-2 border-[#818CF8]'
                              : 'hover:bg-[#0D1220] text-[#F8FAFC]'
                            }`}
                        >
                          <span className="truncate">{file}</span>
                          <ArrowUpRight className="h-3 w-3 text-[#64748B] shrink-0" />
                        </div>
                      );
                    })
                  )}
                </div>
              </div>

              {/* Downstream Cascade Bucket */}
              <div className="p-3.5 rounded-lg space-y-2 bg-[#0A0D14] border border-white/[0.08] border-l-2 border-l-[#FCD34D]">
                <div className="flex items-center justify-between">
                  <span className="text-[10.5px] font-bold text-[#FCD34D] uppercase tracking-wider flex items-center gap-1.5">
                    <span className="h-1.5 w-1.5 rounded-full bg-[#FCD34D]" />
                    DOWNSTREAM CASCADE ({impactData.indirectly_affected_files.length})
                  </span>
                  <span className="text-[9.5px] text-[#64748B]">TRANSITIVE CONSUMERS</span>
                </div>
                <div className="space-y-1 max-h-44 overflow-y-auto pr-1">
                  {impactData.indirectly_affected_files.length === 0 ? (
                    <div className="p-3.5 rounded flex flex-col items-center justify-center text-center space-y-1.5 my-1 bg-[#0A0D14] border border-dashed border-white/[0.08]">
                      <ShieldCheck className="h-4 w-4 text-[#34D399]" />
                      <span className="text-[10.5px] font-bold font-mono text-[#34D399] uppercase tracking-wider">
                        NO DOWNSTREAM RIPPLE DETECTED
                      </span>
                      <p className="text-[10px] text-[#CBD5E1] font-sans max-w-sm leading-relaxed">
                        Current indexed dependency analysis found no transitive consumers reachable from the direct targets.
                      </p>
                    </div>
                  ) : (
                    impactData.indirectly_affected_files.map((file, idx) => {
                      const isSelected = selectedFile === file;
                      return (
                        <div
                          key={idx}
                          onClick={() => selectFile(file)}
                          className={`p-1.5 rounded flex items-center justify-between gap-2 cursor-pointer transition-colors text-[11px] ${isSelected
                              ? 'bg-[#131A2E] text-[#F8FAFC] border-l-2 border-[#818CF8]'
                              : 'hover:bg-[#0D1220] text-[#CBD5E1]'
                            }`}
                        >
                          <span className="truncate">{file}</span>
                          <ArrowUpRight className="h-3 w-3 text-[#64748B] shrink-0" />
                        </div>
                      );
                    })
                  )}
                </div>
              </div>
            </div>
          </section>

          {/* ── ZONE G: AFFECTED FILES REGISTRY (Progressive Disclosure & Search) ── */}
          <section aria-labelledby="affected-files-registry" className="p-4 sm:p-5 rounded-xl space-y-3.5 bg-gradient-to-b from-[#0D1220]/90 to-[#070A12]/95 backdrop-blur-xl border border-white/[0.08]">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 pb-2.5 border-b border-white/[0.08]">
              <div>
                <h3 id="affected-files-registry" className="text-xs font-bold font-mono text-[#F8FAFC] uppercase tracking-wider flex items-center gap-2">
                  <ListChecks className="h-3.5 w-3.5 text-[#818CF8]" />
                  AFFECTED FILES REGISTRY ({filteredFiles.length})
                </h3>
                <p className="text-[10.5px] text-[#CBD5E1] font-sans mt-0.5">
                  Ordered by evidence strength, confidence, and propagation proximity.
                </p>
              </div>

              {/* Search filter */}
              <div className="relative min-w-[200px] sm:min-w-[240px]">
                <Search className="h-3 w-3 text-[#64748B] absolute left-2.5 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  value={fileSearch}
                  onChange={(e) => setFileSearch(e.target.value)}
                  placeholder="Filter impacted files..."
                  className="w-full rounded-md pl-8 pr-7 py-1 text-xs font-mono text-[#F8FAFC] placeholder-[#64748B] bg-[#07090E] border border-white/[0.10] focus:border-[#818CF8] focus:ring-1 focus:ring-[#818CF8]/30 focus-visible:outline-none transition-colors"
                />
                {fileSearch && (
                  <button
                    type="button"
                    onClick={() => setFileSearch('')}
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-[#64748B] hover:text-[#F8FAFC]"
                  >
                    <X className="h-3 w-3" />
                  </button>
                )}
              </div>
            </div>

            {/* Files List */}
            {filteredFiles.length === 0 ? (
              <div className="p-4 text-center rounded-lg text-xs font-mono text-[#CBD5E1] space-y-1 bg-[#0A0D14] border border-white/[0.08]">
                <p>No impacted files matching &ldquo;{fileSearch}&rdquo;</p>
                <button
                  type="button"
                  onClick={() => setFileSearch('')}
                  className="text-[#818CF8] hover:underline"
                >
                  Clear filter
                </button>
              </div>
            ) : (
              <div className="space-y-1.5">
                {displayedFiles.map((file, idx) => {
                  const isDirect = file.isDirect;
                  const isSelected = selectedFile === file.path;
                  const tagColor = isDirect ? '#FF758F' : '#FCD34D';
                  const tagBg = isDirect ? 'rgba(255,117,143,0.12)' : 'rgba(252,211,77,0.12)';
                  const tagBorder = isDirect ? 'rgba(255,117,143,0.30)' : 'rgba(252,211,77,0.30)';

                  return (
                    <div
                      key={file.path}
                      onClick={() => selectFile(file.path)}
                      className={`p-3 rounded-lg transition-all space-y-1.5 text-xs cursor-pointer ${isSelected
                          ? 'border-[#818CF8]/60 shadow-[0_0_16px_rgba(129,140,248,0.18)] bg-[#131A2E]'
                          : 'hover:border-white/[0.14] hover:bg-[#0D1220] bg-[#0A0D14]'
                        }`}
                      style={{
                        border: `1px solid ${isSelected ? 'rgba(129,140,248,0.5)' : 'rgba(255,255,255,0.08)'}`,
                        borderLeft: isSelected ? '2px solid #818CF8' : undefined,
                      }}
                    >
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1.5">
                        <div className="flex items-center gap-2 min-w-0">
                          <span className="text-[10px] font-mono font-bold text-[#64748B] shrink-0">
                            {String(idx + 1).padStart(2, '0')}
                          </span>
                          <span
                            className="px-1.5 py-0.5 rounded text-[9px] font-mono font-bold uppercase shrink-0"
                            style={{ color: tagColor, background: tagBg, border: `1px solid ${tagBorder}` }}
                          >
                            {isDirect ? 'DIRECT TARGET' : 'DOWNSTREAM'}
                          </span>
                          <span className="font-mono text-xs text-[#F8FAFC] font-semibold truncate" title={file.path}>
                            {file.path}
                          </span>
                          <button
                            type="button"
                            onClick={(e) => handleCopy(e, file.path)}
                            className="text-[#64748B] hover:text-[#F8FAFC] p-0.5 shrink-0 transition-colors"
                            title="Copy path"
                          >
                            {copiedPath === file.path ? <Check className="h-3 w-3 text-[#34D399]" /> : <Copy className="h-3 w-3" />}
                          </button>
                        </div>

                        <div className="flex items-center gap-2 shrink-0 font-mono text-[10px]">
                          <span className="px-1.5 py-0.5 rounded text-[#CBD5E1] bg-[#0D1220] border border-white/[0.08]">
                            {Math.round(file.confidenceScore * 100)}% CONFIDENCE
                          </span>
                          <span className="px-1.5 py-0.5 rounded text-[#34D399] bg-[#0D1220] border border-white/[0.08]">
                            VERIFIED
                          </span>
                        </div>
                      </div>

                      <div className="flex items-center justify-between gap-3 text-xs">
                        <div className="text-[11px] text-[#CBD5E1] font-sans leading-relaxed flex-1 truncate">
                          {file.reason}
                        </div>

                        <div className="flex items-center gap-2.5 font-mono text-[10px] shrink-0">
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              openInGraph(file.path);
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
                              openInCallGraph(file.path);
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
                              openInChat(`What is the impact of modifying ${file.path} under this change?`);
                            }}
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
                {!isSearchActive && filteredFiles.length > 8 && (
                  <div className="pt-1.5 flex items-center justify-between text-xs font-mono">
                    <span className="text-[#64748B]">
                      SHOWING {displayedFiles.length} OF {filteredFiles.length} IMPACTED FILES
                    </span>
                    <div className="flex items-center gap-2">
                      {filesLimit < filteredFiles.length ? (
                        <button
                          type="button"
                          onClick={() => setFilesLimit((prev) => Math.min(prev + 8, filteredFiles.length))}
                          className="px-3 py-1 rounded-md bg-[#0D1220] border border-white/[0.08] hover:bg-[#131A2E] text-[#F8FAFC] text-xs font-mono transition-colors flex items-center gap-1.5"
                        >
                          <span>SHOW MORE IMPACTED FILES ({displayedFiles.length} &rarr; {Math.min(filesLimit + 8, filteredFiles.length)})</span>
                          <ChevronDown className="h-3 w-3" />
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={() => setFilesLimit(8)}
                          className="px-3 py-1 rounded-md bg-[#0D1220] border border-white/[0.08] hover:bg-[#131A2E] text-[#CBD5E1] hover:text-[#F8FAFC] text-xs font-mono transition-colors flex items-center gap-1.5"
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

          {/* ── ZONE H: AFFECTED SYMBOLS ────────────────────────────────────── */}
          {impactData.affected_symbols && impactData.affected_symbols.length > 0 && (
            <section aria-labelledby="affected-symbols-heading" className="p-4 sm:p-5 rounded-xl space-y-3.5" style={{ border: `1px solid ${T.hairline}`, background: T.glassCard, backdropFilter: 'blur(12px)' }}>
              <div className="flex items-center justify-between pb-2.5" style={{ borderBottom: `1px solid ${T.hairline}` }}>
                <div>
                  <h3 id="affected-symbols-heading" className="text-xs font-bold font-mono text-[#F8FAFC] uppercase tracking-wider flex items-center gap-2">
                    <FileCode className="h-3.5 w-3.5 text-[#818CF8]" />
                    AFFECTED SYMBOLS ({impactData.affected_symbols.length})
                  </h3>
                  <p className="text-[10.5px] text-[#CBD5E1] font-sans mt-0.5">
                    Functions, methods, and classes directly modified or invoked along execution pathways.
                  </p>
                </div>
                <span className="text-[10px] font-mono text-[#64748B]">
                  SYMBOL RESOLUTION
                </span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2 font-mono text-xs">
                {impactData.affected_symbols.map((symbol, idx) => (
                  <div
                    key={idx}
                    className="p-2.5 rounded-lg flex items-center justify-between gap-2 bg-[#0A0D14] border border-white/[0.08] hover:bg-[#0D1220] transition-colors"
                  >
                    <div className="min-w-0 flex items-center gap-2">
                      <span className="text-[9.5px] font-mono text-[#64748B]">#{idx + 1}</span>
                      <span className="font-semibold text-[#F8FAFC] text-xs truncate" title={symbol}>
                        {symbol}()
                      </span>
                    </div>
                    <button
                      type="button"
                      onClick={() => openInChat(`What callers depend on symbol ${symbol}() in ${impactData.repo}?`)}
                      className="text-[#CBD5E1] hover:text-[#818CF8] text-[10px] shrink-0 uppercase"
                      title="Inspect symbol in Chat"
                    >
                      CHAT
                    </button>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* ── ZONE I: IMPACT PROPAGATION GRAPH ───────────────────────────── */}
          <section aria-labelledby="impact-propagation-graph" className="p-4 sm:p-5 rounded-xl space-y-3.5 bg-gradient-to-b from-[#0D1220]/90 to-[#070A12]/95 backdrop-blur-xl border border-white/[0.08]">
            <div className="flex items-center justify-between pb-2.5 border-b border-white/[0.08]">
              <div>
                <h3 id="impact-propagation-graph" className="text-xs font-bold font-mono text-[#F8FAFC] uppercase tracking-wider flex items-center gap-2">
                  <Network className="h-3.5 w-3.5 text-[#818CF8]" />
                  IMPACT PROPAGATION GRAPH
                </h3>
                <p className="text-[10.5px] text-[#CBD5E1] font-sans mt-0.5">
                  Interactive topology of direct modification targets, dependent files, and component clusters.
                </p>
              </div>

              <div className="flex items-center gap-3 font-mono text-[10px]">
                <button
                  type="button"
                  onClick={() => openInGraph()}
                  className="text-[#CBD5E1] hover:text-[#818CF8] flex items-center gap-1 uppercase transition-colors"
                >
                  <span>VIEW FULL FILE GRAPH</span>
                  <ArrowUpRight className="h-3 w-3" />
                </button>
                <button
                  type="button"
                  onClick={() => openInCallGraph()}
                  className="text-[#CBD5E1] hover:text-[#818CF8] flex items-center gap-1 uppercase transition-colors"
                >
                  <span>VIEW CALL GRAPH</span>
                  <ArrowUpRight className="h-3 w-3" />
                </button>
              </div>
            </div>

            {/* Embedded ReactFlow Canvas */}
            <div className="rounded-lg overflow-hidden border border-white/[0.08] bg-[#020304]">
              <Suspense fallback={
                <div className="h-72 flex items-center justify-center font-mono text-xs text-[#64748B]">
                  Loading propagation canvas…
                </div>
              }>
                <ImpactAnalysisGraph
                  repoName={activeRepo}
                  impactData={impactData}
                  onReset={resetToNewScenario}
                  variant="graph-only"
                  hideScenarioStrip={true}
                />
              </Suspense>
            </div>
          </section>

          {/* ── ZONE J: COMPONENT IMPACT ───────────────────────────────────── */}
          {impactData.affected_components && impactData.affected_components.length > 0 && (
            <section aria-labelledby="component-impact-heading" className="p-4 sm:p-5 rounded-xl space-y-3.5 bg-gradient-to-b from-[#0D1220]/90 to-[#070A12]/95 backdrop-blur-xl border border-white/[0.08]">
              <div className="flex items-center justify-between pb-2.5 border-b border-white/[0.08]">
                <div>
                  <h3 id="component-impact-heading" className="text-xs font-bold font-mono text-[#F8FAFC] uppercase tracking-wider flex items-center gap-2">
                    <Layers className="h-3.5 w-3.5 text-[#818CF8]" />
                    COMPONENT IMPACT ({impactData.affected_components.length})
                  </h3>
                  <p className="text-[10.5px] text-[#CBD5E1] font-sans mt-0.5">
                    Repository architectural subsystems touched by this change.
                  </p>
                </div>
              </div>

              <div className={impactData.affected_components.length === 1 ? 'grid grid-cols-1 font-mono text-xs' : 'grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 font-mono text-xs'}>
                {impactData.affected_components.map((comp, idx) => {
                  const compLower = comp.toLowerCase();
                  const compFiles = allAffectedFiles.filter(f => f.path.toLowerCase().includes(compLower));
                  const directCount = compFiles.filter(f => f.isDirect).length;
                  const downstreamCount = compFiles.filter(f => !f.isDirect).length;
                  const compSymbols = (impactData.affected_symbols || []).filter(s =>
                    s.toLowerCase().includes(compLower)
                  );

                  return (
                    <div
                      key={idx}
                      className="p-3.5 rounded-lg space-y-2 bg-[#0A0D14] border border-white/[0.08] hover:bg-[#0D1220] transition-colors"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-[#F8FAFC] text-xs uppercase tracking-wider">
                          {comp}
                        </span>
                        <span className="text-[9.5px] font-mono text-[#818CF8] font-bold">
                          {compFiles.length || 1} FILE(S)
                        </span>
                      </div>

                      <div className="grid grid-cols-2 gap-2 text-[10px] font-mono text-[#64748B] pt-0.5">
                        <div>
                          <span className="text-[#CBD5E1] font-semibold">{directCount}</span> DIRECT &middot; <span className="text-[#CBD5E1] font-semibold">{downstreamCount}</span> DOWNSTREAM
                        </div>
                        <div className="text-right">
                          <span className="text-[#CBD5E1] font-semibold">{compSymbols.length > 0 ? compSymbols.length : '1+'}</span> SYMBOL(S)
                        </div>
                      </div>

                      <p className="text-[11px] text-[#CBD5E1] font-sans pt-1 border-t border-white/[0.04]">
                        {directCount > 0 && downstreamCount > 0
                          ? 'Subsystem contains both target implementations and downstream consumers.'
                          : directCount > 0
                            ? 'Subsystem contains direct modification targets.'
                            : 'Subsystem is affected via downstream transitive propagation.'}
                      </p>
                    </div>
                  );
                })}
              </div>
            </section>
          )}

          {/* ── ZONE K: TEST IMPACT ────────────────────────────────────────── */}
          <section aria-labelledby="test-impact-heading" className="p-4 sm:p-5 rounded-xl space-y-3.5 bg-gradient-to-b from-[#0D1220]/90 to-[#070A12]/95 backdrop-blur-xl border border-white/[0.08]">
            <div className="flex items-center justify-between pb-2.5 border-b border-white/[0.08]">
              <div>
                <h3 id="test-impact-heading" className="text-xs font-bold font-mono text-[#F8FAFC] uppercase tracking-wider flex items-center gap-2">
                  <TestTube className="h-3.5 w-3.5 text-[#818CF8]" />
                  TEST IMPACT ({impactData.affected_tests ? impactData.affected_tests.length : 'UNKNOWN'})
                </h3>
                <p className="text-[10.5px] text-[#CBD5E1] font-sans mt-0.5">
                  Test files exercising affected modules or calling modified symbols.
                </p>
              </div>

              <span className="text-[9.5px] font-mono uppercase tracking-wider px-2 py-0.5 rounded bg-[#0D1220] border border-white/[0.08]" style={{ color: impactData.affected_tests && impactData.affected_tests.length > 0 ? '#34D399' : '#64748B' }}>
                {impactData.affected_tests && impactData.affected_tests.length > 0 ? 'KNOWN' : impactData.affected_tests ? 'NONE DETECTED' : 'UNKNOWN'}
              </span>
            </div>

            {impactData.affected_tests && impactData.affected_tests.length > 0 ? (
              <div className="space-y-1.5">
                {impactData.affected_tests.map((test, idx) => (
                  <div
                    key={idx}
                    className="p-3 rounded-lg flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs font-mono bg-[#0A0D14] border border-white/[0.08] hover:bg-[#0D1220] transition-colors"
                  >
                    <div className="space-y-0.5 min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-[9px] px-1.5 py-0.5 rounded uppercase font-bold text-[#FF758F] bg-[#FF758F]/10 border border-[#FF758F]/30">
                          {test.impact_type}
                        </span>
                        <span className="text-[#F8FAFC] font-medium truncate">{test.test_file}</span>
                      </div>
                      <p className="text-[11px] text-[#CBD5E1] font-sans">{test.reason}</p>
                    </div>

                    <div className="flex items-center gap-2 shrink-0 text-[10px]">
                      <span className="px-1.5 py-0.5 rounded text-[#34D399] bg-[#0D1220] border border-white/[0.08]">
                        {test.confidence_tier || 'HIGH'}
                      </span>
                      <button
                        type="button"
                        onClick={() => openInChat(`How should test ${test.test_file} be updated for this change?`)}
                        className="text-[#CBD5E1] hover:text-[#818CF8] uppercase transition-colors"
                      >
                        CHAT
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            ) : impactData.affected_tests && impactData.affected_tests.length === 0 ? (
              <div className="p-3 rounded-lg text-xs font-mono text-[#CBD5E1] flex items-center gap-2 bg-[#0A0D14] border border-white/[0.08]">
                <ShieldCheck className="h-4 w-4 text-[#34D399] shrink-0" />
                <span>No repository-internal tests were detected that directly import or call the identified target symbols.</span>
              </div>
            ) : (
              <div className="p-3 rounded-lg text-xs font-mono text-[#CBD5E1] space-y-1 bg-[#0A0D14] border border-white/[0.08]">
                <div className="flex items-center gap-2 text-[#64748B] font-bold uppercase">
                  <HelpCircle className="h-4 w-4 shrink-0" />
                  <span>TEST IMPACT: UNKNOWN</span>
                </div>
                <p className="text-[11px] text-[#CBD5E1] font-sans">
                  Static analysis cannot establish complete runtime test behavior or test discovery configuration in this repository.
                </p>
              </div>
            )}
          </section>

          {/* ── ZONE L: BLAST RADIUS & DECISION LAYER ──────────────────────── */}
          {recommendedAction && (
            <section aria-labelledby="blast-radius-recommendation" className="p-4 sm:p-5 rounded-xl space-y-3.5 bg-gradient-to-b from-[#0D1220]/90 to-[#070A12]/95 backdrop-blur-xl border border-white/[0.08]">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 pb-2.5 border-b border-white/[0.08]">
                <div>
                  <span className="text-[9.5px] font-mono font-bold text-[#818CF8] uppercase tracking-widest block">
                    CHANGE DECISION
                  </span>
                  <h3 id="blast-radius-recommendation" className="font-mono text-sm font-bold text-[#F8FAFC] mt-0.5">
                    RECOMMENDED ENGINEERING ACTION
                  </h3>
                </div>

                <span
                  className="px-2.5 py-0.5 rounded text-xs font-mono font-bold uppercase"
                  style={{
                    color: recommendedAction.tone,
                    background: `${recommendedAction.tone}18`,
                    border: `1px solid ${recommendedAction.tone}35`
                  }}
                >
                  {recommendedAction.title}
                </span>
              </div>

              {/* Compact Evidence Row above narrative */}
              <div className="flex items-center gap-2 flex-wrap text-[10.5px] font-mono text-[#CBD5E1]">
                <span className="text-[#F8FAFC] font-bold">
                  {blastRadiusInfo?.category} BLAST RADIUS ({impactData.risk_level.toUpperCase()})
                </span>
                <span className="text-[#64748B]">&middot;</span>
                <span className="text-[#34D399] font-bold">
                  {impactData.confidence}% CONFIDENCE
                </span>
                <span className="text-[#64748B]">&middot;</span>
                <span className={impactData.indirectly_affected_files.length > 0 ? 'text-[#FCD34D] font-bold' : 'text-[#64748B]'}>
                  {impactData.indirectly_affected_files.length} DOWNSTREAM
                </span>
                <span className="text-[#64748B]">&middot;</span>
                <span className="text-[#FF758F] font-bold">
                  {impactData.directly_affected_files.length} DIRECT TARGETS
                </span>
              </div>

              <div className="p-3.5 rounded-lg space-y-2 text-xs bg-[#0A0D14] border border-white/[0.08]">
                <p className="text-[#F8FAFC] font-medium leading-relaxed text-[12px]">
                  {recommendedAction.description}
                </p>

                <p className="text-[10px] font-mono text-[#64748B] uppercase tracking-wider pt-1">
                  STATIC ANALYSIS ONLY &mdash; This blast radius reflects indexed repository dependencies and call graph reach. External callers and runtime behavior are outside static scope.
                </p>
              </div>
            </section>
          )}

          {/* ── ZONE M: ACTION BAR ─────────────────────────────────────────── */}
          <div className="p-3 rounded-xl flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 bg-gradient-to-r from-[#0D1220]/95 to-[#070A12]/95 backdrop-blur-xl border border-white/[0.08] shadow-2xl">
            <div className="flex items-center gap-2 flex-wrap font-mono text-xs">
              {selectedFile && (
                <div className="px-2.5 py-1 rounded text-[10.5px] font-mono text-[#CBD5E1] flex items-center gap-1.5 border border-white/[0.08] bg-[#07090E] max-w-[220px] sm:max-w-xs truncate">
                  <span className="text-[9px] uppercase text-[#818CF8] font-bold shrink-0">SELECTED:</span>
                  <span className="truncate text-[#F8FAFC]">{selectedFile}</span>
                </div>
              )}
              <button
                type="button"
                onClick={() => openInGraph(selectedFile || undefined)}
                className="px-3.5 py-1.5 rounded-md bg-[#818CF8] hover:bg-[#A5B4FC] active:bg-[#6366F1] border border-white/10 text-white text-xs font-bold font-mono transition-all shadow-[0_0_12px_rgba(129,140,248,0.25)] flex items-center gap-1.5"
              >
                <span>VIEW FILE GRAPH</span>
                <ArrowRight className="h-3 w-3" />
              </button>
              <button
                type="button"
                onClick={() => openInCallGraph(selectedFile || undefined)}
                className="px-3 py-1.5 rounded-md bg-[#0D1220] border border-white/[0.08] hover:bg-[#131A2E] text-[#CBD5E1] hover:text-[#F8FAFC] flex items-center gap-1 transition-colors"
              >
                <span>CALL GRAPH</span>
                <ArrowUpRight className="h-3 w-3" />
              </button>
              <button
                type="button"
                onClick={() => openInChat(selectedFile ? `Explain how ${selectedFile} is impacted by this change in ${activeRepo}` : undefined)}
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
                onClick={resetToNewScenario}
                className="px-3 py-1.5 rounded-md bg-[#0D1220] border border-white/[0.08] hover:bg-[#131A2E] text-[#CBD5E1] hover:text-[#F8FAFC] flex items-center gap-1 transition-colors"
              >
                <Plus className="h-3 w-3" />
                <span>NEW SCENARIO</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ImpactAnalysisWorkspace;

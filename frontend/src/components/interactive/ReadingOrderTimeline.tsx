import React, { useState, useEffect, useMemo, useRef } from 'react';
import { apiUrl, extractErrorMessage } from '../../lib/api';
import { FilePath } from '../ui/FilePath';
import { EmptyState } from '../ui/EmptyState';
import { 
  BookOpen, 
  Clock, 
  ArrowDown, 
  ArrowRight,
  ArrowLeft, 
  Info, 
  X, 
  ExternalLink, 
  GitMerge,
  ChevronRight,
  Sparkles,
  Compass,
  DoorOpen,
  Check,
  CheckCircle,
  RotateCcw,
  Workflow
} from 'lucide-react';

export interface ReadingOrderEntry {
  rank: number;
  file_path: string;
  reason: string;
  tier: string;
  score: number;
}

export interface ReadingOrder {
  repo: string;
  ordered_files: ReadingOrderEntry[];
  reasoning: string[];
  estimated_reading_time: number;
  total_files_ranked: number;
}

interface FileSymbol {
  name: string;
  type: string;
  file_path: string;
  line_number: number;
  language: string;
  parent_class?: string | null;
}

interface FileDependencies {
  imports: string[];
  importedBy: string[];
}

type PanelDataState = 'idle' | 'loading' | 'ready' | 'unavailable';

export interface TimelineProps {
  repoName: string;
  /** Sends a file-specific question to the Chat tab. */
  onAskAboutFile?: (filePath: string) => void;
  /** Focuses the File Graph tab on this file's neighbourhood. */
  onViewInGraph?: (filePath: string) => void;
  /** Focuses the Call Graph tab on this file. */
  onViewInCallGraph?: (filePath: string) => void;
  /** Optional preloaded reading order data */
  initialData?: ReadingOrder | null;
}

/**
 * Normalized localStorage key generator for repository progress.
 */
function getStorageKey(repo: string): string {
  const normalized = (repo || 'default').trim().toLowerCase();
  return `reading-path-progress:${normalized}`;
}

export const ReadingOrderTimeline: React.FC<TimelineProps> = ({
  repoName,
  onAskAboutFile,
  onViewInGraph,
  onViewInCallGraph,
  initialData,
}) => {
  const [readingPath, setReadingPath] = useState<ReadingOrder | null>(initialData || null);
  const [loading, setLoading] = useState<boolean>(!initialData);
  const [error, setError] = useState<string | null>(null);
  
  // Progress tracking state (persisted in localStorage per repository)
  const [completedFiles, setCompletedFiles] = useState<Record<string, boolean>>({});
  const [selectedFile, setSelectedFile] = useState<ReadingOrderEntry | null>(null);
  const [announcement, setAnnouncement] = useState<string>('');

  // File Intelligence panel enrichment
  const [symbols, setSymbols] = useState<FileSymbol[]>([]);
  const [symbolState, setSymbolState] = useState<PanelDataState>('idle');
  const [deps, setDeps] = useState<FileDependencies>({ imports: [], importedBy: [] });
  const [depsState, setDepsState] = useState<PanelDataState>('idle');

  // Load progress for repository
  const loadSavedProgress = (repo: string, files: ReadingOrderEntry[]) => {
    if (typeof window === 'undefined') return {};
    const key = getStorageKey(repo);
    try {
      const stored = localStorage.getItem(key);
      if (stored) {
        const parsed: Record<string, boolean> = JSON.parse(stored);
        // Prune stale paths not in current ordered_files
        const valid: Record<string, boolean> = {};
        files.forEach((f) => {
          if (parsed[f.file_path]) {
            valid[f.file_path] = true;
          }
        });
        return valid;
      }
    } catch (e) {
      console.error('Failed to parse progress from localStorage', e);
    }
    return {};
  };

  // 1. Fetch reading order data (lazy loaded on mount if not provided)
  useEffect(() => {
    if (initialData) {
      setReadingPath(initialData);
      const files = initialData.ordered_files || [];
      const saved = loadSavedProgress(repoName, files);
      setCompletedFiles(saved);

      // Find first unread step or default to first step
      const firstUnread = files.find((f) => !saved[f.file_path]) || files[0] || null;
      setSelectedFile(firstUnread);
      setLoading(false);
      return;
    }

    setSelectedFile(null);
    setReadingPath(null);
    const fetchReadingOrder = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(apiUrl('/api/v1/reading-order'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ repo: repoName })
        });
        
        if (!response.ok) {
          const errJson = await response.json().catch(() => ({}));
          throw new Error(extractErrorMessage(errJson) || 'Failed to fetch reading path');
        }
        
        const data: ReadingOrder = await response.json();
        setReadingPath(data);
        
        const files = data.ordered_files || [];
        const saved = loadSavedProgress(repoName, files);
        setCompletedFiles(saved);

        // Default select the first unread step
        const firstUnread = files.find((f) => !saved[f.file_path]) || files[0] || null;
        setSelectedFile(firstUnread);
      } catch (err: any) {
        console.error(err);
        setError(err.message || 'An error occurred generating the reading order.');
      } finally {
        setLoading(false);
      }
    };

    if (repoName) {
      fetchReadingOrder();
    }
  }, [repoName, initialData]);

  /**
   * Enriches the File Intelligence panel for the selected file using existing
   * read-only endpoints: the symbol index and the dependency graph neighbourhood.
   */
  useEffect(() => {
    const filePath = selectedFile?.file_path;
    const [owner, repo] = repoName.split('/');

    if (!filePath || !owner || !repo) {
      setSymbols([]);
      setSymbolState('idle');
      setDeps({ imports: [], importedBy: [] });
      setDepsState('idle');
      return;
    }

    const controller = new AbortController();
    const encodedPath = filePath.split('/').map(encodeURIComponent).join('/');

    setSymbolState('loading');
    setDepsState('loading');

    fetch(apiUrl(`/api/v1/symbols/${owner}/${repo}/file/${encodedPath}`), { signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error('unavailable');
        return res.json();
      })
      .then((data) => {
        setSymbols(Array.isArray(data?.symbols) ? data.symbols : []);
        setSymbolState('ready');
      })
      .catch((err) => {
        if (err?.name === 'AbortError') return;
        setSymbols([]);
        setSymbolState('unavailable');
      });

    fetch(apiUrl(`/api/v1/graph/${owner}/${repo}/neighbors/${encodedPath}`), { signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error('unavailable');
        return res.json();
      })
      .then((data) => {
        const edges: { source: string; target: string }[] = Array.isArray(data?.edges) ? data.edges : [];
        const imports = edges.filter((e) => e.source === filePath).map((e) => e.target);
        const importedBy = edges.filter((e) => e.target === filePath).map((e) => e.source);
        setDeps({
          imports: Array.from(new Set(imports)).sort(),
          importedBy: Array.from(new Set(importedBy)).sort(),
        });
        setDepsState('ready');
      })
      .catch((err) => {
        if (err?.name === 'AbortError') return;
        setDeps({ imports: [], importedBy: [] });
        setDepsState('unavailable');
      });

    return () => controller.abort();
  }, [selectedFile?.file_path, repoName]);

  // Derived reading metrics and step state
  const ordered_files = readingPath?.ordered_files || [];
  const totalFiles = ordered_files.length;
  const estimated_reading_time = readingPath?.estimated_reading_time || 0;
  const reasoning = readingPath?.reasoning || [];

  // Completed count
  const completedCount = useMemo(() => {
    return ordered_files.filter((f) => completedFiles[f.file_path]).length;
  }, [ordered_files, completedFiles]);

  const progressPct = totalFiles > 0 ? (completedCount / totalFiles) * 100 : 0;
  const isAllComplete = totalFiles > 0 && completedCount === totalFiles;

  // Dynamic estimated minutes per file calculation from score
  const getFileReadingTime = (score: number) => {
    return Math.max(1, Math.round(score / 20));
  };

  // Importance tier categorization
  const getImportanceLevel = (score: number) => {
    if (score > 100) return { label: 'Critical', color: 'text-success border-success/30 bg-success/10' };
    if (score > 50) return { label: 'Important', color: 'text-primary border-primary/30 bg-primary/10' };
    return { label: 'Supporting', color: 'text-text-muted border-white/[0.08] bg-white/[0.02]' };
  };

  // First unread step calculation (Dynamic "Start Here" / "Continue Here" target)
  const firstUnreadIndex = useMemo(() => {
    return ordered_files.findIndex((f) => !completedFiles[f.file_path]);
  }, [ordered_files, completedFiles]);

  const currentUnreadStep = useMemo(() => {
    if (firstUnreadIndex === -1) return null;
    return ordered_files[firstUnreadIndex] || null;
  }, [ordered_files, firstUnreadIndex]);

  // Remaining reading time (Sum of unread steps only)
  const remainingMinutes = useMemo(() => {
    return ordered_files
      .filter((f) => !completedFiles[f.file_path])
      .reduce((sum, f) => sum + getFileReadingTime(f.score), 0);
  }, [ordered_files, completedFiles]);

  // Count metrics
  const entryPointsCount = useMemo(() => ordered_files.filter((f) => f.tier === 'entry_point').length, [ordered_files]);
  const coreModulesCount = useMemo(() => ordered_files.filter((f) => f.tier === 'core').length, [ordered_files]);

  // Handle step completion and automatic advancement to next unread step
  const handleToggleComplete = (filePath: string) => {
    const isCurrentlyComplete = !!completedFiles[filePath];
    const willBeComplete = !isCurrentlyComplete;
    
    const updated: Record<string, boolean> = {
      ...completedFiles,
      [filePath]: willBeComplete,
    };
    if (!willBeComplete) {
      delete updated[filePath];
    }
    setCompletedFiles(updated);
    
    // Persist to normalized repository storage key
    const key = getStorageKey(repoName);
    try {
      localStorage.setItem(key, JSON.stringify(updated));
    } catch (e) {
      console.error('Failed to save progress to localStorage', e);
    }

    // Automatic advancement on completion
    if (willBeComplete) {
      const currentIdx = ordered_files.findIndex((f) => f.file_path === filePath);
      // Find next unread step across the sequence
      const nextUnread = ordered_files.find((f) => f.file_path !== filePath && !updated[f.file_path]);

      if (nextUnread) {
        const nextIdx = ordered_files.findIndex((f) => f.file_path === nextUnread.file_path);
        setSelectedFile(nextUnread);
        const fileName = nextUnread.file_path.split('/').pop() || nextUnread.file_path;
        setAnnouncement(`Step ${currentIdx + 1} completed. Continuing with step ${nextIdx + 1}, ${fileName}.`);
      } else {
        setAnnouncement(`All ${totalFiles} reading steps completed. Reading path complete.`);
      }
    }
  };

  const handleResetProgress = () => {
    setCompletedFiles({});
    const key = getStorageKey(repoName);
    try {
      localStorage.removeItem(key);
    } catch (e) {
      console.error('Failed to clear progress in localStorage', e);
    }
    if (ordered_files.length > 0) {
      setSelectedFile(ordered_files[0]);
    }
    setAnnouncement('Reading progress reset.');
  };

  // Step navigation in Context Drawer
  const currentIndex = useMemo(() => {
    if (!selectedFile || !readingPath) return -1;
    return ordered_files.findIndex(f => f.file_path === selectedFile.file_path);
  }, [selectedFile, ordered_files, readingPath]);

  const handleSelectStep = (entry: ReadingOrderEntry, scrollToDrawer: boolean = false) => {
    setSelectedFile(entry);
    if (scrollToDrawer && typeof window !== 'undefined' && window.innerWidth < 1024) {
      setTimeout(() => {
        const el = document.getElementById('reading-step-context');
        el?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }, 50);
    }
  };

  const handleNavigateStep = (delta: number) => {
    if (!readingPath || currentIndex === -1) return;
    const targetIdx = currentIndex + delta;
    if (targetIdx >= 0 && targetIdx < ordered_files.length) {
      setSelectedFile(ordered_files[targetIdx]);
    }
  };

  if (loading) {
    return (
      <div className="w-full space-y-6 fade-up" aria-label="Reading Path Loading">
        <div className="p-6 rounded-xl border border-white/[0.07] bg-surface-0/60 space-y-4">
          <div className="flex items-center justify-between">
            <div className="space-y-2">
              <div className="skeleton h-5 w-48 rounded" />
              <div className="skeleton h-3 w-80 rounded" />
            </div>
            <div className="skeleton h-7 w-28 rounded" />
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 pt-2">
            {[1, 2, 3, 4].map(i => (
              <div key={i} className="skeleton h-16 w-full rounded" />
            ))}
          </div>
        </div>
        <div className="space-y-4">
          {[1, 2, 3].map(i => (
            <div key={i} className="skeleton h-24 w-full rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8 rounded-xl border border-danger/30 bg-danger/5 text-center max-w-xl mx-auto space-y-4 fade-up">
        <Info className="h-7 w-7 text-danger mx-auto" />
        <h3 className="font-mono text-sm font-semibold text-text uppercase">Reading Path Generation Failed</h3>
        <p className="text-xs text-text-muted font-sans leading-relaxed">{error}</p>
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="btn-ghost text-xs inline-flex items-center gap-1.5 px-4 py-2 text-primary font-sans font-semibold"
        >
          <RotateCcw className="h-3.5 w-3.5" />
          <span>Retry Generation</span>
        </button>
      </div>
    );
  }

  if (!readingPath || !readingPath.ordered_files || readingPath.ordered_files.length === 0) {
    return (
      <div className="py-8 max-w-xl mx-auto">
        <EmptyState
          icon={<BookOpen className="h-8 w-8 text-text-subtle" />}
          title="No reading path available"
          description="ARIA could not derive a reliable onboarding sequence from the available repository structure. Explore the file graph or ask ARIA for guidance."
          action={
            <div className="flex flex-wrap gap-2 justify-center mt-3">
              {onViewInGraph && (
                <button
                  type="button"
                  onClick={() => onViewInGraph('')}
                  className="btn-ghost text-xs inline-flex items-center gap-1.5 font-sans font-semibold"
                >
                  <GitMerge className="h-3.5 w-3.5" aria-hidden="true" />
                  <span>Inspect File Graph</span>
                </button>
              )}
              {onAskAboutFile && (
                <button
                  type="button"
                  onClick={() => onAskAboutFile('repository')}
                  className="btn-ghost text-xs inline-flex items-center gap-1.5 font-sans font-semibold"
                >
                  <Sparkles className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
                  <span>Ask ARIA</span>
                </button>
              )}
            </div>
          }
        />
      </div>
    );
  }

  return (
    <div className="w-full space-y-6 sm:space-y-7 pb-10 fade-up" aria-label="Reading Path Workspace">
      {/* Screen Reader Live Region for Accessible Step Transitions */}
      <div aria-live="polite" aria-atomic="true" className="sr-only">
        {announcement}
      </div>

      {/* ── 1. READING PATH HEADER & ONBOARDING SUMMARY ──────────────────────── */}
      <section aria-labelledby="reading-path-header-title" className="rounded-xl border border-white/[0.07] bg-surface-0/70 p-5 sm:p-6 backdrop-blur-sm shadow-xl">
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 pb-4 border-b border-white/[0.06]">
          <div>
            <div className="flex items-center gap-2">
              <Compass className="h-4 w-4 text-primary" aria-hidden="true" />
              <h2 id="reading-path-header-title" className="mono-label text-text font-semibold tracking-[0.16em] text-xs sm:text-sm">
                READING PATH
              </h2>
            </div>
            <p className="text-xs sm:text-sm text-text-muted font-sans mt-1 leading-relaxed">
              A guided route through the most important parts of this repository.
            </p>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <span className="mono-detail text-[11px] px-2.5 py-1 rounded-md bg-surface-1/60 border border-white/[0.06] text-text font-medium flex items-center gap-1.5">
              <BookOpen className="h-3.5 w-3.5 text-primary" />
              <span>{totalFiles} files</span>
            </span>
            <span className="mono-detail text-[11px] px-2.5 py-1 rounded-md bg-primary/10 border border-primary/25 text-primary font-medium flex items-center gap-1.5">
              <Clock className="h-3.5 w-3.5" />
              <span>~{estimated_reading_time} min</span>
            </span>
            <span className="mono-detail text-[10px] uppercase text-text-subtle px-2 py-1 rounded bg-white/[0.03] border border-white/[0.04]">
              TOPOLOGY-RANKED
            </span>
          </div>
        </div>

        {/* Metrics Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3.5 pt-4">
          <div className="p-3 rounded-lg bg-surface-1/40 border border-white/[0.04] text-center">
            <span className="mono-label block text-[9.5px] text-text-subtle uppercase mb-1 tracking-[0.16em]">READING STEPS</span>
            <span className="font-sans text-2xl sm:text-3xl font-bold text-text tabular-nums tracking-tight">{totalFiles}</span>
            <span className="text-[11px] text-text-muted block mt-0.5 font-sans">Ranked sequence</span>
          </div>
          <div className="p-3 rounded-lg bg-surface-1/40 border border-white/[0.04] text-center">
            <span className="mono-label block text-[9.5px] text-text-subtle uppercase mb-1 tracking-[0.16em]">EST. TIME</span>
            <span className="font-sans text-2xl sm:text-3xl font-bold text-text tabular-nums tracking-tight">{estimated_reading_time}m</span>
            <span className="text-[11px] text-text-muted block mt-0.5 font-sans">Total reading</span>
          </div>
          <div className="p-3 rounded-lg bg-surface-1/40 border border-white/[0.04] text-center">
            <span className="mono-label block text-[9.5px] text-text-subtle uppercase mb-1 tracking-[0.16em]">ENTRY POINTS</span>
            <span className="font-sans text-2xl sm:text-3xl font-bold text-success tabular-nums tracking-tight">{entryPointsCount}</span>
            <span className="text-[11px] text-text-muted block mt-0.5 font-sans">Starting roots</span>
          </div>
          <div className="p-3 rounded-lg bg-surface-1/40 border border-white/[0.04] text-center">
            <span className="mono-label block text-[9.5px] text-text-subtle uppercase mb-1 tracking-[0.16em]">CORE MODULES</span>
            <span className="font-sans text-2xl sm:text-3xl font-bold text-primary tabular-nums tracking-tight">{coreModulesCount}</span>
            <span className="text-[11px] text-text-muted block mt-0.5 font-sans">High centrality</span>
          </div>
        </div>

        {/* Onboarding Progress Bar */}
        <div className="mt-5 pt-4 border-t border-white/[0.06] flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="mono-label text-[10px] text-text-muted uppercase tracking-[0.16em]">
                ONBOARDING PROGRESS
              </span>
              {isAllComplete && (
                <span className="inline-flex items-center gap-1 text-[10px] font-mono font-bold text-success bg-success/10 border border-success/30 px-1.5 py-0.5 rounded">
                  <Check className="h-3 w-3" />
                  <span>COMPLETED</span>
                </span>
              )}
            </div>
            <div className="flex items-center gap-3 text-xs font-sans">
              <span className="text-text font-semibold">
                {completedCount} of {totalFiles} Steps Read ({Math.round(progressPct)}%)
              </span>
              {completedCount > 0 && !isAllComplete && (
                <span className="text-text-muted text-[11px]">
                  · ~{remainingMinutes}m remaining
                </span>
              )}
            </div>
          </div>

          <div className="flex items-center gap-3 flex-grow max-w-sm">
            <div className="flex-grow bg-white/[0.06] h-2 rounded-full overflow-hidden relative" role="progressbar" aria-valuenow={Math.round(progressPct)} aria-valuemin={0} aria-valuemax={100}>
              <div
                className="bg-primary h-full transition-all duration-300 rounded-full"
                style={{ width: `${progressPct}%` }}
                aria-hidden="true"
              />
            </div>
            {completedCount > 0 && (
              <button
                type="button"
                onClick={handleResetProgress}
                className="text-[10px] font-mono text-text-subtle hover:text-text hover:underline focus-visible:outline-none shrink-0"
                title="Reset reading progress"
              >
                Reset
              </button>
            )}
          </div>
        </div>
      </section>

      {/* ── 2. DYNAMIC "START HERE" / "CONTINUE HERE" / "READING PATH COMPLETE" BANNER ── */}
      {!isAllComplete && currentUnreadStep && (
        <section aria-labelledby="dynamic-banner-heading" className="rounded-xl border border-primary/35 bg-primary/[0.03] p-5 sm:p-6 relative overflow-hidden backdrop-blur-sm shadow-lg">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="space-y-2 min-w-0 flex-1">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="inline-flex items-center gap-1 text-[10px] font-mono font-bold uppercase tracking-wider text-primary bg-primary/10 border border-primary/30 px-2 py-0.5 rounded">
                  <DoorOpen className="h-3 w-3" />
                  <span>
                    {completedCount === 0 ? 'START HERE' : 'CONTINUE HERE'} · STEP {String(firstUnreadIndex + 1).padStart(2, '0')}
                  </span>
                </span>
                <span className="mono-detail text-[10px] text-text-subtle uppercase">
                  {currentUnreadStep.tier === 'entry_point'
                    ? 'PRIMARY APPLICATION ENTRY POINT'
                    : `${currentUnreadStep.tier.replace('_', ' ')} · ~${getFileReadingTime(currentUnreadStep.score)} MIN`}
                </span>
              </div>

              <div className="flex items-baseline gap-2">
                <h3 id="dynamic-banner-heading" className="font-mono text-sm sm:text-base font-bold text-text truncate">
                  {currentUnreadStep.file_path}
                </h3>
              </div>

              <p className="text-xs sm:text-sm text-text-muted font-sans leading-relaxed max-w-3xl">
                {currentUnreadStep.reason || 'Recommended starting point based on repository structure.'}
              </p>
            </div>

            <div className="flex items-center gap-2 shrink-0">
              <button
                type="button"
                onClick={() => handleSelectStep(currentUnreadStep, true)}
                className="action-chip text-xs px-4 py-2 inline-flex items-center gap-2 bg-primary/15 border-primary/40 text-primary hover:bg-primary/25 font-sans font-semibold"
              >
                <span>{completedCount === 0 ? 'Start Reading' : 'Continue Reading'}</span>
                <ArrowRight className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        </section>
      )}

      {/* Completion Banner (When all steps read) */}
      {isAllComplete && (
        <section aria-labelledby="completion-banner-heading" className="rounded-xl border border-success/35 bg-success/[0.04] p-5 sm:p-6 relative overflow-hidden backdrop-blur-sm shadow-xl">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="space-y-2 min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="inline-flex items-center gap-1.5 text-[10px] font-mono font-bold uppercase tracking-wider text-success bg-success/15 border border-success/40 px-2 py-0.5 rounded">
                  <CheckCircle className="h-3.5 w-3.5" />
                  <span>READING PATH COMPLETE</span>
                </span>
                <span className="mono-detail text-[10px] text-text-subtle uppercase">
                  {totalFiles} / {totalFiles} STEPS READ (100%)
                </span>
              </div>

              <h3 id="completion-banner-heading" className="font-sans text-sm sm:text-base font-bold text-text">
                All Recommended Reading Steps Completed
              </h3>

              <p className="text-xs sm:text-sm text-text-muted font-sans leading-relaxed max-w-3xl">
                You have completed the recommended repository reading sequence. You are now ready to explore architecture relationships, trace call paths, or ask ARIA specific questions.
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-2 shrink-0">
              {ordered_files.length > 0 && (
                <button
                  type="button"
                  onClick={() => handleSelectStep(ordered_files[0], true)}
                  className="action-chip text-xs px-3.5 py-1.5 inline-flex items-center gap-1.5 font-sans font-semibold"
                >
                  <BookOpen className="h-3.5 w-3.5 text-text-subtle" />
                  <span>Review Step 01</span>
                </button>
              )}
              {onViewInGraph && (
                <button
                  type="button"
                  onClick={() => onViewInGraph('')}
                  className="action-chip text-xs px-3.5 py-1.5 inline-flex items-center gap-1.5 font-sans font-semibold"
                >
                  <GitMerge className="h-3.5 w-3.5 text-primary" />
                  <span>Explore Architecture</span>
                </button>
              )}
              {onAskAboutFile && (
                <button
                  type="button"
                  onClick={() => onAskAboutFile('repository')}
                  className="btn-primary text-xs px-3.5 py-1.5 inline-flex items-center gap-1.5 font-sans font-semibold"
                >
                  <Sparkles className="h-3.5 w-3.5" />
                  <span>Ask ARIA</span>
                </button>
              )}
            </div>
          </div>
        </section>
      )}

      {/* ── 3. MAIN WORKSPACE: TIMELINE + FILE INTELLIGENCE DRAWER ───────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* ── LEFT: Ordered Reading Sequence (Timeline) ── */}
        <div className={`${selectedFile ? 'lg:col-span-7' : 'lg:col-span-12'} space-y-4 transition-all duration-200`}>
          <div className="flex items-center justify-between pb-2 border-b border-white/[0.06]">
            <span className="mono-label text-[11px] text-text tracking-wider">
              ORDERED READING SEQUENCE ({totalFiles})
            </span>
            <span className="mono-detail text-[10px] text-text-subtle">
              CLICK STEP TO INSPECT CONTEXT
            </span>
          </div>

          <div className="space-y-3 relative pl-6 before:absolute before:left-[11px] before:top-3 before:bottom-3 before:w-[2px] before:bg-white/[0.07]">
            {ordered_files.map((entry, idx) => {
              const isCompleted = !!completedFiles[entry.file_path];
              const isSelected = selectedFile?.file_path === entry.file_path;
              const isCurrentUnread = currentUnreadStep?.file_path === entry.file_path;
              const estMinutes = getFileReadingTime(entry.score);
              const importance = getImportanceLevel(entry.score);

              return (
                <div key={entry.file_path} className="relative space-y-2 group">
                  {/* Timeline node circle indicator */}
                  <button
                    type="button"
                    aria-label={isCompleted ? `Mark step ${idx + 1} incomplete` : `Mark step ${idx + 1} complete`}
                    onClick={(e) => {
                      e.stopPropagation();
                      handleToggleComplete(entry.file_path);
                    }}
                    className={`absolute -left-[24px] top-4 h-5 w-5 rounded-full border-2 bg-canvas transition-all z-10 flex items-center justify-center cursor-pointer focus-visible:outline-none ${
                      isCompleted
                        ? 'border-success bg-success/20 text-success'
                        : isCurrentUnread
                          ? 'border-primary bg-primary/20 text-primary ring-2 ring-primary/40'
                          : 'border-white/[0.2] hover:border-primary text-text-subtle'
                    }`}
                  >
                    {isCompleted ? (
                      <Check className="h-3 w-3 stroke-[3]" />
                    ) : isCurrentUnread ? (
                      <ArrowRight className="h-2.5 w-2.5 stroke-[3]" />
                    ) : null}
                  </button>

                  {/* Step Item Card */}
                  <div
                    onClick={() => handleSelectStep(entry, true)}
                    className={`p-4 rounded-xl border transition-all duration-150 cursor-pointer flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 ${
                      isSelected
                        ? 'border-primary/60 bg-surface-1/70 ring-1 ring-primary/40 shadow-lg'
                        : isCompleted
                          ? 'border-white/[0.05] bg-surface-0/40 opacity-85 hover:border-white/[0.12]'
                          : isCurrentUnread
                            ? 'border-primary/30 bg-primary/[0.02] hover:border-primary/50'
                            : 'border-white/[0.07] bg-surface-0/60 hover:border-primary/40 hover:bg-surface-1/40'
                    }`}
                  >
                    <div className="space-y-1.5 min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className={`font-mono text-xs font-bold ${isCompleted ? 'text-success' : isCurrentUnread ? 'text-primary' : 'text-text-muted'}`}>
                          {isCompleted ? '✓' : String(idx + 1).padStart(2, '0')}
                        </span>
                        <span className="text-xs font-mono font-semibold text-text truncate max-w-md" title={entry.file_path}>
                          {entry.file_path}
                        </span>
                        <span className={`text-[9px] font-mono px-1.5 py-0.5 rounded border uppercase font-bold ${
                          entry.tier === 'entry_point' ? 'bg-success/10 border-success/30 text-success' :
                          entry.tier === 'core' ? 'bg-primary/10 border-primary/30 text-primary' :
                          entry.tier === 'service' ? 'bg-indigo-500/10 border-indigo-500/30 text-indigo-400' :
                          entry.tier === 'utility' ? 'bg-amber-500/10 border-amber-500/30 text-warn' :
                          'bg-white/[0.04] border-white/[0.08] text-text-muted'
                        }`}>
                          {entry.tier.replace('_', ' ')}
                        </span>
                        <span className={`text-[8px] font-mono px-1.5 py-0.5 rounded border uppercase font-bold ${importance.color}`}>
                          {importance.label}
                        </span>
                      </div>

                      <p className="text-xs text-text-muted font-sans leading-relaxed line-clamp-2">
                        {entry.reason}
                      </p>
                    </div>

                    <div className="flex items-center gap-3 shrink-0 self-end sm:self-center font-mono text-[11px]">
                      <div className="flex items-center gap-1 text-text-subtle px-2 py-0.5 rounded bg-white/[0.03] border border-white/[0.04]">
                        <Clock className="h-3 w-3" />
                        <span>~{estMinutes}m</span>
                      </div>
                      <ChevronRight className={`h-4 w-4 transition-transform ${isSelected ? 'text-primary translate-x-0.5' : 'text-text-subtle group-hover:text-text'}`} />
                    </div>
                  </div>

                  {/* Connecting Arrow between steps */}
                  {idx < totalFiles - 1 && (
                    <div className="flex items-center gap-2 pl-4 py-1 text-[10px] font-mono text-text-subtle" aria-hidden="true">
                      <ArrowDown className="h-3.5 w-3.5 text-white/[0.15]" />
                      <span className="text-[9px] uppercase tracking-wider text-text-subtle">
                        Next in sequence
                      </span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* ── 4. WHY THIS ORDER? (Algorithmic explanation) ───────────────── */}
          <div className="p-4 sm:p-5 rounded-xl border border-white/[0.06] bg-surface-0/40 backdrop-blur-sm space-y-2 mt-6">
            <div className="flex items-center gap-2">
              <Info className="h-4 w-4 text-primary" aria-hidden="true" />
              <span className="mono-label text-[10px] text-text tracking-wider uppercase">
                WHY THIS ORDER?
              </span>
            </div>
            <p className="text-xs text-text-muted font-sans leading-relaxed">
              {reasoning && reasoning.length > 0
                ? reasoning[0]
                : 'The reading path begins with confirmed application entry points, traverses core high-centrality modules, and respects dependency direction so foundational components are understood before their consumers.'}
            </p>
          </div>
        </div>

        {/* ── RIGHT: Selected File Intelligence Drawer ── */}
        {selectedFile && (
          <aside id="reading-step-context" className="lg:col-span-5 p-5 sm:p-6 rounded-xl border border-white/[0.08] bg-surface-0/70 backdrop-blur-sm space-y-5 sticky top-16 max-h-[calc(100vh-5rem)] overflow-y-auto shadow-2xl">
            {/* Drawer Header */}
            <div className="flex items-start justify-between gap-3 pb-3 border-b border-white/[0.06]">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className="mono-label mono-label-accent text-[10px]">STEP CONTEXT</span>
                  {currentIndex !== -1 && (
                    <span className="mono-detail text-[10px] text-text-subtle">
                      {currentIndex + 1} OF {totalFiles}
                    </span>
                  )}
                </div>
                <h3 className="font-mono text-sm sm:text-base font-bold text-text truncate" title={selectedFile.file_path}>
                  {selectedFile.file_path.split('/').pop()}
                </h3>
              </div>

              <button
                type="button"
                onClick={() => setSelectedFile(null)}
                className="text-text-subtle hover:text-text transition-colors p-1 rounded hover:bg-white/[0.05]"
                aria-label="Close step context"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Step Navigation Controls (Prev / Next & Complete) */}
            <div className="flex items-center justify-between gap-2 p-2 rounded-lg bg-surface-1/40 border border-white/[0.04]">
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  disabled={currentIndex <= 0}
                  onClick={() => handleNavigateStep(-1)}
                  className="px-2.5 py-1 rounded bg-white/[0.04] border border-white/[0.06] text-xs font-sans font-medium text-text hover:bg-white/[0.08] disabled:opacity-30 disabled:cursor-not-allowed inline-flex items-center gap-1"
                >
                  <ArrowLeft className="h-3 w-3" />
                  <span>Prev</span>
                </button>
                <button
                  type="button"
                  disabled={currentIndex === -1 || currentIndex >= totalFiles - 1}
                  onClick={() => handleNavigateStep(1)}
                  className="px-2.5 py-1 rounded bg-white/[0.04] border border-white/[0.06] text-xs font-sans font-medium text-text hover:bg-white/[0.08] disabled:opacity-30 disabled:cursor-not-allowed inline-flex items-center gap-1"
                >
                  <span>Next</span>
                  <ArrowRight className="h-3 w-3" />
                </button>
              </div>

              <button
                type="button"
                onClick={() => handleToggleComplete(selectedFile.file_path)}
                className={`px-3 py-1 rounded text-xs font-sans font-semibold inline-flex items-center gap-1.5 transition-colors ${
                  completedFiles[selectedFile.file_path]
                    ? 'bg-success/15 border border-success/40 text-success hover:bg-success/25'
                    : 'bg-white/[0.05] border border-white/[0.08] text-text hover:border-primary/40'
                }`}
              >
                <Check className="h-3.5 w-3.5" />
                <span>{completedFiles[selectedFile.file_path] ? 'Completed' : 'Mark as Read'}</span>
              </button>
            </div>

            {/* Path & Metadata */}
            <div className="space-y-3 font-mono text-xs">
              <div>
                <span className="mono-label text-[9.5px] text-text-subtle uppercase block mb-1 tracking-[0.16em]">FILE PATH</span>
                <FilePath path={selectedFile.file_path} tone="primary" size="sm" />
              </div>

              <div className="grid grid-cols-2 gap-3 pt-2">
                <div className="p-2.5 rounded bg-surface-1/30 border border-white/[0.03]">
                  <span className="mono-label text-[9.5px] text-text-subtle uppercase block mb-0.5 tracking-[0.16em]">CATEGORY</span>
                  <span className="text-text font-sans font-semibold uppercase text-[11px]">{selectedFile.tier.replace('_', ' ')}</span>
                </div>
                <div className="p-2.5 rounded bg-surface-1/30 border border-white/[0.03]">
                  <span className="mono-label text-[9.5px] text-text-subtle uppercase block mb-0.5 tracking-[0.16em]">READ TIME</span>
                  <span className="text-text font-sans font-semibold text-[11px]">~{getFileReadingTime(selectedFile.score)} min</span>
                </div>
              </div>

              <div className="pt-2">
                <span className="mono-label text-[9.5px] text-text-subtle uppercase block mb-1 tracking-[0.16em]">WHY READ THIS FILE</span>
                <p className="text-xs sm:text-sm text-text font-sans leading-relaxed p-3 rounded bg-surface-1/30 border border-white/[0.04]">
                  {selectedFile.reason}
                </p>
              </div>
            </div>

            {/* Defined Symbols (AST Symbols) */}
            <div className="space-y-2 pt-2 border-t border-white/[0.05]">
              <div className="flex items-center justify-between">
                <span className="mono-label text-[10px] text-text-muted tracking-[0.16em] uppercase">
                  DEFINED SYMBOLS
                </span>
                {symbolState === 'ready' && (
                  <span className="mono-detail text-[10px] text-text-subtle">
                    {symbols.length}
                  </span>
                )}
              </div>

              {symbolState === 'loading' && (
                <div className="space-y-1.5">
                  <div className="skeleton h-3 w-full rounded" />
                  <div className="skeleton h-3 w-2/3 rounded" />
                </div>
              )}

              {symbolState === 'ready' && symbols.length > 0 && (
                <ul className="max-h-36 overflow-y-auto space-y-1 pr-1 font-mono text-xs">
                  {symbols.slice(0, 30).map((sym) => (
                    <li key={`${sym.type}-${sym.name}-${sym.line_number}`} className="flex items-baseline justify-between gap-2 p-1.5 rounded bg-surface-1/30 border border-white/[0.03]">
                      <div className="flex items-baseline gap-2 min-w-0">
                        <span className="text-[9px] uppercase px-1 py-0.2 rounded bg-white/[0.04] text-text-subtle shrink-0">
                          {sym.type.slice(0, 3)}
                        </span>
                        <span className="text-text truncate text-[11px]" title={sym.name}>
                          {sym.name}
                        </span>
                      </div>
                      <span className="mono-detail text-[10px] text-text-subtle shrink-0">
                        L{sym.line_number}
                      </span>
                    </li>
                  ))}
                </ul>
              )}

              {symbolState === 'ready' && symbols.length === 0 && (
                <p className="text-[11px] text-text-subtle font-sans">No named functions or classes indexed.</p>
              )}

              {symbolState === 'unavailable' && (
                <p className="text-[11px] text-text-subtle font-sans">Symbol index unavailable.</p>
              )}
            </div>

            {/* Dependency Neighbourhood */}
            <div className="space-y-2 pt-2 border-t border-white/[0.05]">
              <span className="mono-label text-[10px] text-text-muted tracking-[0.16em] uppercase">
                DEPENDENCY NEIGHBOURHOOD
              </span>

              {depsState === 'loading' && (
                <div className="space-y-1.5">
                  <div className="skeleton h-3 w-full rounded" />
                </div>
              )}

              {depsState === 'ready' && (deps.imports.length > 0 || deps.importedBy.length > 0) && (
                <div className="space-y-2 font-mono text-xs">
                  {deps.imports.length > 0 && (
                    <div>
                      <span className="mono-detail text-[9px] text-text-subtle block mb-1">
                        IMPORTS ({deps.imports.length})
                      </span>
                      <ul className="max-h-20 overflow-y-auto space-y-1 pr-1">
                        {deps.imports.slice(0, 5).map((imp) => (
                          <li key={imp} className="p-1 rounded bg-surface-1/30 text-[10px] truncate" title={imp}>
                            → {imp}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {deps.importedBy.length > 0 && (
                    <div>
                      <span className="mono-detail text-[9px] text-text-subtle block mb-1">
                        IMPORTED BY ({deps.importedBy.length})
                      </span>
                      <ul className="max-h-20 overflow-y-auto space-y-1 pr-1">
                        {deps.importedBy.slice(0, 5).map((imp) => (
                          <li key={imp} className="p-1 rounded bg-surface-1/30 text-[10px] truncate" title={imp}>
                            ← {imp}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}

              {depsState === 'ready' && deps.imports.length === 0 && deps.importedBy.length === 0 && (
                <p className="text-[11px] text-text-subtle font-sans">Isolated node with no direct file import edges.</p>
              )}

              {depsState === 'unavailable' && (
                <p className="text-[11px] text-text-subtle font-sans">Dependency graph unavailable.</p>
              )}
            </div>

            {/* Action Buttons */}
            <div className="space-y-2 pt-3 border-t border-white/[0.06]">
              {onAskAboutFile && (
                <button
                  type="button"
                  onClick={() => onAskAboutFile(selectedFile.file_path)}
                  className="w-full flex items-center justify-between p-2.5 rounded-lg bg-surface-1/60 border border-white/[0.08] hover:border-primary/50 text-xs font-sans font-medium text-text transition-colors group focus-visible:outline-none"
                >
                  <span className="flex items-center gap-2">
                    <Sparkles className="h-3.5 w-3.5 text-primary" />
                    <span>Ask ARIA About File</span>
                  </span>
                  <ArrowRight className="h-3.5 w-3.5 text-text-subtle group-hover:text-primary transition-colors" />
                </button>
              )}

              {onViewInGraph && (
                <button
                  type="button"
                  onClick={() => onViewInGraph(selectedFile.file_path)}
                  className="w-full flex items-center justify-between p-2.5 rounded-lg bg-surface-1/60 border border-white/[0.08] hover:border-primary/50 text-xs font-sans font-medium text-text transition-colors group focus-visible:outline-none"
                >
                  <span className="flex items-center gap-2">
                    <GitMerge className="h-3.5 w-3.5 text-primary" />
                    <span>Inspect in File Graph</span>
                  </span>
                  <ArrowRight className="h-3.5 w-3.5 text-text-subtle group-hover:text-primary transition-colors" />
                </button>
              )}

              {onViewInCallGraph && (
                <button
                  type="button"
                  onClick={() => onViewInCallGraph(selectedFile.file_path)}
                  className="w-full flex items-center justify-between p-2.5 rounded-lg bg-surface-1/60 border border-white/[0.08] hover:border-primary/50 text-xs font-sans font-medium text-text transition-colors group focus-visible:outline-none"
                >
                  <span className="flex items-center gap-2">
                    <Workflow className="h-3.5 w-3.5 text-primary" />
                    <span>Trace in Call Graph</span>
                  </span>
                  <ArrowRight className="h-3.5 w-3.5 text-text-subtle group-hover:text-primary transition-colors" />
                </button>
              )}

              <a
                href={`https://github.com/${repoName}/blob/HEAD/${selectedFile.file_path}`}
                target="_blank"
                rel="noopener noreferrer"
                className="w-full flex items-center justify-between p-2.5 rounded-lg bg-surface-1/40 border border-white/[0.05] hover:border-white/[0.15] text-xs font-sans font-medium text-text-muted hover:text-text transition-colors group"
              >
                <span className="flex items-center gap-2">
                  <ExternalLink className="h-3.5 w-3.5 text-text-subtle" />
                  <span>Open on GitHub</span>
                </span>
                <ChevronRight className="h-3.5 w-3.5 text-text-subtle group-hover:text-text transition-colors" />
              </a>
            </div>
          </aside>
        )}
      </div>
    </div>
  );
};

export default ReadingOrderTimeline;

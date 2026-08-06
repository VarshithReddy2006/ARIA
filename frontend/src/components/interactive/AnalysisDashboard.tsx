import React, { useState, useEffect, useMemo, Suspense, lazy } from 'react';
import { apiUrl, extractErrorMessage } from '../../lib/api';
import FileTree from './FileTree';
import IssueMapper from './IssueMapper';
import ChatInterface from './ChatInterface';
import { ReadingOrderTimeline } from './ReadingOrderTimeline';
import { PRIntelligence } from './PRIntelligence';
import { ArchitectureDrift } from './ArchitectureDrift';
import { DeadCodeAnalyzer } from './DeadCodeAnalyzer';
import { GitHistoryAnalyzer } from './GitHistoryAnalyzer';
import { CallGraphAnalyzer } from './CallGraphAnalyzer';
import { APISurfaceAnalyzer } from './APISurfaceAnalyzer';
import { ReportPanel } from './ReportPanel';
import { RepoHero } from './RepoHero';
import { TechStackPanel } from './TechStackPanel';
import { DependencyExplorer } from './DependencyExplorer';
import { RepoCommandPalette, COMMAND_ICONS, type CommandItem } from './RepoCommandPalette';
import { ExecutiveInsights } from './ExecutiveInsights';
import { deriveInsights } from '../../lib/repoInsights';
import { Tabs, type TabItem } from './Tabs';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { MetricCard } from '../ui/MetricCard';
import { EmptyState } from '../ui/EmptyState';
import { SkeletonCard, SkeletonGroup, SkeletonGraph, Skeleton, SkeletonDashboard } from '../ui/Skeleton';
import { AnimatedNumber } from '../ui/AnimatedNumber';
import {
  computeComplexity, detectPrimaryLanguage, estimateReadingMinutes,
  relativeTimeFrom, formatDuration,
} from '../../lib/repoMetrics';
import {
  Layers, Box, Code2, BookOpen, Cpu, Info, Target, HelpCircle,
  MessageSquareCode, GitPullRequest, GitCompare, Trash2, FileText, DoorOpen,
  Network, AlertCircle, GitCommit, Workflow, Globe, ArrowRight, BarChart2,
} from 'lucide-react';

// ── Lazy-load graph-heavy components ──────────────────────────────────────────
const InteractiveDependencyGraph = lazy(
  () => import('./graph/InteractiveDependencyGraph').then(m => ({ default: m.InteractiveDependencyGraph }))
);
const ImpactAnalysisGraph = lazy(
  () => import('./ImpactAnalysisGraph').then(m => ({ default: m.ImpactAnalysisGraph }))
);

// ── Types ─────────────────────────────────────────────────────────────────────

interface ComponentRelationship {
  source: string;
  target: string;
  relationship_type: string;
  description: string;
}

interface AnalysisData {
  analysis: {
    structure: Record<string, string[]>;
    dependencies: string[];
    tech_stack: string[];
    metadata: Record<string, string>;
  };
  architecture: {
    summary: string;
    reading_order: string[];
    relationships: ComponentRelationship[];
  };
}

interface DashboardProps {
  repoParam?: string;
}

type TabId =
  | 'analysis' | 'reading_path' | 'chat'
  | 'graph' | 'call_graph' | 'api_surface'
  | 'report' | 'dead_code' | 'issues'
  | 'git_history' | 'pr_intelligence' | 'architecture_drift' | 'impact_analysis';

const TABS: TabItem<TabId>[] = [
  // ── Understand ──
  { id: 'analysis',           label: 'Overview',      icon: Layers,          group: 'Understand' },
  { id: 'reading_path',       label: 'Reading Path',  icon: BookOpen,        group: 'Understand' },
  { id: 'chat',               label: 'Chat',          icon: MessageSquareCode, group: 'Understand' },
  // ── Structure ──
  { id: 'graph',              label: 'File Graph',    icon: Code2,           group: 'Structure' },
  { id: 'call_graph',         label: 'Call Graph',    icon: Workflow,        group: 'Structure' },
  { id: 'api_surface',        label: 'API Surface',   icon: Globe,           group: 'Structure' },
  // ── Quality ──
  { id: 'report',             label: 'Health Report', icon: FileText,        group: 'Quality' },
  { id: 'dead_code',          label: 'Dead Code',     icon: Trash2,          group: 'Quality' },
  { id: 'issues',             label: 'Issues',        icon: Cpu,             group: 'Quality' },
  // ── History & PRs ──
  { id: 'git_history',        label: 'Git History',   icon: GitCommit,       group: 'History & PRs' },
  { id: 'pr_intelligence',    label: 'PR Risk',       icon: GitPullRequest,  group: 'History & PRs' },
  { id: 'architecture_drift', label: 'PR Drift',      icon: GitCompare,      group: 'History & PRs' },
  { id: 'impact_analysis',    label: 'Impact',        icon: Target,          group: 'History & PRs' },
];

function countFiles(structure: Record<string, string[]>): number {
  return Object.values(structure).reduce((sum, arr) => sum + arr.length, 0);
}

function countComponents(rels: ComponentRelationship[]): number {
  const set = new Set<string>();
  rels.forEach((r) => { set.add(r.source); set.add(r.target); });
  return set.size;
}

/** Reads the ?tab= URL param, validates it, and returns a valid TabId. */
function resolveInitialTab(): TabId {
  if (typeof window === 'undefined') return 'analysis';
  const param = new URLSearchParams(window.location.search).get('tab') as TabId | null;
  if (param && TABS.some(t => t.id === param)) return param;
  return 'analysis';
}

/** Syncs the active tab into the URL without a page reload. */
function syncTabToUrl(tab: TabId) {
  if (typeof window === 'undefined') return;
  const url = new URL(window.location.href);
  url.searchParams.set('tab', tab);
  window.history.replaceState({}, '', url.toString());
}

// ── Component ─────────────────────────────────────────────────────────────────

export const getRepoFromUrl = (repoParam?: string): string => {
  if (repoParam) return repoParam.replace('-', '/');
  if (typeof window !== 'undefined') {
    const urlParams = new URLSearchParams(window.location.search);
    const owner = urlParams.get('owner');
    const repo  = urlParams.get('repo');
    if (owner && repo) return `${owner}/${repo}`;
    const repoQuery = urlParams.get('repo');
    if (repoQuery) return repoQuery;
  }
  return 'unknown/repo';
};

export const AnalysisDashboard: React.FC<DashboardProps> = ({ repoParam }) => {
  const [repoName, setRepoName]       = useState(() => getRepoFromUrl(repoParam));
  const [data, setData]               = useState<AnalysisData | null>(null);
  const [loading, setLoading]         = useState(true);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [activeTab, setActiveTab]     = useState<TabId>(resolveInitialTab);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  /** Epoch ms of the most recent index for this repo — drives "indexed X ago". */
  const [indexedAt, setIndexedAt]     = useState<number | null>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  /** Question handed to the Chat tab from another panel. */
  const [pendingChatPrompt, setPendingChatPrompt] = useState<{ text: string; token: number } | null>(null);
  /** Node the File Graph tab should focus on. */
  const [graphFocus, setGraphFocus] = useState<{ path: string; token: number } | null>(null);

  // Impact Analysis state
  const [impactData, setImpactData]   = useState<any | null>(null);
  const [impactLoading, setImpactLoading] = useState(false);
  const [issueInput, setIssueInput]   = useState('');
  const [impactError, setImpactError] = useState<string | null>(null);

  // Lazy mount: tracks which tabs have been visited (so we only mount on first visit)
  const [mountedTabs, setMountedTabs] = useState<Set<TabId>>(new Set([resolveInitialTab()]));

  const circularDependencies = useMemo(() => {
    if (!data || !data.architecture || !data.architecture.relationships) return [];
    const adj: Record<string, string[]> = {};
    data.architecture.relationships.forEach((r) => {
      if (!adj[r.source]) adj[r.source] = [];
      adj[r.source].push(r.target);
    });

    const cycles: string[][] = [];
    const visited = new Set<string>();
    const recStack = new Set<string>();
    const parent: Record<string, string> = {};

    const dfs = (node: string): void => {
      visited.add(node);
      recStack.add(node);

      const neighbors = adj[node] || [];
      for (const neighbor of neighbors) {
        if (!visited.has(neighbor)) {
          parent[neighbor] = node;
          dfs(neighbor);
        } else if (recStack.has(neighbor)) {
          const cycle = [neighbor];
          let curr = node;
          while (curr !== neighbor && curr) {
            cycle.push(curr);
            curr = parent[curr];
          }
          cycle.push(neighbor);
          cycle.reverse();
          cycles.push(cycle);
        }
      }
      recStack.delete(node);
    };

    Object.keys(adj).forEach((node) => {
      if (!visited.has(node)) dfs(node);
    });
    return cycles;
  }, [data]);

  /**
   * Real distribution series for the KPI sparklines. These plot actual indexed
   * data (largest first), not synthetic trends — a repository has no historical
   * series available at this point in the flow.
   */
  const fileDistribution = useMemo(() => {
    if (!data?.analysis?.structure) return [];
    return Object.values(data.analysis.structure)
      .map((files) => files.length)
      .sort((a, b) => b - a)
      .slice(0, 16);
  }, [data]);

  const componentDistribution = useMemo(() => {
    const rels = data?.architecture?.relationships;
    if (!rels || rels.length === 0) return [];
    const degree: Record<string, number> = {};
    rels.forEach((r) => {
      degree[r.source] = (degree[r.source] ?? 0) + 1;
      degree[r.target] = (degree[r.target] ?? 0) + 1;
    });
    return Object.values(degree).sort((a, b) => b - a).slice(0, 16);
  }, [data]);

  const entryPoints = useMemo(() => {
    if (!data || !data.analysis || !data.analysis.structure) return [];
    const entryFiles: string[] = [];
    const entryPatterns = [
      /\bmain\.(py|go|rs|ts|js)$/i,
      /\bapp\.(py|ts|js)$/i,
      /\bindex\.(ts|js|tsx|jsx)$/i,
      /\bapi\.(py|ts|js)$/i,
      /\bserver\.(ts|js)$/i,
      /\bmanage\.py$/i
    ];
    Object.values(data.analysis.structure).forEach((files) => {
      files.forEach((f) => {
        const parts = f.split('/');
        const fileName = parts[parts.length - 1];
        if (entryPatterns.some((pat) => pat.test(fileName))) {
          entryFiles.push(f);
        }
      });
    });
    // Full list — callers slice for display so counts stay accurate.
    return entryFiles;
  }, [data]);

  const handleTabChange = (tab: TabId) => {
    setActiveTab(tab);
    setMountedTabs(prev => new Set([...prev, tab]));
    syncTabToUrl(tab);
  };

  /** Sends a file-specific question to the Chat tab and switches to it. */
  const handleAskAboutFile = (filePath: string) => {
    setPendingChatPrompt({
      text: `Explain the file \`${filePath}\`. What is its responsibility, what does it depend on, and what depends on it?`,
      token: Date.now(),
    });
    handleTabChange('chat');
  };

  /** Focuses the File Graph tab on a file's dependency neighbourhood. */
  const handleViewInGraph = (filePath: string) => {
    setSelectedFile(filePath);
    setGraphFocus({ path: filePath, token: Date.now() });
    handleTabChange('graph');
  };

  /**
   * Searchable index for the command palette, built entirely from data already
   * fetched for this view — the palette issues no additional requests.
   */
  const commandItems = useMemo<CommandItem[]>(() => {
    const items: CommandItem[] = [];

    // Destinations — every dashboard tab is reachable by name.
    TABS.forEach((tab) => {
      items.push({
        id: `nav:${tab.id}`,
        label: tab.label,
        sublabel: `Go to ${tab.group}`,
        group: 'Destinations',
        icon: COMMAND_ICONS.navigate,
        keywords: `${tab.group} ${tab.id} navigate open goto`,
        run: () => handleTabChange(tab.id),
      });
    });

    if (!data) return items;

    // Files — selecting one reveals it in the tree/context panel.
    Object.entries(data.analysis.structure).forEach(([directory, files]) => {
      files.forEach((file) => {
        items.push({
          id: `file:${file}`,
          label: file.split('/').pop() || file,
          sublabel: file,
          group: 'Files',
          icon: COMMAND_ICONS.file,
          keywords: `${directory} ${file}`,
          run: () => setSelectedFile(file),
        });
      });
    });

    // Reading path steps.
    data.architecture.reading_order.forEach((step, index) => {
      items.push({
        id: `reading:${index}:${step}`,
        label: step.split('/').pop() || step,
        sublabel: `Step ${index + 1} · ${step}`,
        group: 'Reading Path',
        icon: COMMAND_ICONS.reading,
        keywords: `reading order onboarding step ${index + 1} ${step}`,
        run: () => { setSelectedFile(step); handleTabChange('reading_path'); },
      });
    });

    // Architecture components.
    const componentNames = new Set<string>();
    data.architecture.relationships.forEach((rel) => {
      componentNames.add(rel.source);
      componentNames.add(rel.target);
    });
    componentNames.forEach((name) => {
      items.push({
        id: `component:${name}`,
        label: name,
        sublabel: 'Architecture component',
        group: 'Components',
        icon: COMMAND_ICONS.component,
        keywords: `component module architecture ${name}`,
        run: () => handleTabChange('graph'),
      });
    });

    // Dependencies and detected stack.
    data.analysis.dependencies.forEach((dep) => {
      items.push({
        id: `dep:${dep}`,
        label: dep,
        sublabel: 'Dependency',
        group: 'Dependencies',
        icon: COMMAND_ICONS.dependency,
        keywords: `package dependency library ${dep}`,
        run: () => handleTabChange('analysis'),
      });
    });

    data.analysis.tech_stack.forEach((tech) => {
      items.push({
        id: `tech:${tech}`,
        label: tech,
        sublabel: 'Technology',
        group: 'Tech Stack',
        icon: COMMAND_ICONS.tech,
        keywords: `stack technology framework language ${tech}`,
        run: () => handleTabChange('analysis'),
      });
    });

    return items;
  }, [data]);

  // Sync state if repoParam changes from parent
  useEffect(() => {
    const nextRepo = getRepoFromUrl(repoParam);
    setRepoName(nextRepo);
  }, [repoParam]);

  // Sync state on popstate (browser back/forward buttons)
  useEffect(() => {
    const handlePopState = () => {
      const tab = resolveInitialTab();
      setActiveTab(tab);
      setMountedTabs(prev => new Set([...prev, tab]));
      
      const repoVal = getRepoFromUrl(repoParam);
      setRepoName(repoVal);
    };
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, [repoParam]);

  // Global Cmd/Ctrl+K to open the command palette.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() !== 'k' || !(event.metaKey || event.ctrlKey)) return;
      event.preventDefault();
      setPaletteOpen((prev) => !prev);
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  useEffect(() => {
    const [owner, name] = repoName.split('/');
    if (!owner || !name || owner === 'unknown' || name === 'repo') {
      setErrorMessage('Repository information missing or invalid. Redirecting to home.');
      setTimeout(() => (window.location.href = '/'), 2000);
      setLoading(false);
      return;
    }
    
    // Clear stale state for the previous repository
    setData(null);
    setSelectedFile(null);
    setImpactData(null);
    setIssueInput('');
    setImpactError(null);
    setLoading(true);
    setErrorMessage(null);

    if (typeof window !== 'undefined') {
      const now = Date.now();
      localStorage.setItem('activeRepo', repoName);
      localStorage.setItem(`lastAnalysed:${repoName}`, String(now));
      setIndexedAt(now);
      // Dispatch custom event to notify Astro header navigation that activeRepo changed
      window.dispatchEvent(new CustomEvent('active-repo-changed', { detail: repoName }));
    }

    fetch(apiUrl(`/api/v1/analysis/${owner}/${name}`))
      .then((res) => {
        if (!res.ok) throw new Error('Failed to fetch repository details');
        return res.json();
      })
      .then((resData) => { setData(resData); setLoading(false); })
      .catch((err) => { setErrorMessage(err.message); setLoading(false); });
  }, [repoName]);

  const handleRunImpactAnalysis = (overrideText?: string) => {
    const queryText = overrideText !== undefined ? overrideText : issueInput;
    if (!queryText.trim()) return;
    if (overrideText !== undefined) setIssueInput(overrideText);
    setImpactLoading(true);
    setImpactError(null);

    fetch(apiUrl('/api/v1/impact-analysis'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repo: repoName, issue: queryText }),
    })
      .then(async (res) => {
        if (!res.ok) {
          const errData = await res.json().catch(() => ({}));
          throw new Error(extractErrorMessage(errData) || 'Failed to analyze impact');
        }
        return res.json();
      })
      .then((resData) => { setImpactData(resData); setImpactLoading(false); })
      .catch((err) => { setImpactError(extractErrorMessage(err)); setImpactLoading(false); });
  };

  // ── Loading skeleton ───────────────────────────────────────────────────────
  if (loading) {
    return (
      <SkeletonGroup label="Loading repository analysis">
        <SkeletonDashboard />
      </SkeletonGroup>
    );
  }

  // ── Hard error state ───────────────────────────────────────────────────────
  if (!data) {
    return (
      <div className="py-12 max-w-lg mx-auto w-full">
        <EmptyState
          tone="danger"
          icon={<AlertCircle className="h-6 w-6" aria-hidden="true" />}
          title="Analysis could not be loaded"
          description={
            <div className="text-left space-y-3 mt-2 font-sans">
              <p className="text-xs text-text-muted leading-relaxed">
                {errorMessage ?? 'The repository analysis is unavailable or failed to process.'}
              </p>
              <div className="p-3.5 rounded-lg border border-danger/20 bg-danger/5 space-y-1.5">
                <span className="text-[10px] font-bold font-mono uppercase tracking-wider text-danger block">
                  Possible Causes
                </span>
                <ul className="list-disc pl-4 text-[11px] text-text-muted/95 space-y-1 leading-relaxed">
                  <li>Private repository without configuration</li>
                  <li>Invalid or malformed GitHub repository URL</li>
                  <li>GitHub API rate limit or quota exceeded</li>
                  <li>Temporary network failure or backend server is offline</li>
                </ul>
              </div>
            </div>
          }
          action={
            <div className="flex gap-3 justify-center mt-2 select-none">
              <button
                type="button"
                onClick={() => window.location.reload()}
                className="btn-primary px-4 py-2 text-xs"
              >
                Retry Loading
              </button>
              <button
                type="button"
                onClick={() => (window.location.href = '/')}
                className="btn-ghost px-4 py-2 text-xs"
              >
                Back to home
              </button>
            </div>
          }
        />
      </div>
    );
  }

  const { analysis, architecture } = data;

  const fileCount       = countFiles(analysis.structure);
  const componentCount  = countComponents(architecture.relationships);
  const languageCount   = analysis.tech_stack.length;
  const dependencyCount = analysis.dependencies.length;
  const readingSteps    = architecture.reading_order.length;
  const [owner, repoSlug] = repoName.split('/');

  // Derived presentation metrics — centralised so hero and cards always agree.
  const complexity      = computeComplexity({ fileCount, componentCount, dependencyCount });
  const primaryLanguage = detectPrimaryLanguage(analysis.tech_stack);
  const readingMinutes  = estimateReadingMinutes(readingSteps);
  const directoryCount  = Object.keys(analysis.structure).length;
  const indexedAgo      = relativeTimeFrom(indexedAt);

  const insights = deriveInsights({
    fileCount,
    directoryCount,
    dependencyCount,
    techStack: analysis.tech_stack,
    structure: analysis.structure,
    entryPointCount: entryPoints.length,
    cycleCount: circularDependencies.length,
    componentCount,
    relationshipCount: architecture.relationships.length,
    readingSteps,
    readingMinutes,
  });

  return (
    <div className="space-y-6 w-full py-4 fade-up">
      <RepoCommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        items={commandItems}
        scopeLabel={repoName}
      />

      {/* ── REPO CONTEXT HEADER ──────────────────────────────────────────────── */}
      <header className="space-y-6">
        <RepoHero
          onOpenCommandPalette={() => setPaletteOpen(true)}
          owner={owner}
          repoSlug={repoSlug}
          summary={architecture.summary}
          primaryLanguage={primaryLanguage}
          readingMinutes={readingMinutes}
          complexity={complexity}
          indexedAt={indexedAt}
          onRefresh={() => window.location.reload()}
          onExportReport={() => handleTabChange('report')}
        />

        <ExecutiveInsights insights={insights} />

        {/* KPI metric strip */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
          <MetricCard
            tone="primary"
            icon={<FileText className="h-4 w-4" />}
            label="Files Indexed"
            value={<AnimatedNumber value={fileCount} />}
            hint={`${directoryCount} ${directoryCount === 1 ? 'directory' : 'directories'}`}
            subHint={`~${Math.max(1, Math.round(fileCount / Math.max(1, directoryCount)))} files per directory`}
            footnote={indexedAgo ? `Indexed ${indexedAgo}` : 'Indexed this session'}
            spark={fileDistribution}
            sparkLabel="File count per directory, largest first"
          />
          <MetricCard
            tone="info"
            icon={<Code2 className="h-4 w-4" />}
            label="Languages"
            value={<AnimatedNumber value={languageCount} />}
            hint={analysis.tech_stack.slice(0, 3).join(' · ') || '—'}
            subHint={primaryLanguage ? `Primary: ${primaryLanguage}` : undefined}
            footnote={`${languageCount} stack ${languageCount === 1 ? 'signal' : 'signals'} detected`}
          />
          <MetricCard
            tone="success"
            icon={<Network className="h-4 w-4" />}
            label="Components"
            value={<AnimatedNumber value={componentCount} />}
            hint={`${architecture.relationships.length} relationships`}
            subHint={
              circularDependencies.length > 0
                ? `${circularDependencies.length} cycle${circularDependencies.length === 1 ? '' : 's'} detected`
                : 'No cycles detected'
            }
            footnote="From architecture graph"
            spark={componentDistribution}
            sparkLabel="Relationships per component, most connected first"
            onClick={() => handleTabChange('graph')}
          />
          <MetricCard
            tone="warn"
            icon={<Box className="h-4 w-4" />}
            label="Dependencies"
            value={<AnimatedNumber value={dependencyCount} />}
            hint="Resolved from manifests"
            subHint={`Complexity ${complexity.label.toLowerCase()} · ${complexity.score}/100`}
            footnote="External package surface"
          />
          <MetricCard
            tone="primary"
            icon={<DoorOpen className="h-4 w-4" />}
            label="Reading Steps"
            value={<AnimatedNumber value={readingSteps} />}
            hint="Ranked onboarding flow"
            subHint={`~${formatDuration(readingMinutes)} to complete`}
            footnote="Open reading path →"
            onClick={() => handleTabChange('reading_path')}
          />
        </div>
      </header>

      {/* ── WORKSPACE ────────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        <div className="lg:col-span-3 xl:col-span-3 space-y-4">
          <FileTree structure={analysis.structure} onFileSelect={setSelectedFile} />
          {selectedFile && (
            <div className="card p-4 space-y-3 fade-up">
              <span className="text-primary font-bold uppercase tracking-wider block text-[10px] font-mono">
                Selected Node Context
              </span>
              <div className="flex flex-wrap items-center gap-1.5 text-[10px] font-mono text-text-muted select-none bg-canvas/30 p-2 rounded-lg border border-border/60">
                {selectedFile.split('/').map((seg, i, arr) => {
                  const isLast = i === arr.length - 1;
                  return (
                    <React.Fragment key={i}>
                      <span className={isLast ? 'text-text font-semibold' : 'text-text-muted hover:text-text cursor-pointer transition-colors'} title={arr.slice(0, i + 1).join('/')}>
                        {seg}
                      </span>
                      {!isLast && <span>/</span>}
                    </React.Fragment>
                  );
                })}
              </div>
              <p className="text-text-muted text-xs font-sans leading-relaxed">
                Pass this file context to the Issue Mapper or Chat companion to discuss targeted modifications.
              </p>
            </div>
          )}
        </div>

        <div className="lg:col-span-9 xl:col-span-9 space-y-6 min-w-0">
          <Tabs items={TABS} active={activeTab} onChange={handleTabChange} />

          {/* Tab panels — mount-on-first-visit, stay mounted to preserve state */}
          {TABS.map(({ id }) => (
            <div
              key={id}
              id={`tabpanel-${id}`}
              role="tabpanel"
              aria-labelledby={id}
              hidden={activeTab !== id}
              className="space-y-6"
            >
              {mountedTabs.has(id) && (
                <>
                  {/* ── Overview ── */}
                  {id === 'analysis' && (
                    <>
                      {/* Quick-action chips */}
                      <div className="flex flex-wrap gap-2" role="navigation" aria-label="Quick navigation">
                        {[
                          { label: 'Explore Graph', tab: 'graph' as TabId },
                          { label: 'Read Path',     tab: 'reading_path' as TabId },
                          { label: 'Health Report', tab: 'report' as TabId },
                          { label: 'Ask Chat',      tab: 'chat' as TabId },
                        ].map(({ label, tab }) => (
                          <button
                            key={tab}
                            type="button"
                            onClick={() => handleTabChange(tab)}
                            className="inline-flex items-center gap-1.5 text-xs font-medium font-sans
                                       px-3 py-1.5 rounded-md border border-primary/30 bg-primary/5
                                       text-primary hover:bg-primary/10 transition-colors
                                       focus-visible:outline-none focus-visible:shadow-ring"
                          >
                            {label}
                            <ArrowRight className="h-3 w-3" aria-hidden="true" />
                          </button>
                        ))}
                      </div>

                      <div className="card p-6 space-y-3">
                        <h2 className="panel-title">
                          <Info className="h-4 w-4 text-primary" aria-hidden="true" /> Codebase Summary
                        </h2>
                        <p className="text-sm text-text leading-relaxed font-sans">
                          {architecture.summary}
                        </p>
                      </div>

                      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 items-start">
                        <TechStackPanel techStack={analysis.tech_stack} />
                        <DependencyExplorer dependencies={analysis.dependencies} />
                      </div>

                      {/* Codebase Health & Warnings Grid */}
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                        {/* Complexity Index Card */}
                        <div className="card p-4 space-y-2.5">
                          <span className="text-[10px] uppercase font-mono tracking-widest text-text-subtle font-semibold block">
                            Complexity Index
                          </span>
                          <div className="flex items-baseline gap-2">
                            <span className="text-2xl font-extrabold text-text font-mono">
                              {complexity.score}
                            </span>
                            <span className="text-[9px] font-bold text-primary font-mono uppercase">
                              {complexity.label} density
                            </span>
                          </div>
                          <p className="text-[10px] text-text-muted leading-relaxed font-sans">
                            Complexity proxy computed from indexing density and system integration links.
                          </p>
                        </div>

                        {/* Circular Dependency Card */}
                        <div className="card p-4 space-y-2.5">
                          <span className="text-[10px] uppercase font-mono tracking-widest text-text-subtle font-semibold block">
                            Architecture Status
                          </span>
                          <div className="flex items-center gap-2">
                            {circularDependencies.length > 0 ? (
                              <>
                                <span className="h-2 w-2 rounded-full bg-warn animate-pulse" aria-hidden="true" />
                                <span className="text-xs font-bold text-warn font-mono uppercase">
                                  {circularDependencies.length} cycle(s) found
                                </span>
                              </>
                            ) : (
                              <>
                                <span className="h-2 w-2 rounded-full bg-success" aria-hidden="true" />
                                <span className="text-xs font-bold text-success font-mono uppercase">
                                  Acyclic / Stable
                                </span>
                              </>
                            )}
                          </div>
                          <p className="text-[10px] text-text-muted leading-relaxed font-sans">
                            {circularDependencies.length > 0
                              ? 'Circular component dependencies detected. Graph analysis indicates circular linkages.'
                              : 'No circular component relationships detected. Clean system architecture.'}
                          </p>
                        </div>

                        {/* Entry Points Card */}
                        <div className="card p-4 space-y-2.5">
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-[10px] uppercase font-mono tracking-widest text-text-subtle font-semibold">
                              Inferred Entry Points
                            </span>
                            {entryPoints.length > 0 && (
                              <span className="text-[10px] font-mono text-text-subtle shrink-0">
                                {entryPoints.length}
                              </span>
                            )}
                          </div>
                          {entryPoints.length > 0 ? (
                            <div className="flex flex-wrap gap-1.5">
                              {entryPoints.slice(0, 6).map((ep) => (
                                <button
                                  key={ep}
                                  type="button"
                                  onClick={() => setSelectedFile(ep)}
                                  className="text-[9px] font-mono bg-canvas border border-primary/20 hover:border-primary/50
                                             text-primary px-1.5 py-0.5 rounded truncate max-w-full transition-colors
                                             focus-visible:outline-none focus-visible:shadow-ring"
                                  title={`Select ${ep} in the file tree`}
                                >
                                  {ep.split('/').pop()}
                                </button>
                              ))}
                            </div>
                          ) : (
                            <span className="text-[10px] text-text-muted font-mono italic">None detected</span>
                          )}
                          <p className="text-[10px] text-text-muted leading-relaxed font-sans">
                            Click a file chip to select the file within the project tree view.
                          </p>
                        </div>
                      </div>

                      {/* Cross-navigate to health report if available */}
                      <button
                        type="button"
                        onClick={() => handleTabChange('report')}
                        className="w-full card p-4 flex items-center justify-between hover:border-primary/40 hover:-translate-y-0.5 transition-all text-left"
                        aria-label="View Health Report"
                      >
                        <div className="flex items-center gap-3">
                          <div className="h-9 w-9 rounded-lg bg-primary/10 border border-primary/30 flex items-center justify-center">
                            <BarChart2 className="h-4 w-4 text-primary" aria-hidden="true" />
                          </div>
                          <div>
                            <div className="text-sm font-semibold text-text">Repository Health Report</div>
                            <div className="text-xs text-text-muted font-sans">Architecture · API · Hygiene · Onboarding scores</div>
                          </div>
                        </div>
                        <ArrowRight className="h-4 w-4 text-text-muted" aria-hidden="true" />
                      </button>

                      <div className="card p-6 space-y-3">
                        <h2 className="panel-title">
                          <Cpu className="h-4 w-4 text-primary" aria-hidden="true" /> Architecture Component Relationships
                        </h2>
                        {architecture.relationships.length > 0 ? (
                          <div className="space-y-3">
                            {architecture.relationships.map((rel, idx) => (
                              <div key={idx} className="border border-border bg-canvas/40 rounded-lg p-3 text-xs space-y-2">
                                <div className="flex flex-wrap items-center gap-2 font-mono">
                                  <span className="text-text font-semibold">{rel.source}</span>
                                  <Badge tone="primary">{rel.relationship_type}</Badge>
                                  <span className="text-text font-semibold">{rel.target}</span>
                                </div>
                                <p className="text-text-muted leading-relaxed font-sans">{rel.description}</p>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <EmptyState
                            compact
                            icon={<Network className="h-5 w-5" aria-hidden="true" />}
                            title="No component relationships detected"
                            description={
                              <span>
                                The architecture agent did not find cross-component links, which usually
                                means this repository contains largely independent modules or services.
                                File-level structure is still fully indexed.
                              </span>
                            }
                            secondaryHelp="Component links are inferred from imports between top-level packages, so flat or single-module layouts often produce none."
                            action={
                              <div className="flex flex-wrap gap-2 justify-center">
                                <button
                                  type="button"
                                  onClick={() => handleTabChange('graph')}
                                  className="btn-ghost text-xs"
                                >
                                  <Code2 className="h-3.5 w-3.5" aria-hidden="true" />
                                  Inspect file graph
                                </button>
                                <button
                                  type="button"
                                  onClick={() => handleTabChange('call_graph')}
                                  className="btn-ghost text-xs"
                                >
                                  <Workflow className="h-3.5 w-3.5" aria-hidden="true" />
                                  Trace call graph
                                </button>
                                <button
                                  type="button"
                                  onClick={() => handleTabChange('reading_path')}
                                  className="btn-ghost text-xs"
                                >
                                  <BookOpen className="h-3.5 w-3.5" aria-hidden="true" />
                                  Follow reading path
                                </button>
                              </div>
                            }
                          />
                        )}
                      </div>
                    </>
                  )}

                  {/* ── Structure ── */}
                  {id === 'graph' && (
                    <Suspense fallback={<SkeletonGraph />}>
                      <InteractiveDependencyGraph repoName={repoName} focusRequest={graphFocus} />
                    </Suspense>
                  )}
                  {id === 'call_graph'  && <CallGraphAnalyzer  repoName={repoName} />}
                  {id === 'api_surface' && <APISurfaceAnalyzer repoName={repoName} />}

                  {/* ── Understand ── */}
                  {id === 'reading_path' && (
                    <ReadingOrderTimeline
                      repoName={repoName}
                      onAskAboutFile={handleAskAboutFile}
                      onViewInGraph={handleViewInGraph}
                    />
                  )}
                  {id === 'chat' && (
                    <div className="min-h-[600px] flex flex-col">
                      <ChatInterface
                        repoName={repoName}
                        pendingPrompt={pendingChatPrompt}
                        onPendingPromptConsumed={() => setPendingChatPrompt(null)}
                      />
                    </div>
                  )}

                  {/* ── Quality ── */}
                  {id === 'report'     && <ReportPanel      repoName={repoName} />}
                  {id === 'dead_code'  && <DeadCodeAnalyzer  repoName={repoName} />}
                  {id === 'issues'     && <IssueMapper       repoName={repoName} />}

                  {/* ── History & PRs ── */}
                  {id === 'git_history'        && <GitHistoryAnalyzer repoName={repoName} />}
                  {id === 'pr_intelligence'    && <PRIntelligence     repoName={repoName} />}
                  {id === 'architecture_drift' && <ArchitectureDrift  repoName={repoName} />}
                  {id === 'impact_analysis' && (
                    <div className="space-y-4">
                      {impactLoading ? (
                        <SkeletonGroup label="Analyzing change impact">
                          <div className="space-y-4"><SkeletonCard /><SkeletonCard /></div>
                        </SkeletonGroup>
                      ) : impactData ? (
                        <Suspense fallback={<SkeletonGraph />}>
                          <ImpactAnalysisGraph
                            repoName={repoName}
                            impactData={impactData}
                            onReset={() => setImpactData(null)}
                          />
                        </Suspense>
                      ) : (
                        <div className="card p-6 space-y-5">
                          <div className="space-y-2">
                            <h2 className="panel-title">
                              <Target className="h-4 w-4 text-primary" aria-hidden="true" /> Predictive Impact Analysis
                            </h2>
                            <p className="text-sm text-text-muted font-sans leading-normal max-w-2xl">
                              Describe a proposed code modification or feature request to trace import propagation
                              and discover risk metrics across architectural layers.
                            </p>
                          </div>

                          <div className="flex flex-col sm:flex-row gap-3">
                            <label htmlFor="impact-query" className="sr-only">Issue text</label>
                            <textarea
                              id="impact-query"
                              value={issueInput}
                              onChange={(e) => setIssueInput(e.target.value)}
                              placeholder="e.g., Add GitHub OAuth Login, or Fix SQLite Timeout Issue"
                              rows={2}
                              className="input flex-grow resize-none"
                            />
                            <Button
                              type="button"
                              onClick={() => handleRunImpactAnalysis()}
                              disabled={impactLoading || !issueInput.trim()}
                              className="shrink-0"
                            >
                              Run Analysis
                            </Button>
                          </div>

                          {impactError && (
                            <div role="alert" className="text-xs font-sans text-danger bg-danger/10 border border-danger/30 p-3 rounded-lg">
                              {impactError}
                            </div>
                          )}

                          <div className="border-t border-border pt-4 space-y-3">
                            <span className="panel-title">Quick Scenario Presets</span>
                            <div className="flex flex-wrap gap-2.5">
                              {[
                                repoName.includes('fastapi') ? 'Add API key authentication' : 'Add GitHub OAuth Login',
                                'Fix SQLite Timeout Issue',
                                'Refactor Duplicate HTML Templates',
                              ].map((preset) => (
                                <button
                                  key={preset}
                                  type="button"
                                  onClick={() => handleRunImpactAnalysis(preset)}
                                  className="text-xs font-sans bg-canvas border border-border hover:border-primary/40
                                             px-3 py-2 rounded-md text-text-muted hover:text-text transition-colors
                                             flex items-center gap-1.5 focus-visible:outline-none focus-visible:shadow-ring"
                                >
                                  <HelpCircle className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
                                  <span>{preset}</span>
                                </button>
                              ))}
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default AnalysisDashboard;

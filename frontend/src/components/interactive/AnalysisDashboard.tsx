import React, { useState, useEffect, useMemo, useCallback, Suspense, lazy } from 'react';
import { apiUrl, extractErrorMessage } from '../../lib/api';
import FileTree from './FileTree';
import { useRepoHealth, type CentralityHub } from './RepoHero';
import { RepositoryOverview } from './RepositoryOverview';
import { Reveal } from '../ui/Reveal';
import { FilePath } from '../ui/FilePath';
import { inferFileRole } from '../../lib/fileRole';
import { RepoCommandPalette, COMMAND_ICONS, type CommandItem } from './RepoCommandPalette';
import { deriveInsights } from '../../lib/repoInsights';
import { Tabs, type TabItem } from './Tabs';
import { EmptyState } from '../ui/EmptyState';
import { SkeletonCard, SkeletonGroup, SkeletonGraph, SkeletonDashboard } from '../ui/Skeleton';
import {
  computeComplexity, detectPrimaryLanguage, estimateReadingMinutes,
  relativeTimeFrom,
} from '../../lib/repoMetrics';
import {
  Layers, Code2, BookOpen, Cpu, Target,
  MessageSquareCode, GitPullRequest, GitCompare, Trash2, FileText,
  AlertCircle, GitCommit, Workflow, Globe, ArrowRight,
} from 'lucide-react';

// ── Lazy-loaded heavy tab panels & graph visualizers ─────────────────────────
const IssueMapper = lazy(() => import('./IssueMapper'));
const ChatInterface = lazy(() => import('./ChatInterface'));
const ReadingOrderTimeline = lazy(() => import('./ReadingOrderTimeline').then((m) => ({ default: m.ReadingOrderTimeline })));
const PRIntelligence = lazy(() => import('./PRIntelligence'));
const ArchitectureDrift = lazy(() => import('./ArchitectureDrift').then((m) => ({ default: m.ArchitectureDrift })));
const DeadCodeAnalyzer = lazy(() => import('./DeadCodeAnalyzer').then((m) => ({ default: m.DeadCodeAnalyzer })));
const GitHistoryAnalyzer = lazy(() => import('./GitHistoryAnalyzer').then((m) => ({ default: m.GitHistoryAnalyzer })));
const CallGraphAnalyzer = lazy(() => import('./CallGraphAnalyzer').then((m) => ({ default: m.CallGraphAnalyzer })));
const APISurfaceAnalyzer = lazy(() => import('./APISurfaceAnalyzer').then((m) => ({ default: m.APISurfaceAnalyzer })));
const ReportPanel = lazy(() => import('./ReportPanel'));
const ImpactAnalysisWorkspace = lazy(() => import('./ImpactAnalysisWorkspace'));
import { InteractiveDependencyGraph } from './graph/InteractiveDependencyGraph';

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
  // ── Quality & Reliability ──
  { id: 'report',             label: 'Health Report', icon: FileText,        group: 'Quality & Reliability' },
  { id: 'dead_code',          label: 'Dead Code',     icon: Trash2,          group: 'Quality & Reliability' },
  { id: 'issues',             label: 'Issues',        icon: Cpu,             group: 'Quality & Reliability' },
  // ── History & Change ──
  { id: 'git_history',        label: 'Git History',   icon: GitCommit,       group: 'History & Change' },
  { id: 'pr_intelligence',    label: 'PR Risk',       icon: GitPullRequest,  group: 'History & Change' },
  { id: 'architecture_drift', label: 'PR Drift',      icon: GitCompare,      group: 'History & Change' },
  { id: 'impact_analysis',    label: 'Impact',        icon: Target,          group: 'History & Change' },
];

const PRIMARY_TAB_IDS = new Set<TabId>(['analysis', 'reading_path', 'chat', 'graph', 'call_graph', 'api_surface']);

function countFiles(structure: Record<string, string[]>): number {
  return Object.values(structure || {}).reduce((sum, arr) => sum + (arr ? arr.length : 0), 0);
}

function countComponents(rels: ComponentRelationship[]): number {
  const set = new Set<string>();
  (rels || []).forEach((r) => { if (r?.source) set.add(r.source); if (r?.target) set.add(r.target); });
  return set.size;
}

/** Reads the ?tab= URL param, validates it, and returns a valid TabId. */
function resolveInitialTab(): TabId {
  if (typeof window === 'undefined') return 'analysis';
  const param = new URLSearchParams(window.location.search).get('tab') as TabId | null;
  if (param && TABS.some(t => t.id === param)) return param;
  return 'analysis';
}

/** Reads the ?file= or ?focus= URL param for deep-linking into graph/inspector. */
function resolveInitialFile(): string | null {
  if (typeof window === 'undefined') return null;
  const params = new URLSearchParams(window.location.search);
  const file = params.get('file') || params.get('focus') || null;
  return file ? decodeURIComponent(file) : null;
}

/** Syncs the active tab (and optional deep-linked file) into the URL without a page reload. */
function syncTabToUrl(tab: TabId, file?: string | null) {
  if (typeof window === 'undefined') return;
  const url = new URL(window.location.href);
  url.searchParams.set('tab', tab);
  if (tab === 'graph' && file) {
    url.searchParams.set('file', file);
    url.searchParams.delete('focus');
  } else if (tab !== 'graph') {
    url.searchParams.delete('file');
    url.searchParams.delete('focus');
  }
  window.history.replaceState({}, '', url.toString());
}

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

// ── Component ─────────────────────────────────────────────────────────────────

export const AnalysisDashboard: React.FC<DashboardProps> = ({ repoParam }) => {
  const [repoName, setRepoName]       = useState(() => getRepoFromUrl(repoParam));
  const [data, setData]               = useState<AnalysisData | null>(null);
  const [loading, setLoading]         = useState(true);
  const [selectedFile, setSelectedFile] = useState<string | null>(() => resolveInitialFile());
  const [activeTab, setActiveTab]     = useState<TabId>(resolveInitialTab);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  /** Epoch ms of the most recent index for this repo — drives "indexed X ago". */
  const [indexedAt, setIndexedAt]     = useState<number | null>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  /** Question handed to the Chat tab from another panel. */
  const [pendingChatPrompt, setPendingChatPrompt] = useState<{ text: string; token: number } | null>(null);
  /** Node the File Graph tab should focus on. */
  const [graphFocus, setGraphFocus] = useState<{ path: string; token: number } | null>(() => {
    const initialFile = resolveInitialFile();
    return initialFile ? { path: initialFile, token: Date.now() } : null;
  });

  // Lazy mount: tracks which tabs have been visited (so we only mount on first visit)
  const [mountedTabs, setMountedTabs] = useState<Set<TabId>>(new Set([resolveInitialTab()]));

  const [owner, repoSlug] = useMemo(() => {
    const parts = repoName.split('/');
    return [parts[0] || 'unknown', parts[1] || 'repo'];
  }, [repoName]);

  const { health, state: healthState } = useRepoHealth(owner, repoSlug);

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
    return entryFiles;
  }, [data]);

  const groupedEntryPoints = useMemo(() => {
    const byName = new Map<string, string[]>();
    entryPoints.forEach((path) => {
      const name = path.split('/').pop() || path;
      const existing = byName.get(name);
      if (existing) existing.push(path);
      else byName.set(name, [path]);
    });

    return Array.from(byName.entries())
      .map(([name, paths]) => ({
        name: paths.length === 1 ? paths[0] : name,
        paths,
        count: paths.length,
      }))
      .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
  }, [entryPoints]);

  const handleTabChange = (tab: TabId, file?: string | null) => {
    setActiveTab(tab);
    setMountedTabs(prev => new Set([...prev, tab]));
    syncTabToUrl(tab, file !== undefined ? file : (tab === 'graph' ? selectedFile : null));
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('aria-tab-changed', { detail: { tab } }));
    }
  };

  /** Sends a file-specific question to the Chat tab and switches to it. */
  const handleAskAboutFile = (filePath: string) => {
    setPendingChatPrompt({
      text: `Explain the file \`${filePath}\`. What is its responsibility, what does it depend on, and what depends on it?`,
      token: Date.now(),
    });
    handleTabChange('chat');
  };

  // ── Sync with graph selection events ──────────────────────────────────────
  useEffect(() => {
    const handleWorkspaceFileSelect = (evt: Event) => {
      const customEvt = evt as CustomEvent<{ path: string | null }>;
      if (customEvt.detail && customEvt.detail.path !== undefined) {
        setSelectedFile(customEvt.detail.path);
      }
    };
    window.addEventListener('aria-workspace-file-select', handleWorkspaceFileSelect);
    return () => window.removeEventListener('aria-workspace-file-select', handleWorkspaceFileSelect);
  }, []);

  // ── Sync with global shell navigation and search events ───────────────────
  useEffect(() => {
    const initialTab = resolveInitialTab();
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('aria-tab-changed', { detail: { tab: initialTab } }));
    }
    const handleOpenPalette = () => {
      setPaletteOpen(true);
    };

    window.addEventListener('open-command-palette', handleOpenPalette);

    return () => {
      window.removeEventListener('open-command-palette', handleOpenPalette);
    };
  }, []);

  const handleFileTreeSelect = (filePath: string) => {
    setSelectedFile(filePath);
    if (activeTab === 'graph') {
      setGraphFocus({ path: filePath, token: Date.now() });
      syncTabToUrl('graph', filePath);
    }
  };

  /** Focuses the File Graph tab on a file's dependency neighbourhood. */
  const handleViewInGraph = (filePath: string) => {
    setSelectedFile(filePath);
    setGraphFocus({ path: filePath, token: Date.now() });
    handleTabChange('graph', filePath);
  };

  /** Focuses the Call Graph tab on a file. */
  const handleViewInCallGraph = (filePath: string) => {
    setSelectedFile(filePath);
    handleTabChange('call_graph', filePath);
  };

  const commandItems = useMemo<CommandItem[]>(() => {
    const items: CommandItem[] = [];

    // Destinations
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

    // Files
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

    // Reading path steps
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

    // Architecture components
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

    // Dependencies
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

    // Tech stack
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
      const file = resolveInitialFile();
      setActiveTab(tab);
      setMountedTabs(prev => new Set([...prev, tab]));
      if (file) {
        setSelectedFile(file);
        setGraphFocus({ path: file, token: Date.now() });
      }
      
      const repoVal = getRepoFromUrl(repoParam);
      setRepoName(repoVal);
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('aria-tab-changed', { detail: { tab } }));
      }
    };
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, [repoParam]);

  // Cross-Surface Intelligence Deep Linking
  useEffect(() => {
    const handleOpenChat = (e: Event) => {
      const customEvent = e as CustomEvent<{ prompt?: string }>;
      if (customEvent.detail?.prompt) {
        setPendingChatPrompt({ text: customEvent.detail.prompt, token: Date.now() });
      }
      handleTabChange('chat');
    };

    const handleOpenGraph = (e: Event) => {
      const customEvent = e as CustomEvent<{ path?: string; file?: string; owner?: string; repo?: string }>;
      const targetPath = customEvent.detail?.file || customEvent.detail?.path;
      if (targetPath) {
        setSelectedFile(targetPath);
        setGraphFocus({ path: targetPath, token: Date.now() });
      }
      handleTabChange('graph', targetPath);
    };

    const handleOpenImpact = () => {
      handleTabChange('impact_analysis');
    };

    const handleOpenIssues = () => {
      handleTabChange('issues');
    };

    const handleNavigateTab = (e: Event) => {
      const customEvent = e as CustomEvent<{ tab: TabId; file?: string }>;
      if (customEvent.detail?.tab) {
        handleTabChange(customEvent.detail.tab, customEvent.detail.file);
      }
    };

    window.addEventListener('aria-open-chat', handleOpenChat);
    window.addEventListener('aria-open-graph', handleOpenGraph);
    window.addEventListener('aria-open-impact', handleOpenImpact);
    window.addEventListener('aria-open-issues', handleOpenIssues);
    window.addEventListener('aria-navigate-tab', handleNavigateTab);

    return () => {
      window.removeEventListener('aria-open-chat', handleOpenChat);
      window.removeEventListener('aria-open-graph', handleOpenGraph);
      window.removeEventListener('aria-open-impact', handleOpenImpact);
      window.removeEventListener('aria-open-issues', handleOpenIssues);
      window.removeEventListener('aria-navigate-tab', handleNavigateTab);
    };
  }, []);

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

  const fetchAnalysisData = useCallback(async (isRetry: boolean = false) => {
    const [o, n] = repoName.split('/');
    if (!o || !n || o === 'unknown' || n === 'repo') {
      setErrorMessage('Repository information missing or invalid. Redirecting to home.');
      setTimeout(() => (window.location.href = '/'), 2000);
      setLoading(false);
      return;
    }

    setData(null);
    setSelectedFile(null);
    setLoading(true);
    setErrorMessage(null);

    if (typeof window !== 'undefined') {
      const now = Date.now();
      localStorage.setItem('activeRepo', repoName);
      localStorage.setItem(`lastAnalysed:${repoName}`, String(now));
      setIndexedAt(now);
      window.dispatchEvent(new CustomEvent('active-repo-changed', { detail: repoName }));
    }

    try {
      const endpoint = apiUrl(`/api/v1/analysis/${encodeURIComponent(o)}/${encodeURIComponent(n)}`);
      const res = await fetch(endpoint);
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        const extracted = extractErrorMessage(errData);
        if (res.status === 404) {
          throw new Error(extracted || `Repository '${repoName}' has not been analysed yet. Please run analysis first.`);
        }
        if (res.status === 401 || res.status === 403) {
          throw new Error(extracted || 'Access denied or authentication failed for this repository.');
        }
        if (res.status >= 500) {
          throw new Error(extracted || 'Backend service error. Please retry in a few moments.');
        }
        throw new Error(extracted || 'Failed to fetch repository details');
      }
      const resData = await res.json();
      setData(resData);
    } catch (err: any) {
      setErrorMessage(extractErrorMessage(err) || 'Network error or backend service unreachable.');
    } finally {
      setLoading(false);
    }
  }, [repoName]);

  useEffect(() => {
    fetchAnalysisData(false);
  }, [fetchAnalysisData]);


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
                  <li>Repository has not been analyzed yet (run analysis from home page)</li>
                  <li>Invalid or malformed GitHub repository URL</li>
                  <li>GitHub API rate limit or authentication required</li>
                  <li>Temporary network failure or backend server is offline</li>
                </ul>
              </div>
            </div>
          }
          action={
            <div className="flex gap-3 justify-center mt-2 select-none">
              <button
                type="button"
                onClick={() => fetchAnalysisData(true)}
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

  const fileCount       = countFiles(analysis?.structure || {});
  const componentCount  = countComponents(architecture?.relationships || []);
  const dependencyCount = analysis?.dependencies?.length || 0;
  const readingSteps    = architecture?.reading_order?.length || 0;

  // Derived presentation metrics
  const complexity      = computeComplexity({ fileCount, componentCount, dependencyCount });
  const primaryLanguage = detectPrimaryLanguage(analysis?.tech_stack || []);
  const readingMinutes  = estimateReadingMinutes(readingSteps);
  const directoryCount  = Object.keys(analysis?.structure || {}).length;
  const indexedAgo      = relativeTimeFrom(indexedAt);

  const insights = deriveInsights({
    fileCount,
    directoryCount,
    dependencyCount,
    techStack: analysis?.tech_stack || [],
    structure: analysis?.structure || {},
    entryPointCount: entryPoints.length,
    cycleCount: circularDependencies.length,
    componentCount,
    relationshipCount: architecture?.relationships?.length || 0,
    readingSteps,
    readingMinutes,
  });

  // Degraded / Partial capability assessment
  const isDegraded = data?.analysis?.metadata?.status === 'degraded' || data?.analysis?.metadata?.partial === 'true';

  return (
    <div className="w-full pt-1 pb-10 space-y-6 fade-up">
      <RepoCommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        items={commandItems}
        scopeLabel={repoName}
      />

      {/* ── SECONDARY INSTRUMENT SUB-RAIL (Only rendered when exploring secondary tools) ── */}
      {!PRIMARY_TAB_IDS.has(activeTab) && (
        <div className="tab-rail-sticky -mt-1 pt-1 z-10 bg-canvas/90 backdrop-blur pb-2">
          <Tabs items={TABS.filter(t => !PRIMARY_TAB_IDS.has(t.id))} active={activeTab} onChange={handleTabChange} />
        </div>
      )}

      {/* ── TAB CONTENT MOUNTING ─────────────────────────────────────────────── */}
      {activeTab === 'analysis' ? (
        /* ── Redesigned Overview Page ── */
        <RepositoryOverview
          owner={owner}
          repoSlug={repoSlug}
          repoName={repoName}
          summary={architecture?.summary || ''}
          analysis={analysis}
          architecture={architecture}
          health={health}
          healthState={healthState}
          complexity={complexity}
          primaryLanguage={primaryLanguage}
          readingMinutes={readingMinutes}
          readingSteps={readingSteps}
          fileCount={fileCount}
          directoryCount={directoryCount}
          dependencyCount={dependencyCount}
          componentCount={componentCount}
          entryPoints={entryPoints}
          groupedEntryPoints={groupedEntryPoints}
          circularDependencies={circularDependencies}
          insights={insights}
          indexedAt={indexedAt}
          onNavigateTab={handleTabChange}
          onSelectFile={handleFileTreeSelect}
          onAskAboutFile={handleAskAboutFile}
          onViewInGraph={handleViewInGraph}
        />
      ) : (
        /* ── Other Surfaces with Explorer Split ── */
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-y-8 lg:gap-0 items-stretch border-t border-white/[0.055]">
          {/* Quiet left workspace rail */}
          <div className="lg:col-span-3 min-w-0 lg:pr-7 lg:border-r lg:border-white/[0.055] pt-5">
            <details className="lg:hidden group/ws" open={false}>
              <summary className="flex items-center justify-between gap-3 cursor-pointer list-none py-1 focus-visible:outline-none focus-visible:shadow-ring">
                <span className="mono-label">WORKSPACE EXPLORER</span>
                <span className="mono-detail" style={{ fontSize: 10 }}>
                  <span className="group-open/ws:hidden">SHOW</span>
                  <span className="hidden group-open/ws:inline">HIDE</span>
                </span>
              </summary>
              <div className="mt-4">
                <FileTree structure={analysis.structure} onFileSelect={handleFileTreeSelect} />
              </div>
            </details>

            <div className="hidden lg:block">
              <FileTree structure={analysis.structure} onFileSelect={handleFileTreeSelect} />
            </div>

            {selectedFile && (
              <div className="mt-7 pt-5 hair-t fade-up min-w-0">
                <span className="mono-label mono-label-accent block mb-3">SELECTED FILE</span>
                <p className="font-mono text-[15px] text-text font-semibold leading-snug break-words">
                  {selectedFile.split('/').pop()}
                </p>
                <div className="mt-5 pt-4 hair-t">
                  <span className="mono-label block mb-2">PATH</span>
                  <FilePath path={selectedFile} tone="secondary" size="sm" />
                </div>
                <div className="mt-4 pt-4 hair-t">
                  <span className="mono-label block mb-2">ROLE · INFERRED</span>
                  <span className="font-mono text-[12px] text-text">
                    {inferFileRole(selectedFile)}
                  </span>
                </div>
                <div className="mt-4 pt-4 hair-t">
                  <span className="mono-label block mb-3">ACTIONS</span>
                  <div className="flex flex-col items-start gap-2.5">
                    <button
                      type="button"
                      onClick={() => handleAskAboutFile(selectedFile)}
                      className="link-arrow group flex items-center gap-2 font-mono text-[11px] text-text-muted hover:text-text transition-colors focus-visible:outline-none"
                    >
                      Ask ARIA
                      <ArrowRight className="h-3 w-3 arrow" aria-hidden="true" />
                    </button>
                    <button
                      type="button"
                      onClick={() => handleViewInGraph(selectedFile)}
                      className="link-arrow group flex items-center gap-2 font-mono text-[11px] text-text-muted hover:text-text transition-colors focus-visible:outline-none"
                    >
                      View in Graph
                      <ArrowRight className="h-3 w-3 arrow" aria-hidden="true" />
                    </button>
                    <button
                      type="button"
                      onClick={() => handleTabChange('issues')}
                      className="link-arrow group flex items-center gap-2 font-mono text-[11px] text-text-muted hover:text-text transition-colors focus-visible:outline-none"
                    >
                      Map Issue
                      <ArrowRight className="h-3 w-3 arrow" aria-hidden="true" />
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Right analysis workbench surface */}
          <div className="lg:col-span-9 space-y-6 min-w-0 lg:pl-9 pt-5">
            {TABS.filter((t) => t.id !== 'analysis').map(({ id }) => (
              <div
                key={id}
                id={`tabpanel-${id}`}
                role="tabpanel"
                aria-labelledby={id}
                hidden={activeTab !== id}
                className={`space-y-6 ${activeTab === id ? 'panel-enter' : ''}`}
              >
                {mountedTabs.has(id) && (
                  <>
                    {/* Structure */}
                    {id === 'graph' && (
                      <InteractiveDependencyGraph repoName={repoName} focusRequest={graphFocus} />
                    )}
                    {id === 'call_graph' && (
                      <Suspense fallback={<SkeletonGraph />}>
                        <CallGraphAnalyzer repoName={repoName} />
                      </Suspense>
                    )}
                    {id === 'api_surface' && (
                      <Suspense fallback={<SkeletonDashboard />}>
                        <APISurfaceAnalyzer repoName={repoName} />
                      </Suspense>
                    )}

                    {/* Understand */}
                    {id === 'reading_path' && (
                      <Suspense fallback={<SkeletonDashboard />}>
                        <ReadingOrderTimeline
                          repoName={repoName}
                          onAskAboutFile={handleAskAboutFile}
                          onViewInGraph={handleViewInGraph}
                          onViewInCallGraph={handleViewInCallGraph}
                        />
                      </Suspense>
                    )}
                    {id === 'chat' && (
                      <div className="min-h-[600px] flex flex-col">
                        <Suspense fallback={<SkeletonDashboard />}>
                          <ChatInterface
                            repoName={repoName}
                            pendingPrompt={pendingChatPrompt}
                            onPendingPromptConsumed={() => setPendingChatPrompt(null)}
                            repoMetadata={{
                              techStack: data?.analysis?.tech_stack,
                              dependencies: data?.analysis?.dependencies,
                              entryPoints: entryPoints,
                              cyclesCount: circularDependencies.length,
                              componentCount: componentCount,
                              readingSteps: readingSteps,
                              healthScore: health?.score,
                            }}
                          />
                        </Suspense>
                      </div>
                    )}

                    {/* Quality */}
                    {id === 'report' && (
                      <Suspense fallback={<SkeletonDashboard />}>
                        <ReportPanel
                          repoName={repoName}
                          onNavigate={(tab) => handleTabChange(tab as TabId)}
                        />
                      </Suspense>
                    )}
                    {id === 'dead_code' && (
                      <Suspense fallback={<SkeletonDashboard />}>
                        <DeadCodeAnalyzer repoName={repoName} />
                      </Suspense>
                    )}
                    {id === 'issues' && (
                      <Suspense fallback={<SkeletonDashboard />}>
                        <IssueMapper repoName={repoName} />
                      </Suspense>
                    )}

                    {/* History & PRs */}
                    {id === 'git_history' && (
                      <Suspense fallback={<SkeletonDashboard />}>
                        <GitHistoryAnalyzer repoName={repoName} />
                      </Suspense>
                    )}
                    {id === 'pr_intelligence' && (
                      <Suspense fallback={<SkeletonDashboard />}>
                        <PRIntelligence repoName={repoName} />
                      </Suspense>
                    )}
                    {id === 'architecture_drift' && (
                      <Suspense fallback={<SkeletonDashboard />}>
                        <ArchitectureDrift repoName={repoName} />
                      </Suspense>
                    )}
                    {id === 'impact_analysis' && (
                      <Suspense fallback={<SkeletonDashboard />}>
                        <ImpactAnalysisWorkspace repoName={repoName} />
                      </Suspense>
                    )}
                  </>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── CLOSING STATUS LINE ──────────────────────────────────────────────── */}
      <footer className="mt-10 pt-4 border-t border-white/[0.055]" aria-label="Analysis status">
        <Reveal className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          <span className="flex items-center gap-2.5 shrink-0">
            <span className="h-1.5 w-1.5 rounded-full bg-success" aria-hidden="true" />
            <span className="mono-label" style={{ color: 'var(--success)' }}>
              ANALYSIS COMPLETE
            </span>
          </span>
          <span className="mono-detail shrink-0 tabular-nums" style={{ fontSize: 10, letterSpacing: '0.14em' }}>
            STRUCTURE MAPPED · RELATIONSHIPS RESOLVED ·{' '}
            {indexedAgo ? `INDEXED ${indexedAgo.toUpperCase()}` : 'INDEXED THIS SESSION'}
          </span>
        </Reveal>
      </footer>
    </div>
  );
};

export default AnalysisDashboard;

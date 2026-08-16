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
import { RepoHero, type CentralityHub } from './RepoHero';
import { SectionSeam } from '../ui/SectionSeam';
import { Reveal } from '../ui/Reveal';
import { Meter } from '../ui/Meter';
import { FilePath } from '../ui/FilePath';
import { inferFileRole } from '../../lib/fileRole';
import { TechStackPanel } from './TechStackPanel';
import { DependencyExplorer } from './DependencyExplorer';
import { RepoCommandPalette, COMMAND_ICONS, type CommandItem } from './RepoCommandPalette';
import { ExecutiveInsights } from './ExecutiveInsights';
import { deriveInsights } from '../../lib/repoInsights';
import { Tabs, type TabItem } from './Tabs';
import { Badge } from '../ui/Badge';
import { Button } from '../ui/Button';
import { MetricMatrix } from '../ui/MetricMatrix';
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

import { InteractiveDependencyGraph } from './graph/InteractiveDependencyGraph';
import { ImpactAnalysisGraph } from './ImpactAnalysisGraph';

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
  /**
   * Components ranked by how many architecture relationships touch them, used
   * for the centrality read-out in the header. This is derived from the real
   * relationship graph already in `data` — no extra request, no placeholder
   * figures.
   */
  const centralityHubs = useMemo<CentralityHub[]>(() => {
    const rels = data?.architecture?.relationships;
    if (!rels || rels.length === 0) return [];

    const degree: Record<string, number> = {};
    const inbound: Record<string, number> = {};

    rels.forEach((r) => {
      degree[r.source] = (degree[r.source] ?? 0) + 1;
      degree[r.target] = (degree[r.target] ?? 0) + 1;
      inbound[r.target] = (inbound[r.target] ?? 0) + 1;
      inbound[r.source] = inbound[r.source] ?? 0;
    });

    return Object.keys(degree)
      .map((name) => ({ name, inbound: inbound[name] ?? 0, degree: degree[name] }))
      .sort((a, b) => b.degree - a.degree || b.inbound - a.inbound)
      .slice(0, 4);
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

  /**
   * Entry points collapsed by filename. A repository with thirteen `main.py`
   * files previously rendered thirteen identical chips; this reports the count
   * instead, while a unique entry still shows its full distinguishing path.
   */
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
      const file = resolveInitialFile();
      setActiveTab(tab);
      setMountedTabs(prev => new Set([...prev, tab]));
      if (file) {
        setSelectedFile(file);
        setGraphFocus({ path: file, token: Date.now() });
      }
      
      const repoVal = getRepoFromUrl(repoParam);
      setRepoName(repoVal);
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

    const handleOpenImpact = (e: Event) => {
      const customEvent = e as CustomEvent<{ file?: string }>;
      if (customEvent.detail?.file) {
        setIssueInput(customEvent.detail.file);
      }
      handleTabChange('impact_analysis');
    };

    const handleOpenIssues = () => {
      handleTabChange('issues');
    };

    window.addEventListener('aria-open-chat', handleOpenChat);
    window.addEventListener('aria-open-graph', handleOpenGraph);
    window.addEventListener('aria-open-impact', handleOpenImpact);
    window.addEventListener('aria-open-issues', handleOpenIssues);

    return () => {
      window.removeEventListener('aria-open-chat', handleOpenChat);
      window.removeEventListener('aria-open-graph', handleOpenGraph);
      window.removeEventListener('aria-open-impact', handleOpenImpact);
      window.removeEventListener('aria-open-issues', handleOpenIssues);
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
    /*
      Rhythm is set explicitly by the seams between groups rather than by a
      uniform `space-y`, so major transitions get air and content inside a group
      stays compact.
    */
    <div className="w-full pt-2 fade-up">
      <RepoCommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        items={commandItems}
        scopeLabel={repoName}
      />

      {/* ── REPOSITORY HEADER + SIGNAL RAIL + CENTRALITY ─────────────────────── */}
      <header>
        <RepoHero
          onOpenCommandPalette={() => setPaletteOpen(true)}
          owner={owner}
          repoSlug={repoSlug}
          summary={architecture.summary}
          primaryLanguage={primaryLanguage}
          readingMinutes={readingMinutes}
          complexity={complexity}
          indexedAt={indexedAt}
          hubs={centralityHubs}
          onRefresh={() => window.location.reload()}
          onExportReport={() => handleTabChange('report')}
        />
      </header>

      {/* ── REPOSITORY INSIGHTS ──────────────────────────────────────────────── */}
      <SectionSeam label="ARCHITECTURE SIGNAL → FINDINGS" />
      <ExecutiveInsights insights={insights} />

      {/* ── STRUCTURAL METRICS ───────────────────────────────────────────────── */}
      <SectionSeam label="FINDINGS → STRUCTURE" />
      <div>
        <div className="flex items-baseline justify-between gap-4 mb-1">
          <h2 className="mono-label">STRUCTURAL METRICS</h2>
          <span className="mono-detail shrink-0" style={{ fontSize: 10 }}>
            {indexedAgo ? `INDEXED ${indexedAgo.toUpperCase()}` : 'INDEXED THIS SESSION'}
          </span>
        </div>

        <MetricMatrix
          entries={[
            {
              label: 'FILES',
              value: <AnimatedNumber value={fileCount} startOnView />,
              detail: `${directoryCount} ${directoryCount === 1 ? 'directory' : 'directories'}`,
              note: `~${Math.max(1, Math.round(fileCount / Math.max(1, directoryCount)))} per directory`,
            },
            {
              label: 'LANGUAGES',
              value: <AnimatedNumber value={languageCount} startOnView />,
              detail: analysis.tech_stack.slice(0, 4).join(' · ') || '—',
              note: primaryLanguage ? `Primary: ${primaryLanguage}` : undefined,
            },
            {
              label: 'COMPONENTS',
              value: <AnimatedNumber value={componentCount} startOnView />,
              detail: `${architecture.relationships.length} relationships`,
              note:
                circularDependencies.length > 0
                  ? `${circularDependencies.length} cycle${circularDependencies.length === 1 ? '' : 's'} detected`
                  : 'No cycles detected',
              tone: circularDependencies.length > 0 ? 'warn' : 'default',
              onClick: () => handleTabChange('graph'),
              actionLabel: `Components: ${componentCount}. Open the file graph.`,
            },
            {
              label: 'DEPENDENCIES',
              value: <AnimatedNumber value={dependencyCount} startOnView />,
              detail: dependencyCount === 0 ? 'No manifest resolved' : 'Resolved from manifests',
              note: `Complexity ${complexity.label.toLowerCase()} · ${complexity.score}/100`,
            },
            {
              label: 'READING STEPS',
              value: <AnimatedNumber value={readingSteps} startOnView />,
              detail: `~${formatDuration(readingMinutes)} to complete`,
              note: 'Centrality ranked',
              onClick: () => handleTabChange('reading_path'),
              actionLabel: `Reading steps: ${readingSteps}. Open the reading path.`,
            },
          ]}
        />
      </div>

      {/* ── WORKSPACE + ANALYSIS SURFACE ─────────────────────────────────────── */}
      <SectionSeam label="STRUCTURE → WORKSPACE" />

      {/* Deliberate entry into the investigation layer — tighter editorial rhythm */}
      <Reveal as="header" className="mb-4 sm:mb-5 max-w-3xl">
        <span className="mono-label mono-label-accent block mb-1.5">WORKSPACE</span>
        <h2 className="display-3 text-text">The codebase, ready to inspect.</h2>
        <p className="text-[13px] sm:text-sm text-text-muted leading-relaxed mt-1.5 max-w-xl">
          Move from repository-level signals into the files, graphs, paths, and evidence behind
          them.
        </p>
      </Reveal>

      {/*
        One instrument, not two panels: a shared top rule spans both columns and
        a single hairline divides them (27% explorer / 73% analysis surface).
      */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-y-8 lg:gap-0 items-stretch border-t border-white/[0.055]">
        {/* Quiet left rail (approx 27%) */}
        <div className="lg:col-span-3 min-w-0 lg:pr-7 lg:border-r lg:border-white/[0.055] pt-5">
          {/* Collapsible below lg so the tree never buries the analysis surface */}
          <details className="lg:hidden group/ws" open={false}>
            <summary
              className="flex items-center justify-between gap-3 cursor-pointer list-none py-1
                         focus-visible:outline-none focus-visible:shadow-ring"
            >
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

          {/* Selected file as an intelligence object, not merely a selection */}
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
                {/* Derived from the path on the client — labelled as inferred */}
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
                    className="link-arrow group flex items-center gap-2 font-mono text-[11px]
                               text-text-muted hover:text-text transition-colors duration-200
                               focus-visible:outline-none focus-visible:shadow-ring"
                  >
                    Ask ARIA
                    <ArrowRight className="h-3 w-3 arrow" aria-hidden="true" />
                  </button>
                  <button
                    type="button"
                    onClick={() => handleViewInGraph(selectedFile)}
                    className="link-arrow group flex items-center gap-2 font-mono text-[11px]
                               text-text-muted hover:text-text transition-colors duration-200
                               focus-visible:outline-none focus-visible:shadow-ring"
                  >
                    View in Graph
                    <ArrowRight className="h-3 w-3 arrow" aria-hidden="true" />
                  </button>
                  <button
                    type="button"
                    onClick={() => handleTabChange('issues')}
                    className="link-arrow group flex items-center gap-2 font-mono text-[11px]
                               text-text-muted hover:text-text transition-colors duration-200
                               focus-visible:outline-none focus-visible:shadow-ring"
                  >
                    Map Issue
                    <ArrowRight className="h-3 w-3 arrow" aria-hidden="true" />
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Right analysis surface (approx 73%) */}
        <div className="lg:col-span-9 space-y-6 min-w-0 lg:pl-9 pt-5">
          {/* Instrument selector stays reachable while a long panel scrolls */}
          <div className="tab-rail-sticky -mt-1 pt-1">
            <Tabs items={TABS} active={activeTab} onChange={handleTabChange} />
          </div>

          {/* Tab panels — mount-on-first-visit, stay mounted to preserve state */}
          {TABS.map(({ id }) => (
            <div
              key={id}
              id={`tabpanel-${id}`}
              role="tabpanel"
              aria-labelledby={id}
              hidden={activeTab !== id}
              /*
                `panel-enter` exists only on the active panel, so switching tabs
                removes it from the outgoing panel and adds it to the incoming
                one — which is what replays the entry animation. Panels stay
                mounted, so no tab state is lost.
              */
              className={`space-y-6 ${activeTab === id ? 'panel-enter' : ''}`}
            >
              {mountedTabs.has(id) && (
                <>
                  {/* ── Overview ── */}
                  {id === 'analysis' && (
                    <>
                      {/* Action row — transparent, bordered, no filled chips */}
                      <div
                        className="flex flex-wrap gap-2.5"
                        role="navigation"
                        aria-label="Quick navigation"
                      >
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
                            className="action-chip"
                          >
                            {label}
                            <ArrowRight className="h-3 w-3" aria-hidden="true" />
                          </button>
                        ))}
                      </div>

                      {/* Editorial summary — capped line length, no card */}
                      <section aria-labelledby="codebase-summary-heading">
                        <h2 id="codebase-summary-heading" className="mono-label pb-3 hair-b">
                          CODEBASE SUMMARY
                        </h2>
                        <p className="text-[15px] sm:text-base text-text leading-relaxed max-w-[68ch] mt-5">
                          {architecture.summary}
                        </p>

                        {/*
                          Metadata readout — prominent architectural readout
                        */}
                        <dl className="mt-7 pt-5 hair-t grid grid-cols-2 sm:grid-cols-4 gap-6">
                          {primaryLanguage && (
                            <div className="min-w-0">
                              <dt className="mono-label mb-1.5">PRIMARY LANGUAGE</dt>
                              <dd className="font-mono text-[14px] font-semibold text-text truncate">
                                {primaryLanguage}
                              </dd>
                            </div>
                          )}
                          <div className="min-w-0">
                            <dt className="mono-label mb-1.5">COMPONENTS</dt>
                            <dd className="font-mono text-[14px] font-semibold text-text tabular-nums">
                              {componentCount}
                              <span className="text-text-muted font-normal text-[12px]">
                                {' '}· {architecture.relationships.length} edges
                              </span>
                            </dd>
                          </div>
                          <div className="min-w-0">
                            <dt className="mono-label mb-1.5">ENTRY SURFACE</dt>
                            <dd className="font-mono text-[14px] font-semibold text-text tabular-nums">
                              {entryPoints.length}
                              <span className="text-text-muted font-normal text-[12px]">
                                {' '}
                                {entryPoints.length === 1 ? 'entry point' : 'entry points'}
                              </span>
                            </dd>
                          </div>
                          <div className="min-w-0">
                            <dt className="mono-label mb-1.5">FOOTPRINT</dt>
                            <dd className="font-mono text-[14px] font-semibold text-text tabular-nums">
                              {fileCount.toLocaleString()}
                              <span className="text-text-muted font-normal text-[12px]"> files · {directoryCount} dirs</span>
                            </dd>
                          </div>
                        </dl>
                      </section>

                      <div className="grid grid-cols-1 xl:grid-cols-2 gap-8 xl:gap-12 items-start pt-2">
                        <TechStackPanel techStack={analysis.tech_stack} />
                        <DependencyExplorer dependencies={analysis.dependencies} />
                      </div>

                      {/* ── Diagnostics: complexity · architecture status · entry points ── */}
                      <div className="grid grid-cols-1 sm:grid-cols-3 border-t border-white/[0.055]">
                        {/* Complexity */}
                        <div className="diagnostic py-6 sm:pr-8 sm:border-r sm:border-white/[0.055]">
                          <span className="mono-label block mb-3">COMPLEXITY INDEX</span>
                          <div className="diagnostic-body">
                            <div className="flex items-baseline gap-2.5">
                              <span className="readout-value readout-value--lead">
                                <AnimatedNumber value={complexity.score} startOnView />
                              </span>
                              <span className="font-mono text-[11px] uppercase tracking-[0.16em] text-text-muted">
                                {complexity.label}
                              </span>
                            </div>

                            {/* Severity scale — restrained, grows once in view */}
                            <Meter
                              value={complexity.score / 100}
                              barClassName={
                                complexity.score >= 75
                                  ? 'bg-danger'
                                  : complexity.score >= 50
                                    ? 'bg-warn'
                                    : 'bg-success'
                              }
                              className="mt-4 max-w-[10rem]"
                              delay={140}
                            />
                          </div>

                          <p className="mono-detail mt-4" style={{ fontSize: 10 }}>
                            DENSITY SCORE
                          </p>
                        </div>

                        {/* Architecture status */}
                        <div className="diagnostic py-6 sm:px-8 border-t sm:border-t-0 border-white/[0.055] sm:border-r sm:border-white/[0.055]">
                          <span className="mono-label block mb-3">ARCHITECTURE STATUS</span>
                          <div className="diagnostic-body">
                            <div className="flex items-center gap-2.5">
                              <span
                                className={`h-1.5 w-1.5 rounded-full shrink-0 ${
                                  circularDependencies.length > 0 ? 'bg-warn' : 'bg-success'
                                }`}
                                aria-hidden="true"
                              />
                              <span
                                className={`font-mono text-[13px] sm:text-[15px] uppercase tracking-[0.1em] font-semibold ${
                                  circularDependencies.length > 0 ? 'text-warn' : 'text-success'
                                }`}
                              >
                                {circularDependencies.length > 0
                                  ? `${circularDependencies.length} cycle${circularDependencies.length === 1 ? '' : 's'} found`
                                  : 'Acyclic / Stable'}
                              </span>
                            </div>
                            <p className="text-[12px] text-text-muted leading-relaxed mt-4 max-w-[34ch]">
                              {circularDependencies.length > 0
                                ? 'Circular component dependencies detected in the relationship graph.'
                                : 'No circular component relationships detected across the graph.'}
                            </p>
                          </div>

                          <p className="mono-detail mt-4" style={{ fontSize: 10 }}>
                            CYCLE DETECTION
                          </p>
                        </div>

                        {/* Entry points — grouped so repeated filenames read as counts */}
                        <div className="diagnostic py-6 sm:pl-8 border-t sm:border-t-0 border-white/[0.055]">
                          <div className="flex items-baseline justify-between gap-3 mb-3">
                            <span className="mono-label">ENTRY POINTS</span>
                            <span className="mono-detail shrink-0 tabular-nums" style={{ fontSize: 10 }}>
                              {entryPoints.length} DETECTED
                            </span>
                          </div>

                          <div className="diagnostic-body">
                          {entryPoints.length > 0 ? (
                            <ul className="min-w-0">
                              {groupedEntryPoints.slice(0, 5).map((group) => (
                                <li key={group.name} className="min-w-0">
                                  <button
                                    type="button"
                                    onClick={() => setSelectedFile(group.paths[0])}
                                    title={group.paths.join('\n')}
                                    className="spec-row w-full flex items-baseline justify-between gap-3 py-1.5 text-left min-w-0
                                               focus-visible:outline-none focus-visible:shadow-ring"
                                  >
                                    <FilePath path={group.name} tone="secondary" size="sm" />
                                    {group.count > 1 && (
                                      <span
                                        className="mono-detail shrink-0 tabular-nums"
                                        style={{ fontSize: 10 }}
                                      >
                                        × {group.count}
                                      </span>
                                    )}
                                  </button>
                                </li>
                              ))}
                            </ul>
                          ) : (
                            <p className="mono-detail" style={{ fontSize: 10 }}>
                              NONE DETECTED
                            </p>
                          )}
                          </div>

                          <p className="mono-detail mt-4" style={{ fontSize: 10 }}>
                            INFERRED FROM FILENAME PATTERNS
                          </p>
                        </div>
                      </div>

                      {/* Health report — a navigation row, not a CTA card */}
                      <button
                        type="button"
                        onClick={() => handleTabChange('report')}
                        className="spec-row link-arrow group w-full flex items-center justify-between gap-4
                                   py-5 border-y border-white/[0.055] text-left
                                   focus-visible:outline-none focus-visible:shadow-ring"
                        aria-label="Open the repository health report"
                      >
                        <span className="min-w-0">
                          <span className="block font-mono text-[13px] uppercase tracking-[0.12em] text-text
                                           group-hover:text-primary transition-colors">
                            Health Report
                          </span>
                          <span className="mono-detail block mt-1.5" style={{ fontSize: 10 }}>
                            ARCHITECTURE · API · HYGIENE · ONBOARDING
                          </span>
                        </span>
                        <ArrowRight
                          className="h-4 w-4 shrink-0 text-text-subtle group-hover:text-primary arrow transition-colors"
                          aria-hidden="true"
                        />
                      </button>

                      <section aria-labelledby="relationships-heading">
                        <div className="flex items-baseline justify-between gap-4 pb-3 hair-b">
                          <h2 id="relationships-heading" className="mono-label mono-label-accent">
                            ARCHITECTURE COMPONENT RELATIONSHIPS
                          </h2>
                          <span className="mono-detail shrink-0 tabular-nums" style={{ fontSize: 10 }}>
                            {architecture.relationships.length}{' '}
                            {architecture.relationships.length === 1 ? 'EDGE' : 'EDGES'}
                          </span>
                        </div>

                        {architecture.relationships.length > 0 ? (
                          /*
                            A topology list: each edge is source → type → target on a
                            single connected spine, echoing the graph language used on
                            the landing page rather than three unrelated cards.
                          */
                          <ol className="mt-6 relative pl-7 sm:pl-9">
                            <span
                              className="topo-line top-1 bottom-1 left-[5px] sm:left-[7px]"
                              aria-hidden="true"
                            />
                            {architecture.relationships.map((rel, idx) => (
                              <Reveal
                                key={idx}
                                as="li"
                                tabIndex={0}
                                delay={Math.min(idx * 90, 450)}
                                className="topo-item relative pb-8 last:pb-0 min-w-0
                                           focus-visible:outline-none focus-visible:shadow-ring"
                              >
                                {/* Node on the spine */}
                                <span
                                  className="topo-node absolute -left-7 sm:-left-9 top-1 h-[11px] w-[11px]
                                             rounded-full border"
                                  aria-hidden="true"
                                />

                                {/* SOURCE → RELATIONSHIP → TARGET, read top to bottom */}
                                <span className="mono-label block mb-1.5">SOURCE</span>
                                <p className="topo-source min-w-0">
                                  <FilePath path={rel.source} tone="primary" size="md" />
                                </p>

                                <div className="flex items-center gap-2.5 my-3">
                                  <span className="topo-type font-mono text-[10px] uppercase tracking-[0.24em] shrink-0">
                                    {rel.relationship_type}
                                  </span>
                                  <span className="topo-edge h-px flex-1" aria-hidden="true" />
                                  <span className="topo-type text-[10px] shrink-0" aria-hidden="true">
                                    ↓
                                  </span>
                                </div>

                                <span className="mono-label block mb-1.5">TARGET</span>
                                <p className="topo-target min-w-0">
                                  <FilePath path={rel.target} tone="secondary" size="md" marker="target" />
                                </p>

                                {/* Level 3: explanation, deliberately quieter */}
                                <p className="text-[12px] text-text-subtle leading-relaxed mt-3 max-w-[62ch]">
                                  {rel.description}
                                </p>
                              </Reveal>
                            ))}
                          </ol>
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
                      </section>
                    </>
                  )}

                  {/* ── Structure ── */}
                  {id === 'graph' && (
                    <InteractiveDependencyGraph repoName={repoName} focusRequest={graphFocus} />
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
                  {/* onNavigate reuses the dashboard's existing tab handler so the
                      report's cross-surface links need no new routing. */}
                  {id === 'report'     && (
                    <ReportPanel
                      repoName={repoName}
                      onNavigate={(tab) => handleTabChange(tab as TabId)}
                    />
                  )}
                  {id === 'dead_code'  && <DeadCodeAnalyzer  repoName={repoName} />}
                  {id === 'issues'     && <IssueMapper       repoName={repoName} />}

                  {/* ── History & PRs ── */}
                  {id === 'git_history'        && <GitHistoryAnalyzer repoName={repoName} />}
                  {id === 'pr_intelligence'    && <PRIntelligence     repoName={repoName} />}
                  {id === 'architecture_drift' && <ArchitectureDrift  repoName={repoName} />}
                  {id === 'impact_analysis' && (
                    <div className="min-w-0">
                      {/* ── Contextual header ──────────────────────────── */}
                      <header className="min-w-0">
                        <span className="mono-label mono-label-accent block mb-2.5">
                          IMPACT INTELLIGENCE / PREDICTIVE ANALYSIS
                        </span>
                        <h2 className="display-3 text-text">See what this change will touch.</h2>
                        <p className="text-[13px] text-text-muted leading-relaxed mt-3 max-w-2xl">
                          Trace import propagation, affected components, and architectural risk
                          before modifying the codebase.
                        </p>
                      </header>

                      {/* ── Scenario command surface ───────────────────── */}
                      <div className="mt-9 min-w-0">
                        <h3 className="mono-label pb-3 hair-b">PREDICTIVE IMPACT ANALYSIS</h3>

                        <p className="text-[12px] text-text-muted leading-relaxed mt-4 max-w-2xl">
                          Describe a proposed code modification or feature request.
                        </p>

                        <div className="mt-3 flex flex-col sm:flex-row sm:items-start gap-3 min-w-0">
                          <label htmlFor="impact-query" className="sr-only">Issue text</label>
                          <textarea
                            id="impact-query"
                            value={issueInput}
                            onChange={(e) => setIssueInput(e.target.value)}
                            placeholder="e.g., Add GitHub OAuth Login, or Fix SQLite Timeout Issue"
                            rows={2}
                            className="console-field flex-grow text-[12.5px] min-h-0"
                          />
                          <button
                            type="button"
                            onClick={() => handleRunImpactAnalysis()}
                            disabled={impactLoading || !issueInput.trim()}
                            className="action-chip shrink-0 justify-center disabled:opacity-40 disabled:cursor-not-allowed"
                          >
                            Run Analysis
                            <ArrowRight className="h-3 w-3" aria-hidden="true" />
                          </button>
                        </div>

                        {/* Reserves its band either way, so running shifts nothing. */}
                        <div className="mt-2.5" aria-hidden="true">
                          {impactLoading ? <div className="activity-line" /> : <div className="h-px" />}
                        </div>

                        {impactError && (
                          <div role="alert" className="mt-5 flex items-start gap-3">
                            <AlertCircle className="h-4 w-4 shrink-0 mt-0.5 text-danger" aria-hidden="true" />
                            <div className="min-w-0">
                              <span className="mono-label block mb-1.5" style={{ color: 'var(--danger)' }}>
                                IMPACT ANALYSIS UNAVAILABLE
                              </span>
                              <p className="text-[12px] text-text-muted leading-relaxed">{impactError}</p>
                            </div>
                          </div>
                        )}

                        {/* Quiet preset rail — secondary to the input and CTA. */}
                        <div className="mt-7 min-w-0">
                          <span className="mono-label block mb-2.5">QUICK SCENARIOS</span>
                          <div className="flex flex-wrap gap-x-5 gap-y-2">
                            {[
                              repoName.includes('fastapi') ? 'Add API key authentication' : 'Add GitHub OAuth Login',
                              'Fix SQLite Timeout Issue',
                              'Refactor Duplicate HTML Templates',
                            ].map((preset) => (
                              <button
                                key={preset}
                                type="button"
                                onClick={() => handleRunImpactAnalysis(preset)}
                                disabled={impactLoading}
                                className="api-action link-arrow disabled:opacity-40 disabled:cursor-not-allowed"
                              >
                                {preset.toUpperCase()}
                                <ArrowRight className="h-2.5 w-2.5 arrow ml-1" aria-hidden="true" />
                              </button>
                            ))}
                          </div>
                        </div>
                      </div>

                      {/* ── Loading ────────────────────────────────────── */}
                      {impactLoading && (
                        <div className="mt-9 pt-6 hair-t">
                          <span className="mono-label block mb-3">ANALYZING IMPACT</span>
                          <p className="mono-detail mb-5" style={{ fontSize: 10, letterSpacing: '0.16em' }}>
                            SCENARIO → PROPAGATION → RISK
                          </p>
                          <SkeletonGroup label="Analyzing change impact">
                            <div className="space-y-4"><SkeletonCard /><SkeletonCard /></div>
                          </SkeletonGroup>
                        </div>
                      )}

                      {/* ── Analyzed ───────────────────────────────────── */}
                      {!impactLoading && impactData && (
                        <div className="mt-9 min-w-0">
                          <SectionSeam label="IMPACT → PROPAGATION" />
                          <Suspense fallback={<SkeletonGraph />}>
                            <ImpactAnalysisGraph
                              repoName={repoName}
                              impactData={impactData}
                              onReset={() => setImpactData(null)}
                            />
                          </Suspense>
                        </div>
                      )}

                      {/* ── Compact waiting state ──────────────────────── */}
                      {!impactLoading && !impactData && !impactError && (
                        <div className="mt-8 pt-5 hair-t min-w-0 max-h-[15rem]">
                          <span className="mono-label block mb-2">WAITING FOR SCENARIO</span>
                          <p className="mono-detail mb-3" style={{ fontSize: 10, letterSpacing: '0.2em' }}>
                            SCENARIO → PROPAGATION → RISK
                          </p>
                          <p className="text-[13px] text-text-muted leading-relaxed max-w-lg">
                            Describe a proposed change above to begin.
                          </p>
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

      {/* ── CLOSING STATUS LINE ──────────────────────────────────────────────── */}
      <footer className="mt-12 pt-5 border-t border-white/[0.055]" aria-label="Analysis status">
        <Reveal className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          {/* Static dot: the run has finished, so nothing here should pulse. */}
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

/**
 * Canonical metadata for the analysis dashboard tabs.
 *
 * This is deliberately icon-free plain data so it can be imported by lightweight
 * consumers (the command palette) without pulling the dashboard's dependency
 * graph — and by the dashboard itself, which maps each id onto a Lucide icon.
 *
 * Tab ids are part of the `?tab=` URL contract. Do not rename them.
 */

export type AnalysisTabId =
  | 'analysis' | 'reading_path' | 'chat'
  | 'graph' | 'call_graph' | 'api_surface'
  | 'report' | 'dead_code' | 'issues'
  | 'git_history' | 'pr_intelligence' | 'architecture_drift' | 'impact_analysis';

export type AnalysisTabGroup = 'Understand' | 'Structure' | 'Quality' | 'History & PRs';

export interface AnalysisTabMeta {
  id: AnalysisTabId;
  label: string;
  group: AnalysisTabGroup;
  /** Shown as the secondary line in the command palette. */
  description: string;
  /** Extra search terms so the palette matches intent, not just the label. */
  keywords: string[];
}

export const ANALYSIS_TABS: AnalysisTabMeta[] = [
  {
    id: 'analysis',
    label: 'Overview',
    group: 'Understand',
    description: 'Architecture summary, tech stack, and repository KPIs',
    keywords: ['summary', 'dashboard', 'kpi', 'stack', 'structure', 'home'],
  },
  {
    id: 'reading_path',
    label: 'Reading Path',
    group: 'Understand',
    description: 'Ranked onboarding order — read the right files first',
    keywords: ['onboarding', 'order', 'learn', 'tour', 'guide', 'study'],
  },
  {
    id: 'chat',
    label: 'Chat',
    group: 'Understand',
    description: 'Ask questions grounded in retrieval, cited file by file',
    keywords: ['ask', 'question', 'ai', 'assistant', 'rag', 'retrieval'],
  },
  {
    id: 'graph',
    label: 'File Graph',
    group: 'Structure',
    description: 'Interactive dependency graph of files and imports',
    keywords: ['dependency', 'imports', 'edges', 'nodes', 'map', 'network'],
  },
  {
    id: 'call_graph',
    label: 'Call Graph',
    group: 'Structure',
    description: 'Function-level callers and callees across the codebase',
    keywords: ['functions', 'callers', 'callees', 'invocation', 'trace'],
  },
  {
    id: 'api_surface',
    label: 'API Surface',
    group: 'Structure',
    description: 'Public endpoints, routes, and exported symbols',
    keywords: ['endpoints', 'routes', 'rest', 'public', 'exports', 'http'],
  },
  {
    id: 'report',
    label: 'Health Report',
    group: 'Quality',
    description: 'Scored analytics for maintainability, coupling, and docs',
    keywords: ['health', 'score', 'quality', 'maintainability', 'metrics', 'audit'],
  },
  {
    id: 'dead_code',
    label: 'Dead Code',
    group: 'Quality',
    description: 'Unreachable modules and orphan chains with cleanup scores',
    keywords: ['unused', 'unreachable', 'orphan', 'cleanup', 'prune'],
  },
  {
    id: 'issues',
    label: 'Issues',
    group: 'Quality',
    description: 'Map GitHub issues onto the files most likely responsible',
    keywords: ['bugs', 'github', 'tickets', 'triage'],
  },
  {
    id: 'git_history',
    label: 'Git History',
    group: 'History & PRs',
    description: 'Churn, hotspots, and contribution patterns over time',
    keywords: ['commits', 'churn', 'hotspots', 'blame', 'authors', 'log'],
  },
  {
    id: 'pr_intelligence',
    label: 'PR Risk',
    group: 'History & PRs',
    description: 'Blast radius and risk scoring for a pull request',
    keywords: ['pull request', 'review', 'blast radius', 'diff', 'risk'],
  },
  {
    id: 'architecture_drift',
    label: 'PR Drift',
    group: 'History & PRs',
    description: 'Cycles, coupling shifts, and entry-point changes in a PR',
    keywords: ['drift', 'cycles', 'coupling', 'regression', 'architecture'],
  },
  {
    id: 'impact_analysis',
    label: 'Impact',
    group: 'History & PRs',
    description: 'Downstream propagation paths for a changed symbol',
    keywords: ['propagation', 'downstream', 'blast', 'affected', 'ripple'],
  },
];

/** Ordered group labels, used for grouping palette results. */
export const ANALYSIS_TAB_GROUPS: AnalysisTabGroup[] = [
  'Understand',
  'Structure',
  'Quality',
  'History & PRs',
];

const TAB_IDS = new Set<string>(ANALYSIS_TABS.map((t) => t.id));

/** Narrows an arbitrary string to a known tab id. */
export function isAnalysisTabId(value: string | null | undefined): value is AnalysisTabId {
  return !!value && TAB_IDS.has(value);
}

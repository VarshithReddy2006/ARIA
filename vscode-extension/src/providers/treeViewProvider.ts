/**
 * Repository Explorer tree view provider.
 *
 * Renders a structured tree in the Activity Bar panel with the following shape:
 *
 *   📁 <owner/repo>
 *     ├── 📋 Overview
 *     ├── 🏗  Architecture Health
 *     ├── 📊 Module Stability
 *     ├── 🔌 API Surface
 *     ├── 📈 Git Churn
 *     ├── ☠  Dead Code
 *     └── 📞 Call Graph
 *
 * All data is fetched lazily when the node is expanded for the first time.
 */

import * as vscode from 'vscode';
import { client, extractErrorMessage, RecentRepo } from '../api';
import { StateService } from '../utils/stateService';

// ---------------------------------------------------------------------------
// Tree item kinds
// ---------------------------------------------------------------------------

export type ExplorerNodeKind =
  | 'root'
  | 'section'
  | 'repo'
  | 'overview'
  | 'architecture'
  | 'stability'
  | 'api-surface'
  | 'git-churn'
  | 'dead-code'
  | 'call-graph'
  | 'stat'
  | 'error'
  | 'loading'
  | 'empty';

export class ExplorerNode extends vscode.TreeItem {
  constructor(
    public readonly kind: ExplorerNodeKind,
    label: string,
    collapsible: vscode.TreeItemCollapsibleState,
    public readonly repoId?: string,
    public readonly meta?: Record<string, unknown>
  ) {
    super(label, collapsible);
    this.contextValue = kind;
    this._applyIcon();
    this._applyCommand();
  }

  private _applyIcon(): void {
    const iconMap: Record<ExplorerNodeKind, string> = {
      root: 'library',
      section: 'folder',
      repo: 'repo',
      overview: 'info',
      architecture: 'type-hierarchy',
      stability: 'shield',
      'api-surface': 'symbol-interface',
      'git-churn': 'history',
      'dead-code': 'trash',
      'call-graph': 'call-outgoing',
      stat: 'dash',
      error: 'error',
      loading: 'loading~spin',
      empty: 'circle-slash',
    };
    this.iconPath = new vscode.ThemeIcon(iconMap[this.kind] ?? 'circle');
  }

  private _applyCommand(): void {
    if (this.kind === 'architecture') {
      this.command = {
        command: 'repoIntelligence.openDashboard',
        title: 'Open Dashboard',
      };
    } else if (this.kind === 'api-surface') {
      this.command = {
        command: 'repoIntelligence.showAPISurface',
        title: 'Show API Surface',
      };
    } else if (this.kind === 'call-graph') {
      this.command = {
        command: 'repoIntelligence.showCallGraph',
        title: 'Show Call Graph',
      };
    } else if (this.kind === 'overview') {
      this.command = {
        command: 'repoIntelligence.openDashboard',
        title: 'Open Dashboard',
      };
    }
  }
}

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export class RepositoryExplorerProvider
  implements vscode.TreeDataProvider<ExplorerNode>
{
  private readonly _onDidChangeTreeData = new vscode.EventEmitter<
    ExplorerNode | undefined | void
  >();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  // Lazy-load cache per repo section
  private readonly _cache = new Map<string, ExplorerNode[]>();
  private _recentRepos: RecentRepo[] = [];
  private _loadingRepos = false;

  constructor(private readonly _context: vscode.ExtensionContext) {}

  refresh(): void {
    this._cache.clear();
    this._recentRepos = [];
    this._loadingRepos = false;
    this._onDidChangeTreeData.fire();
  }

  getTreeItem(element: ExplorerNode): vscode.TreeItem {
    return element;
  }

  async getChildren(element?: ExplorerNode): Promise<ExplorerNode[]> {
    // ── Root ──────────────────────────────────────────────────────────────
    if (!element) {
      return this._getRootNodes();
    }

    // ── Repo node → sections ──────────────────────────────────────────────
    if (element.kind === 'repo' && element.repoId) {
      return this._getSections(element.repoId);
    }

    // ── Section nodes → stats ─────────────────────────────────────────────
    if (element.repoId && element.kind !== 'repo') {
      return this._getSectionChildren(element);
    }

    return [];
  }

  // ── Root ───────────────────────────────────────────────────────────────

  private async _getRootNodes(): Promise<ExplorerNode[]> {
    const activeRepo = StateService.getActiveRepository();

    if (!this._loadingRepos && this._recentRepos.length === 0) {
      this._loadingRepos = true;
      try {
        this._recentRepos = await client.getRecentRepos();
      } catch {
        this._recentRepos = [];
      }
    }

    const nodes: ExplorerNode[] = [];

    if (activeRepo) {
      const node = new ExplorerNode(
        'repo',
        `$(star) ${activeRepo}`,
        vscode.TreeItemCollapsibleState.Expanded,
        activeRepo
      );
      node.description = 'active';
      nodes.push(node);
    }

    for (const r of this._recentRepos) {
      if (r.name === activeRepo) {
        continue;
      }
      const node = new ExplorerNode(
        'repo',
        r.name,
        vscode.TreeItemCollapsibleState.Collapsed,
        r.name
      );
      node.description = r.tech_stack.slice(0, 3).join(', ');
      nodes.push(node);
    }

    if (nodes.length === 0) {
      const empty = new ExplorerNode(
        'empty',
        'No repositories connected',
        vscode.TreeItemCollapsibleState.None
      );
      empty.description = 'Run "Repo Intelligence: Set Active Repository"';
      return [empty];
    }

    return nodes;
  }

  // ── Sections for a repo ──────────────────────────────────────────────

  private _getSections(repoId: string): ExplorerNode[] {
    const sections: Array<[ExplorerNodeKind, string]> = [
      ['overview', '$(info) Overview'],
      ['architecture', '$(type-hierarchy) Architecture Health'],
      ['stability', '$(shield) Module Stability'],
      ['api-surface', '$(symbol-interface) API Surface'],
      ['git-churn', '$(history) Git Churn'],
      ['dead-code', '$(trash) Dead Code'],
      ['call-graph', '$(call-outgoing) Call Graph'],
    ];

    return sections.map(([kind, label]) => {
      const node = new ExplorerNode(
        kind,
        label,
        vscode.TreeItemCollapsibleState.Collapsed,
        repoId
      );
      return node;
    });
  }

  // ── Section children (stat rows) ─────────────────────────────────────

  private async _getSectionChildren(
    section: ExplorerNode
  ): Promise<ExplorerNode[]> {
    const cacheKey = `${section.repoId}::${section.kind}`;
    if (this._cache.has(cacheKey)) {
      return this._cache.get(cacheKey)!;
    }

    const repoId = section.repoId!;
    const parts = repoId.split('/');
    if (parts.length !== 2) {
      return [];
    }
    const [owner, repo] = parts;

    const loading = new ExplorerNode(
      'loading',
      'Loading…',
      vscode.TreeItemCollapsibleState.None
    );

    // Fire async, update cache when done
    void this._loadSectionData(section.kind, owner, repo, cacheKey);

    return [loading];
  }

  private async _loadSectionData(
    kind: ExplorerNodeKind,
    owner: string,
    repo: string,
    cacheKey: string
  ): Promise<void> {
    try {
      let nodes: ExplorerNode[] = [];

      switch (kind) {
        case 'overview':
          nodes = await this._loadOverview(owner, repo);
          break;
        case 'architecture':
          nodes = await this._loadArchitecture(owner, repo);
          break;
        case 'api-surface':
          nodes = await this._loadAPISurface(owner, repo);
          break;
        case 'git-churn':
          nodes = await this._loadChurn(owner, repo);
          break;
        case 'call-graph':
          nodes = await this._loadCallGraphStats(owner, repo);
          break;
        default:
          nodes = [
            this._makeStatNode(
              `${kind} data available via Dashboard`,
              '$(arrow-right)'
            ),
          ];
      }

      this._cache.set(cacheKey, nodes);
    } catch (err) {
      const errorNode = new ExplorerNode(
        'error',
        `Error: ${extractErrorMessage(err)}`,
        vscode.TreeItemCollapsibleState.None
      );
      this._cache.set(cacheKey, [errorNode]);
    }
    this._onDidChangeTreeData.fire();
  }

  // ── Section data loaders ─────────────────────────────────────────────

  private async _loadOverview(owner: string, repo: string): Promise<ExplorerNode[]> {
    const details = await client.getAnalysis(owner, repo);
    const analysis = details.analysis;
    const nodes: ExplorerNode[] = [];

    nodes.push(
      this._makeStatNode(
        `Tech: ${(analysis.tech_stack ?? []).slice(0, 4).join(', ') || 'N/A'}`
      )
    );
    nodes.push(
      this._makeStatNode(
        `Dependencies: ${(analysis.dependencies ?? []).length}`
      )
    );

    const arch = details.architecture;
    if (arch?.summary) {
      const summaryNode = new ExplorerNode(
        'stat',
        'Architecture Summary',
        vscode.TreeItemCollapsibleState.None
      );
      summaryNode.description = arch.summary.slice(0, 80);
      summaryNode.tooltip = arch.summary;
      nodes.push(summaryNode);
    }

    return nodes;
  }

  private async _loadArchitecture(owner: string, repo: string): Promise<ExplorerNode[]> {
    try {
      const summary = await client.getArchitectureSummary(owner, repo);
      const nodes: ExplorerNode[] = [];
      nodes.push(
        this._makeStatNode(`Reading order entries: ${(summary.reading_order ?? []).length}`)
      );
      nodes.push(
        this._makeStatNode(`Component relationships: ${(summary.relationships ?? []).length}`)
      );
      return nodes;
    } catch {
      return [
        this._makeStatNode(
          'Not analyzed yet — run Architecture Build',
          '$(warning)'
        ),
      ];
    }
  }

  private async _loadAPISurface(owner: string, repo: string): Promise<ExplorerNode[]> {
    try {
      const stats = await client.getAPISurfaceStats(owner, repo);
      return [
        this._makeStatNode(`Total symbols: ${stats.total_symbols}`),
        this._makeStatNode(`Public: ${stats.public_count}`),
        this._makeStatNode(`Internal: ${stats.internal_count}`),
        this._makeStatNode(`Deprecated: ${stats.deprecated_count}`),
        this._makeStatNode(`Orphan public: ${stats.orphan_public_count}`),
        this._makeStatNode(`Routes: ${stats.route_count}`),
      ];
    } catch {
      return [this._makeStatNode('API Surface not built yet', '$(warning)')];
    }
  }

  private async _loadChurn(owner: string, repo: string): Promise<ExplorerNode[]> {
    try {
      const hotspots = await client.getChurnHotspots(owner, repo, 10, 365);
      const nodes: ExplorerNode[] = [
        this._makeStatNode(`Top ${hotspots.hotspots.length} hotspot files:`),
      ];
      for (const h of hotspots.hotspots.slice(0, 10)) {
        const n = this._makeStatNode(h.file_path, '$(file-code)');
        n.description = `commits: ${h.commit_count}`;
        n.tooltip = `Churn score: ${h.churn_score}`;
        nodes.push(n);
      }
      return nodes;
    } catch {
      return [this._makeStatNode('Churn data not available', '$(warning)')];
    }
  }

  private async _loadCallGraphStats(owner: string, repo: string): Promise<ExplorerNode[]> {
    try {
      const stats = await client.getCallGraphStats(owner, repo);
      return [
        this._makeStatNode(`Functions: ${String(stats.node_count ?? 'N/A')}`),
        this._makeStatNode(`Call edges: ${String(stats.edge_count ?? 'N/A')}`),
        this._makeStatNode(`Entry points: ${String((stats.entry_count as number) ?? 'N/A')}`),
      ];
    } catch {
      return [this._makeStatNode('Call graph not built yet', '$(warning)')];
    }
  }

  // ── Helpers ─────────────────────────────────────────────────────────

  private _makeStatNode(label: string, icon?: string): ExplorerNode {
    const node = new ExplorerNode(
      'stat',
      label,
      vscode.TreeItemCollapsibleState.None
    );
    if (icon) {
      node.iconPath = new vscode.ThemeIcon(icon.replace(/^\$\(/, '').replace(/\)$/, ''));
    }
    return node;
  }
}



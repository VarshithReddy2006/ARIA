import * as vscode from 'vscode';
import { client, extractErrorMessage, FindingsPanel, AdvisorPanel, ExecutionPanel } from '../api';
import { StateService } from '../utils/stateService';
import { WorkspaceEventBus } from '../services/workspaceEventBus';
import { IgnoredRecommendationService } from '../services/ignoredRecommendationService';

function getActiveRepo(): string | undefined {
  const repo = StateService.getActiveRepository() || undefined;
  return repo;
}

import { splitRepo } from '../utils/repoUtils';

export type WorkspaceTreeItemKind =
  | 'category'
  | 'finding'
  | 'phase'
  | 'recommendation'
  | 'batch'
  | 'task'
  | 'critical-path'
  | 'rollback'
  | 'conflict'
  | 'error'
  | 'loading'
  | 'empty';

export class WorkspaceTreeItem extends vscode.TreeItem {
  constructor(
    public readonly kind: WorkspaceTreeItemKind,
    label: string,
    collapsible: vscode.TreeItemCollapsibleState,
    public readonly meta?: Record<string, any>
  ) {
    super(label, collapsible);
    this.contextValue = kind;
    this._applyIcon();
  }

  private _applyIcon(): void {
    const iconMap: Record<WorkspaceTreeItemKind, string> = {
      category: 'folder',
      finding: 'issues',
      phase: 'milestone',
      recommendation: 'lightbulb',
      batch: 'package',
      task: 'tasklist',
      'critical-path': 'git-commit',
      rollback: 'discard',
      conflict: 'warning',
      error: 'error',
      loading: 'loading~spin',
      empty: 'circle-slash',
    };
    this.iconPath = new vscode.ThemeIcon(iconMap[this.kind] ?? 'circle');
  }
}

// ---------------------------------------------------------------------------
// Findings Tree View Provider
// ---------------------------------------------------------------------------

export class FindingsTreeProvider implements vscode.TreeDataProvider<WorkspaceTreeItem>, vscode.Disposable {
  private _onDidChangeTreeData = new vscode.EventEmitter<WorkspaceTreeItem | undefined | void>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  private _findings: FindingsPanel | null = null;
  private _loading = false;
  private _error: string | null = null;
  private _eventSub: vscode.Disposable;
  private _requestId = 0;

  constructor() {
    this._eventSub = WorkspaceEventBus.onEvent((e) => {
      if (
        e.type === 'InspectionFinished' ||
        e.type === 'RepositoryChanged' ||
        e.type === 'WorkspaceReloaded'
      ) {
        this.refresh();
      }
    });
  }

  dispose(): void {
    this._eventSub.dispose();
    this._onDidChangeTreeData.dispose();
  }

  refresh(): void {
    this._requestId++;
    this._findings = null;
    this._error = null;
    this._loading = false;
    this._onDidChangeTreeData.fire();
  }

  getTreeItem(element: WorkspaceTreeItem): vscode.TreeItem {
    return element;
  }

  async getChildren(element?: WorkspaceTreeItem): Promise<WorkspaceTreeItem[]> {
    const repo = getActiveRepo();
    if (!repo) {
      return [new WorkspaceTreeItem('empty', 'No active repository', vscode.TreeItemCollapsibleState.None)];
    }

    let owner: string;
    let repoName: string;
    try {
      [owner, repoName] = splitRepo(repo);
    } catch (err) {
      return [new WorkspaceTreeItem('error', `Invalid repository: ${repo}`, vscode.TreeItemCollapsibleState.None)];
    }

    if (!element) {
      if (this._error) {
        return [new WorkspaceTreeItem('error', `Error: ${this._error}`, vscode.TreeItemCollapsibleState.None)];
      }
      if (!this._findings && !this._loading) {
        this._loading = true;
        const rid = ++this._requestId;
        client.getFindings(owner, repoName)
          .then(data => {
            if (rid !== this._requestId) { return; }
            this._findings = data;
            this._loading = false;
            this._onDidChangeTreeData.fire();
          })
          .catch(err => {
            if (rid !== this._requestId) { return; }
            this._error = extractErrorMessage(err);
            this._loading = false;
            this._onDidChangeTreeData.fire();
          });
        return [new WorkspaceTreeItem('loading', 'Loading findings...', vscode.TreeItemCollapsibleState.None)];
      }

      if (!this._findings || this._findings.total_findings === 0) {
        return [new WorkspaceTreeItem('empty', 'No findings found', vscode.TreeItemCollapsibleState.None)];
      }

      // Group findings by severity
      const severities = ['critical', 'high', 'medium', 'low'];
      return severities.map(sev => {
        const count = this._findings?.by_severity[sev] ?? 0;
        return new WorkspaceTreeItem(
          'category',
          `${sev.toUpperCase()} (${count})`,
          count > 0 ? vscode.TreeItemCollapsibleState.Collapsed : vscode.TreeItemCollapsibleState.None,
          { severity: sev }
        );
      });
    }

    if (element.kind === 'category' && element.meta?.severity) {
      const targetSev = element.meta.severity;
      const filtered = (this._findings?.findings ?? []).filter(f => f.severity === targetSev);
      return filtered.map(f => {
        const item = new WorkspaceTreeItem(
          'finding',
          f.title,
          vscode.TreeItemCollapsibleState.None,
          { finding: f }
        );
        item.description = `[${f.category}] (Conf: ${f.confidence})`;
        item.tooltip = `Affected entities: ${f.affected_entities.join(', ')}`;
        item.command = {
          command: 'repoIntelligence.openFinding',
          title: 'Open Finding',
          arguments: [f]
        };
        return item;
      });
    }

    return [];
  }
}

// ---------------------------------------------------------------------------
// Advisor Tree View Provider
// ---------------------------------------------------------------------------

export class AdvisorTreeProvider implements vscode.TreeDataProvider<WorkspaceTreeItem>, vscode.Disposable {
  private _onDidChangeTreeData = new vscode.EventEmitter<WorkspaceTreeItem | undefined | void>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  private _advisor: AdvisorPanel | null = null;
  private _loading = false;
  private _error: string | null = null;
  private _eventSub: vscode.Disposable;
  private _requestId = 0;

  constructor() {
    this._eventSub = WorkspaceEventBus.onEvent((e) => {
      if (
        e.type === 'AdvisorUpdated' ||
        e.type === 'RepositoryChanged' ||
        e.type === 'WorkspaceReloaded'
      ) {
        this.refresh();
      }
    });
  }

  dispose(): void {
    this._eventSub.dispose();
    this._onDidChangeTreeData.dispose();
  }

  refresh(): void {
    this._requestId++;
    this._advisor = null;
    this._error = null;
    this._loading = false;
    this._onDidChangeTreeData.fire();
  }

  getTreeItem(element: WorkspaceTreeItem): vscode.TreeItem {
    return element;
  }

  async getChildren(element?: WorkspaceTreeItem): Promise<WorkspaceTreeItem[]> {
    const repo = getActiveRepo();
    if (!repo) {
      return [new WorkspaceTreeItem('empty', 'No active repository', vscode.TreeItemCollapsibleState.None)];
    }

    let owner: string;
    let repoName: string;
    try {
      [owner, repoName] = splitRepo(repo);
    } catch (err) {
      return [new WorkspaceTreeItem('error', `Invalid repository: ${repo}`, vscode.TreeItemCollapsibleState.None)];
    }

    if (!element) {
      if (this._error) {
        return [new WorkspaceTreeItem('error', `Error: ${this._error}`, vscode.TreeItemCollapsibleState.None)];
      }
      if (!this._advisor && !this._loading) {
        this._loading = true;
        const rid = ++this._requestId;
        client.getAdvisor(owner, repoName)
          .then(data => {
            if (rid !== this._requestId) { return; }
            this._advisor = data;
            this._loading = false;
            this._onDidChangeTreeData.fire();
          })
          .catch(err => {
            if (rid !== this._requestId) { return; }
            this._error = extractErrorMessage(err);
            this._loading = false;
            this._onDidChangeTreeData.fire();
          });
        return [new WorkspaceTreeItem('loading', 'Loading advisor...', vscode.TreeItemCollapsibleState.None)];
      }

      if (!this._advisor || this._advisor.total_recommendations === 0) {
        return [new WorkspaceTreeItem('empty', 'No recommendations found', vscode.TreeItemCollapsibleState.None)];
      }

      return [
        new WorkspaceTreeItem('category', 'Roadmap Phases', vscode.TreeItemCollapsibleState.Collapsed, { sub: 'roadmap' }),
        new WorkspaceTreeItem('category', 'Prioritized Recommendations', vscode.TreeItemCollapsibleState.Collapsed, { sub: 'recs' }),
      ];
    }

    if (element.kind === 'category') {
      if (element.meta?.sub === 'roadmap') {
        return (this._advisor?.roadmap_summary ?? []).map(p => {
          return new WorkspaceTreeItem(
            'phase',
            p.title || `Phase ${p.phase}`,
            p.recommendation_count > 0 ? vscode.TreeItemCollapsibleState.Collapsed : vscode.TreeItemCollapsibleState.None,
            { phase: p.phase }
          );
        });
      }

      if (element.meta?.sub === 'recs') {
        const activeRepo = getActiveRepo();
        let ignored: string[] = [];
        if (activeRepo) {
          try {
            const [owner, repoName] = splitRepo(activeRepo);
            ignored = IgnoredRecommendationService.getIgnored(owner, repoName);
          } catch {
            // ignore malformed repo
          }
        }
        return (this._advisor?.top_recommendations ?? [])
          .filter(r => !ignored.includes(r.id))
          .map(r => {
            const item = new WorkspaceTreeItem(
              'recommendation',
              r.title,
              vscode.TreeItemCollapsibleState.None,
              { recommendation: r }
            );
            item.description = `[${r.priority}] - ${r.estimated_effort}`;
            return item;
          });
      }
    }

    if (element.kind === 'phase' && element.meta?.phase) {
      const targetPhase = element.meta.phase;
      // We need to fetch the original roadmap recommendations for the phase
      // To keep it simple and deterministic, let's load from the top recommendations that match categories
      const phaseCategories: Record<number, string[]> = {
        1: ['security', 'dependency'],
        2: ['architecture', 'dead_code'],
        3: ['performance', 'complexity'],
        4: ['documentation', 'testing', 'general'],
      };
      const cats = phaseCategories[targetPhase as number] || [];
      const activeRepo = getActiveRepo();
      let ignored: string[] = [];
      if (activeRepo) {
        try {
          const [owner, repoName] = splitRepo(activeRepo);
          ignored = IgnoredRecommendationService.getIgnored(owner, repoName);
        } catch {
          // ignore malformed repo
        }
      }
      const filtered = (this._advisor?.top_recommendations ?? [])
        .filter(r => cats.includes(r.category) && !ignored.includes(r.id));
      if (filtered.length === 0) {
        return [new WorkspaceTreeItem('empty', 'No tasks for this phase', vscode.TreeItemCollapsibleState.None)];
      }
      return filtered.map(r => {
        const item = new WorkspaceTreeItem(
          'recommendation',
          r.title,
          vscode.TreeItemCollapsibleState.None,
          { recommendation: r }
        );
        item.description = `[${r.priority}] - ${r.estimated_effort}`;
        return item;
      });
    }

    return [];
  }
}

// ---------------------------------------------------------------------------
// Execution Tree View Provider
// ---------------------------------------------------------------------------

export class ExecutionTreeProvider implements vscode.TreeDataProvider<WorkspaceTreeItem>, vscode.Disposable {
  private _onDidChangeTreeData = new vscode.EventEmitter<WorkspaceTreeItem | undefined | void>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  private _execution: ExecutionPanel | null = null;
  private _loading = false;
  private _error: string | null = null;
  private _eventSub: vscode.Disposable;
  private _requestId = 0;

  constructor() {
    this._eventSub = WorkspaceEventBus.onEvent((e) => {
      if (
        e.type === 'ExecutionPlanUpdated' ||
        e.type === 'RepositoryChanged' ||
        e.type === 'WorkspaceReloaded'
      ) {
        this.refresh();
      }
    });
  }

  dispose(): void {
    this._eventSub.dispose();
    this._onDidChangeTreeData.dispose();
  }

  refresh(): void {
    this._requestId++;
    this._execution = null;
    this._error = null;
    this._loading = false;
    this._onDidChangeTreeData.fire();
  }

  getTreeItem(element: WorkspaceTreeItem): vscode.TreeItem {
    return element;
  }

  async getChildren(element?: WorkspaceTreeItem): Promise<WorkspaceTreeItem[]> {
    const repo = getActiveRepo();
    if (!repo) {
      return [new WorkspaceTreeItem('empty', 'No active repository', vscode.TreeItemCollapsibleState.None)];
    }

    let owner: string;
    let repoName: string;
    try {
      [owner, repoName] = splitRepo(repo);
    } catch (err) {
      return [new WorkspaceTreeItem('error', `Invalid repository: ${repo}`, vscode.TreeItemCollapsibleState.None)];
    }

    if (!element) {
      if (this._error) {
        return [new WorkspaceTreeItem('error', `Error: ${this._error}`, vscode.TreeItemCollapsibleState.None)];
      }
      if (!this._execution && !this._loading) {
        this._loading = true;
        const rid = ++this._requestId;
        client.getExecutionPlan(owner, repoName)
          .then(data => {
            if (rid !== this._requestId) { return; }
            this._execution = data;
            this._loading = false;
            this._onDidChangeTreeData.fire();
          })
          .catch(err => {
            if (rid !== this._requestId) { return; }
            this._error = extractErrorMessage(err);
            this._loading = false;
            this._onDidChangeTreeData.fire();
          });
        return [new WorkspaceTreeItem('loading', 'Loading execution plan...', vscode.TreeItemCollapsibleState.None)];
      }

      if (!this._execution || this._execution.total_tasks === 0) {
        return [new WorkspaceTreeItem('empty', 'No execution tasks found', vscode.TreeItemCollapsibleState.None)];
      }

      return [
        new WorkspaceTreeItem('category', 'Execution Batches', vscode.TreeItemCollapsibleState.Collapsed, { sub: 'batches' }),
        new WorkspaceTreeItem('category', 'Critical Path', vscode.TreeItemCollapsibleState.Collapsed, { sub: 'critical' }),
        new WorkspaceTreeItem('category', 'Rollback Checkpoints', vscode.TreeItemCollapsibleState.Collapsed, { sub: 'rollback' }),
      ];
    }

    if (element.kind === 'category') {
      if (element.meta?.sub === 'batches') {
        return (this._execution?.batches ?? []).map(b => {
          return new WorkspaceTreeItem(
            'batch',
            b.title || `Batch ${b.order}`,
            b.task_count > 0 ? vscode.TreeItemCollapsibleState.Collapsed : vscode.TreeItemCollapsibleState.None,
            { batchId: b.batch_id }
          );
        });
      }

      if (element.meta?.sub === 'critical') {
        const pathIds = this._execution?.critical_path ?? [];
        if (pathIds.length === 0) {
          return [new WorkspaceTreeItem('empty', 'No critical path computed', vscode.TreeItemCollapsibleState.None)];
        }
        return pathIds.map((id, index) => {
          return new WorkspaceTreeItem(
            'critical-path',
            `Step ${index + 1}: ${id}`,
            vscode.TreeItemCollapsibleState.None
          );
        });
      }

      if (element.meta?.sub === 'rollback') {
        const checkpoints = this._execution?.rollback_checkpoints ?? 0;
        if (checkpoints === 0) {
          return [new WorkspaceTreeItem('empty', 'No rollback checkpoints', vscode.TreeItemCollapsibleState.None)];
        }
        // Let's generate a list of checkpoint task IDs
        const checkpointItems: WorkspaceTreeItem[] = [];
        for (let i = 0; i < checkpoints; i++) {
          checkpointItems.push(new WorkspaceTreeItem(
            'rollback',
            `Checkpoint ${i + 1}`,
            vscode.TreeItemCollapsibleState.None
          ));
        }
        return checkpointItems;
      }
    }

    if (element.kind === 'batch' && element.meta?.batchId) {
      // Find the tasks for this batch from the cache if we had them.
      // Since BatchSummary doesn't list full tasks (only task_count), let's render dummy task items
      // based on the task_count to represent them in the TreeView
      const batch = (this._execution?.batches ?? []).find(b => b.batch_id === element.meta?.batchId);
      if (!batch || batch.task_count === 0) {
        return [new WorkspaceTreeItem('empty', 'No tasks in this batch', vscode.TreeItemCollapsibleState.None)];
      }

      const tasks: WorkspaceTreeItem[] = [];
      for (let i = 0; i < batch.task_count; i++) {
        const taskItem = new WorkspaceTreeItem(
          'task',
          `Task ${i + 1} — Effort: ${batch.estimated_effort}`,
          vscode.TreeItemCollapsibleState.None,
          { taskId: `${batch.batch_id}-task-${i + 1}`, batch }
        );
        tasks.push(taskItem);
      }
      return tasks;
    }

    return [];
  }
}

// ---------------------------------------------------------------------------
// Backend Connection Tree View Provider
// ---------------------------------------------------------------------------

export class BackendConnectionProvider implements vscode.TreeDataProvider<WorkspaceTreeItem>, vscode.Disposable {
  private _onDidChangeTreeData = new vscode.EventEmitter<WorkspaceTreeItem | undefined | void>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  private _status: 'unknown' | 'online' | 'offline' = 'unknown';
  private _loading = false;
  private _repo: string | undefined;
  private _backendUrl: string = '';
  private _eventSub: vscode.Disposable;
  private _requestId = 0;

  constructor() {
    this._eventSub = WorkspaceEventBus.onEvent((e) => {
      // [SYNC] Subscribe to repository changes
      if (
        e.type === 'RepositoryChanged' ||
        e.type === 'WorkspaceReloaded'
      ) {
        this.refresh();
      }
    });
  }

  dispose(): void {
    this._eventSub.dispose();
    this._onDidChangeTreeData.dispose();
  }

  refresh(): void {
    this._requestId++;
    this._status = 'unknown';
    this._loading = false;
    this._repo = undefined;
    this._onDidChangeTreeData.fire();
  }

  getTreeItem(element: WorkspaceTreeItem): vscode.TreeItem {
    return element;
  }

  async getChildren(element?: WorkspaceTreeItem): Promise<WorkspaceTreeItem[]> {

    if (element) {
      return [];
    }

    this._backendUrl = vscode.workspace
      .getConfiguration('repoIntelligence')
      .get<string>('backendUrl', 'http://127.0.0.1:8001');

    this._repo = getActiveRepo();

    if (!this._loading && this._status === 'unknown') {
      this._loading = true;
      const rid = ++this._requestId;
      client.health()
        .then(() => {
          if (rid !== this._requestId) { return; }
          this._status = 'online';
          this._loading = false;
          this._onDidChangeTreeData.fire();
        })
        .catch(() => {
          if (rid !== this._requestId) { return; }
          this._status = 'offline';
          this._loading = false;
          this._onDidChangeTreeData.fire();
        });
      return [new WorkspaceTreeItem('loading', 'Checking backend…', vscode.TreeItemCollapsibleState.None)];
    }

    const statusIcon = this._status === 'online'
      ? '$(check) Online'
      : this._status === 'offline'
        ? '$(circle-slash) Offline'
        : '$(sync~spin) Checking…';

    const urlItem = new WorkspaceTreeItem(
      'category',
      `Backend: ${this._backendUrl}`,
      vscode.TreeItemCollapsibleState.None
    );
    urlItem.iconPath = new vscode.ThemeIcon('plug');
    urlItem.description = statusIcon;

    const repoItem = new WorkspaceTreeItem(
      'category',
      this._repo ? `Repository: ${this._repo}` : 'No active repository',
      vscode.TreeItemCollapsibleState.None
    );
    repoItem.iconPath = new vscode.ThemeIcon(this._repo ? 'repo' : 'circle-slash');

    return [urlItem, repoItem];
  }
}

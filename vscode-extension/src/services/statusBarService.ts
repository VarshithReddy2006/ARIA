import * as vscode from 'vscode';
import { StateService } from '../utils/stateService';
import { client } from '../api';
import { WorkspaceEventBus } from './workspaceEventBus';

export class StatusBarService {
  public static statusBarItem: vscode.StatusBarItem;
  private static disposables: vscode.Disposable[] = [];

  public static initialize(context: vscode.ExtensionContext): void {
    this.statusBarItem = vscode.window.createStatusBarItem(
      vscode.StatusBarAlignment.Left,
      100
    );
    this.statusBarItem.command = 'repoIntelligence.openWorkspace';
    this.statusBarItem.text = '$(sync~spin) Repo Intelligence';
    this.statusBarItem.tooltip = 'Initializing...';
    this.statusBarItem.show();
    this.disposables.push(this.statusBarItem);

    // Subscribe to Event Bus
    this.disposables.push(
      WorkspaceEventBus.onEvent((e) => {
        if (
          e.type === 'RepositoryChanged' ||
          e.type === 'InspectionFinished' ||
          e.type === 'MonitoringUpdated' ||
          e.type === 'WorkspaceReloaded'
        ) {
          void this.update();
        }
      })
    );

    context.subscriptions.push({
      dispose: () => this.dispose(),
    });

    void this.update();
  }

  public static async update(): Promise<void> {
    const repo = StateService.getActiveRepository();
    if (!repo) {
      this.statusBarItem.text = '$(circle-slash) Repo Intel';
      this.statusBarItem.tooltip = 'No active repository selected.';
      return;
    }

    try {
      const parts = repo.split('/');
      if (parts.length !== 2) { return; }
      const [owner, repoName] = parts;

      const overview = await client.getOverview(owner, repoName);
      const health = overview.health?.overall_score !== null ? `${overview.health.overall_score}%` : 'N/A';

      let lastInspected = 'Never';
      if (overview.last_indexed_at) {
        lastInspected = new Date(overview.last_indexed_at * 1000).toLocaleString();
      }

      let monitorStatus = 'Idle';
      try {
        const monitor = await client.getMonitoring(owner, repoName);
        monitorStatus = monitor.status || 'Idle';
      } catch {
        // monitor panel may not be ready
      }

      this.statusBarItem.text = `$(check) Repo: ${repo} (Health: ${health})`;
      this.statusBarItem.tooltip = [
        `Repository: ${repo}`,
        `Health Score: ${health}`,
        `Last Inspection: ${lastInspected}`,
        `Monitoring Status: ${monitorStatus}`,
        'Click to open Workspace Dashboard',
      ].join('\n');
    } catch (err) {
      this.statusBarItem.text = `$(warning) Repo: ${repo} (Offline)`;
      this.statusBarItem.tooltip = `Backend unreachable: ${(err as Error).message}`;
    }
  }

  public static dispose(): void {
    for (const d of this.disposables) {
      d.dispose();
    }
    this.disposables = [];
  }
}

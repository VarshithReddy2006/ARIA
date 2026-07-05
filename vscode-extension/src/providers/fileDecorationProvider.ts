import * as vscode from 'vscode';
import { StateService } from '../utils/stateService';
import { client } from '../api';
import { WorkspaceEventBus } from '../services/workspaceEventBus';

export class RepoIntelFileDecorationProvider implements vscode.FileDecorationProvider, vscode.Disposable {
  private _onDidChangeFileDecorations = new vscode.EventEmitter<vscode.Uri | vscode.Uri[] | undefined>();
  readonly onDidChangeFileDecorations = this._onDidChangeFileDecorations.event;

  private fileIssues = new Map<string, string[]>(); // filePath -> categories[]
  private disposables: vscode.Disposable[] = [];

  constructor(_context: vscode.ExtensionContext) {
    this.disposables.push(
      WorkspaceEventBus.onEvent((e) => {
        if (
          e.type === 'InspectionFinished' ||
          e.type === 'RepositoryChanged' ||
          e.type === 'WorkspaceReloaded'
        ) {
          void this.refresh();
        }
      })
    );
    this.disposables.push(this._onDidChangeFileDecorations);
    void this.refresh();
  }

  public dispose(): void {
    for (const d of this.disposables) {
      d.dispose();
    }
    this.fileIssues.clear();
  }

  private async refresh(): Promise<void> {
    this.fileIssues.clear();
    const repo = StateService.getActiveRepository();
    if (!repo) {
      this._onDidChangeFileDecorations.fire(undefined);
      return;
    }

    try {
      const parts = repo.split('/');
      if (parts.length !== 2) { return; }
      const [owner, repoName] = parts;
      const findings = await client.getFindings(owner, repoName);

      for (const finding of findings.findings) {
        const cat = finding.category.toLowerCase();
        for (const entity of finding.affected_entities) {
          const relPath = entity.split(':')[0].trim();
          if (relPath && !relPath.includes(' ') && relPath.includes('.')) {
            const list = this.fileIssues.get(relPath) || [];
            if (!list.includes(cat)) {
              list.push(cat);
              this.fileIssues.set(relPath, list);
            }
          }
        }
      }
    } catch {
      // ignore
    }

    this._onDidChangeFileDecorations.fire(undefined);
  }

  provideFileDecoration(uri: vscode.Uri, _token: vscode.CancellationToken): vscode.FileDecoration | undefined {
    const workspaceFolder = vscode.workspace.getWorkspaceFolder(uri);
    if (!workspaceFolder) { return undefined; }

    const relPath = vscode.workspace.asRelativePath(uri, false);
    const categories = this.fileIssues.get(relPath);
    if (!categories || categories.length === 0) { return undefined; }

    if (categories.includes('security')) {
      return {
        badge: '🔒',
        tooltip: 'Security Hotspot',
        color: new vscode.ThemeColor('charts.red'),
      };
    }
    if (categories.includes('performance')) {
      return {
        badge: '⚡',
        tooltip: 'Performance Hotspot',
        color: new vscode.ThemeColor('charts.orange'),
      };
    }
    if (categories.includes('architecture')) {
      return {
        badge: '🏗',
        tooltip: 'Architecture Issue',
        color: new vscode.ThemeColor('charts.blue'),
      };
    }
    if (categories.includes('dead_code')) {
      return {
        badge: '💀',
        tooltip: 'Dead Code',
        color: new vscode.ThemeColor('charts.purple'),
      };
    }

    return {
      badge: '⚠',
      tooltip: `Findings: ${categories.join(', ')}`,
      color: new vscode.ThemeColor('charts.yellow'),
    };
  }
}

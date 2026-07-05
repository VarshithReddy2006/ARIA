import * as vscode from 'vscode';
import * as path from 'path';
import { client } from '../api';
import { StateService } from '../utils/stateService';
import { WorkspaceEventBus } from '../services/workspaceEventBus';

export class RepoIntelDiagnosticProvider implements vscode.Disposable {
  private diagnosticCollection: vscode.DiagnosticCollection;
  private disposables: vscode.Disposable[] = [];
  private requestId = 0;

  constructor(_context: vscode.ExtensionContext) {
    this.diagnosticCollection = vscode.languages.createDiagnosticCollection('repo-intelligence');
    this.disposables.push(this.diagnosticCollection);

    // Subscribe to Event Bus
    this.disposables.push(
      WorkspaceEventBus.onEvent((e) => {
        if (
          e.type === 'InspectionFinished' ||
          e.type === 'RepositoryChanged' ||
          e.type === 'WorkspaceReloaded'
        ) {
          void this.refreshDiagnostics();
        }
      })
    );

    void this.refreshDiagnostics();
  }

  public dispose(): void {
    this.diagnosticCollection.clear();
    for (const d of this.disposables) {
      d.dispose();
    }
  }

  public async refreshDiagnostics(): Promise<void> {
    const rid = ++this.requestId;
    this.diagnosticCollection.clear();
    const repo = StateService.getActiveRepository();
    if (!repo) { return; }

    const parts = repo.split('/');
    if (parts.length !== 2) { return; }
    const [owner, repoName] = parts;

    try {
      const findings = await client.getFindings(owner, repoName);
      if (rid !== this.requestId) { return; }
      const diagnosticsMap = new Map<string, vscode.Diagnostic[]>();

      const workspaceFolders = vscode.workspace.workspaceFolders;
      if (!workspaceFolders) { return; }
      const workspaceRoot = workspaceFolders[0].uri.fsPath;

      for (const finding of findings.findings) {
        const severity = this.mapSeverity(finding.severity);

        for (const entity of finding.affected_entities) {
          // Parse entity (e.g. "src/auth.ts:15" or "src/auth.ts")
          const entityParts = entity.split(':');
          const relPath = entityParts[0].trim();
          
          // Skip if it doesn't look like a file relative path
          if (!relPath || relPath.includes(' ') || !relPath.includes('.')) {
            continue;
          }

          const lineNum = entityParts[1] ? parseInt(entityParts[1], 10) : 1;
          const line = Math.max(0, lineNum - 1);
          const range = new vscode.Range(line, 0, line, 100);

          const fsPath = path.isAbsolute(relPath) ? relPath : path.join(workspaceRoot, relPath);
          const uriStr = vscode.Uri.file(fsPath).toString();

          const diagnostic = new vscode.Diagnostic(
            range,
            `[${finding.category.toUpperCase()}] ${finding.title}\n\nConfidence: ${finding.confidence}\nRecommendation ID: ${finding.id}`,
            severity
          );
          diagnostic.source = 'Repo Intelligence';
          diagnostic.code = finding.id;

          const list = diagnosticsMap.get(uriStr) || [];
          list.push(diagnostic);
          diagnosticsMap.set(uriStr, list);
        }
      }

      // Apply diagnostics
      for (const [uriStr, list] of diagnosticsMap.entries()) {
        this.diagnosticCollection.set(vscode.Uri.parse(uriStr), list);
      }
    } catch {
      // ignore fetching/parsing errors silently
    }
  }

  private mapSeverity(sev: string): vscode.DiagnosticSeverity {
    switch (sev.toLowerCase()) {
      case 'critical':
      case 'high':
        return vscode.DiagnosticSeverity.Error;
      case 'medium':
        return vscode.DiagnosticSeverity.Warning;
      case 'low':
        return vscode.DiagnosticSeverity.Information;
      case 'info':
      default:
        return vscode.DiagnosticSeverity.Hint;
    }
  }
}

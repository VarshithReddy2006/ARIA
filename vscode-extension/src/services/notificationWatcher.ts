import * as vscode from 'vscode';
import { WorkspaceEventBus } from './workspaceEventBus';
import { StateService } from '../utils/stateService';
import { client } from '../api';

export class NotificationWatcher implements vscode.Disposable {
  private disposables: vscode.Disposable[] = [];
  private lastFired = new Map<string, number>();
  private throttleIntervalMs = 5000; // 5 seconds throttling

  private previousHealthScore: number | null = null;

  constructor(context: vscode.ExtensionContext) {
    this.disposables.push(
      WorkspaceEventBus.onEvent((e) => {
        void this.handleEvent(e);
      })
    );
    context.subscriptions.push(this);
  }

  public dispose(): void {
    for (const d of this.disposables) {
      d.dispose();
    }
  }

  private async handleEvent(e: any): Promise<void> {
    const now = Date.now();
    const lastTime = this.lastFired.get(e.type) || 0;
    if (now - lastTime < this.throttleIntervalMs) {
      return; // throttled
    }
    this.lastFired.set(e.type, now);

    const repo = StateService.getActiveRepository();
    if (!repo) { return; }
    const parts = repo.split('/');
    if (parts.length !== 2) { return; }
    const [owner, repoName] = parts;

    switch (e.type) {
      case 'InspectionFinished':
        try {
          const overview = await client.getOverview(owner, repoName);
          const score = overview.health?.overall_score;
          if (score !== undefined && score !== null) {
            if (this.previousHealthScore !== null && score < this.previousHealthScore) {
              void vscode.window.showWarningMessage(
                `[Repo Intel] Repository health degraded from ${this.previousHealthScore}% to ${score}%!`
              );
            } else {
              void vscode.window.showInformationMessage(
                `[Repo Intel] Inspection completed successfully. Health Score: ${score}%`
              );
            }
            this.previousHealthScore = score;
          }

          // Check if there are new critical findings
          const findings = await client.getFindings(owner, repoName);
          const critical = (findings.findings || []).filter(
            (f) => f.severity.toLowerCase() === 'critical'
          );
          if (critical.length > 0) {
            void vscode.window.showWarningMessage(
              `[Repo Intel] Warning: ${critical.length} critical security/architecture issues detected!`
            );
          }
        } catch {
          // ignore
        }
        break;

      case 'MonitoringUpdated':
        void vscode.window.showInformationMessage('[Repo Intel] Continuous monitoring run completed.');
        break;

      case 'AdvisorUpdated':
        void vscode.window.showInformationMessage('[Repo Intel] Advisor roadmap updated with new recommendations.');
        break;

      case 'ExecutionPlanUpdated':
        void vscode.window.showInformationMessage('[Repo Intel] Execution plan regenerated with updated checkpoints.');
        break;
    }
  }
}

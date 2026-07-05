import * as vscode from 'vscode';
import { StateService } from '../utils/stateService';
import { client } from '../api';

export class RepoIntelSearchProvider {
  public static async showSearch(): Promise<void> {
    const repo = StateService.getActiveRepository();
    if (!repo) {
      void vscode.window.showWarningMessage('No active repository selected.');
      return;
    }

    const parts = repo.split('/');
    if (parts.length !== 2) { return; }
    const [owner, repoName] = parts;

    // Show quickpick with loading
    const quickPick = vscode.window.createQuickPick();
    quickPick.placeholder = 'Search Findings, Symbols, Recommendations, Tasks, and Snapshots...';
    quickPick.busy = true;
    quickPick.show();

    try {
      // Fetch data in parallel
      const [findingsData, advisorData, executionData] = await Promise.all([
        client.getFindings(owner, repoName).catch(() => null),
        client.getAdvisor(owner, repoName).catch(() => null),
        client.getExecutionPlan(owner, repoName).catch(() => null)
      ]);

      const items: vscode.QuickPickItem[] = [];

      // 1. Findings
      if (findingsData && findingsData.findings) {
        for (const f of findingsData.findings) {
          items.push({
            label: `$(bug) Finding: ${f.title}`,
            description: `[${f.severity}] in ${f.affected_entities.join(', ')}`,
            detail: `Category: ${f.category} — ${f.recommendation_count} recommendations`,
            buttons: [],
            // Keep meta to open later
            meta: { type: 'finding', data: f }
          } as vscode.QuickPickItem & { meta: any });
        }
      }

      // 2. Advisor Recommendations
      if (advisorData && advisorData.top_recommendations) {
        for (const rec of advisorData.top_recommendations) {
          items.push({
            label: `$(lightbulb) Recommendation: ${rec.title}`,
            description: `Priority: ${rec.priority} — Effort: ${rec.estimated_effort}`,
            detail: `Category: ${rec.category}`,
            meta: { type: 'recommendation', data: rec }
          } as vscode.QuickPickItem & { meta: any });
        }
      }

      // 3. Execution Plan Tasks
      if (executionData && executionData.batches) {
        for (const batch of executionData.batches) {
          for (let i = 0; i < batch.task_count; i++) {
            items.push({
              label: `$(tasklist) Task: ${batch.title} — Task ${i + 1}`,
              description: `Status: Pending — Effort: ${batch.estimated_effort}`,
              detail: `Batch: ${batch.title} (${batch.parallel ? 'Parallel' : 'Sequential'})`,
              meta: { type: 'task', data: { taskId: `${batch.batch_id}-task-${i + 1}`, batch } }
            } as vscode.QuickPickItem & { meta: any });
          }
        }
      }

      quickPick.items = items;
      quickPick.busy = false;

      quickPick.onDidAccept(async () => {
        const selected = quickPick.selectedItems[0] as any;
        quickPick.hide();
        if (!selected || !selected.meta) { return; }

        const { type, data } = selected.meta;
        
        if (type === 'finding') {
          // Open the first affected file
          const entity = data.affected_entities[0];
          if (entity) {
            const relPath = entity.split(':')[0].trim();
            const workspaceFolders = vscode.workspace.workspaceFolders;
            if (workspaceFolders && relPath.includes('.')) {
              const uri = vscode.Uri.joinPath(workspaceFolders[0].uri, relPath);
              try {
                const doc = await vscode.workspace.openTextDocument(uri);
                await vscode.window.showTextDocument(doc);
              } catch {
                // ignore if file cannot be opened
              }
            }
          }
          // Also focus findings view
          void vscode.commands.executeCommand('repoIntelligence.openFindings');
        } else if (type === 'recommendation') {
          void vscode.commands.executeCommand('repoIntelligence.openAdvisor');
        } else if (type === 'task') {
          void vscode.commands.executeCommand('repoIntelligence.openExecutionPlan');
        }
      });
    } catch (err) {
      quickPick.busy = false;
      quickPick.hide();
      void vscode.window.showErrorMessage('Search failed to load workspace index metadata.');
    }
  }
}

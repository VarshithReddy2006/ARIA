import * as vscode from 'vscode';
import { StateService } from '../utils/stateService';
import { client } from '../api';
import { WorkspaceEventBus } from '../services/workspaceEventBus';

export class RepoIntelInlineDecorationProvider implements vscode.Disposable {
  private decorationType: vscode.TextEditorDecorationType;
  private disposables: vscode.Disposable[] = [];
  private findingsCache: any[] = [];

  constructor(context: vscode.ExtensionContext) {
    this.decorationType = vscode.window.createTextEditorDecorationType({
      overviewRulerColor: new vscode.ThemeColor('editorOverviewRuler.warningForeground'),
      overviewRulerLane: vscode.OverviewRulerLane.Right,
      light: {
        after: {
          contentText: ' ⚠ Repo Intel Finding',
          color: new vscode.ThemeColor('editorWarning.foreground'),
        }
      },
      dark: {
        after: {
          contentText: ' ⚠ Repo Intel Finding',
          color: new vscode.ThemeColor('editorWarning.foreground'),
        }
      }
    });
    this.disposables.push(this.decorationType);

    // Refresh decorations when event bus fires or editors change
    this.disposables.push(
      WorkspaceEventBus.onEvent((e) => {
        if (
          e.type === 'InspectionFinished' ||
          e.type === 'RepositoryChanged' ||
          e.type === 'WorkspaceReloaded'
        ) {
          void this.refreshCacheAndDecorate();
        }
      })
    );

    this.disposables.push(
      vscode.window.onDidChangeActiveTextEditor((editor) => {
        if (editor) {
          this.applyDecorations(editor);
        }
      })
    );

    context.subscriptions.push(this);
    void this.refreshCacheAndDecorate();
  }

  public dispose(): void {
    for (const d of this.disposables) {
      d.dispose();
    }
  }

  private async refreshCacheAndDecorate(): Promise<void> {
    const repo = StateService.getActiveRepository();
    if (!repo) {
      this.findingsCache = [];
      this.clearAllDecorations();
      return;
    }

    const parts = repo.split('/');
    if (parts.length !== 2) { return; }
    const [owner, repoName] = parts;

    try {
      const findings = await client.getFindings(owner, repoName);
      // Filter only critical/high findings, and security/performance categories
      this.findingsCache = (findings.findings || []).filter(
        (f) =>
          f.severity.toLowerCase() === 'critical' ||
          f.severity.toLowerCase() === 'high' ||
          f.category.toLowerCase() === 'security' ||
          f.category.toLowerCase() === 'performance'
      );
      this.applyDecorationsToAllVisible();
    } catch {
      // ignore
    }
  }

  private applyDecorationsToAllVisible(): void {
    for (const editor of vscode.window.visibleTextEditors) {
      this.applyDecorations(editor);
    }
  }

  private clearAllDecorations(): void {
    for (const editor of vscode.window.visibleTextEditors) {
      editor.setDecorations(this.decorationType, []);
    }
  }

  private applyDecorations(editor: vscode.TextEditor): void {
    if (this.findingsCache.length === 0) {
      editor.setDecorations(this.decorationType, []);
      return;
    }

    const relPath = vscode.workspace.asRelativePath(editor.document.uri, false);
    const decorations: vscode.DecorationOptions[] = [];

    for (const finding of this.findingsCache) {
      for (const entity of finding.affected_entities) {
        const parts = entity.split(':');
        const entityPath = parts[0].trim();
        if (entityPath === relPath) {
          const lineNum = parts[1] ? parseInt(parts[1], 10) : 1;
          const line = Math.max(0, lineNum - 1);
          const range = new vscode.Range(line, 0, line, 100);

          decorations.push({
            range,
            hoverMessage: new vscode.MarkdownString(
              `### ⚠ Repo Intelligence Finding\n\n` +
              `**Title**: ${finding.title}\n` +
              `**Severity**: ${finding.severity.toUpperCase()}\n` +
              `**Category**: ${finding.category}\n` +
              `**Confidence**: ${finding.confidence}\n\n` +
              `*Click lightbulb or context menu for details & recommendations.*`
            ),
          });
        }
      }
    }

    editor.setDecorations(this.decorationType, decorations);
  }
}

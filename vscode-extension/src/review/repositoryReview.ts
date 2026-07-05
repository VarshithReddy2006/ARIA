import * as vscode from 'vscode';
import { client, extractErrorMessage } from '../api';
import { StateService } from '../utils/stateService';
import { GitService } from '../services/gitService';
import { getNonce, BASE_CSS } from '../utils/webview';

export class RepositoryReviewPanel {
  static readonly viewType = 'repoIntelligenceReview';
  private static _panel: vscode.WebviewPanel | undefined;

  public static show(extensionUri: vscode.Uri, title: string, findings: any[]): void {
    if (RepositoryReviewPanel._panel) {
      RepositoryReviewPanel._panel.title = title;
      RepositoryReviewPanel._panel.reveal(vscode.ViewColumn.Beside);
      RepositoryReviewPanel.updateHtml(RepositoryReviewPanel._panel.webview, title, findings);
      return;
    }

    const panel = vscode.window.createWebviewPanel(
      RepositoryReviewPanel.viewType,
      title,
      vscode.ViewColumn.Beside,
      {
        enableScripts: true,
        retainContextWhenHidden: true,
        localResourceRoots: [vscode.Uri.joinPath(extensionUri, 'out')],
      }
    );

    RepositoryReviewPanel._panel = panel;
    panel.onDidDispose(() => {
      RepositoryReviewPanel._panel = undefined;
    });

    RepositoryReviewPanel.updateHtml(panel.webview, title, findings);
  }

  private static updateHtml(webview: vscode.Webview, title: string, findings: any[]): void {
    const nonce = getNonce();
    
    let findingsListHtml = '';
    if (findings.length === 0) {
      findingsListHtml = '<p class="empty-msg">No findings found in the reviewed scope.</p>';
    } else {
      findingsListHtml = findings
        .map(
          (f) => `
        <div class="finding-card ${f.severity.toLowerCase()}">
          <div class="finding-header">
            <span class="badge ${f.severity.toLowerCase()}">${f.severity.toUpperCase()}</span>
            <span class="category">[${f.category}]</span>
            <h3>${f.title}</h3>
          </div>
          <p class="desc">${f.description || ''}</p>
          <div class="affected">
            <strong>Affected Entities:</strong>
            <ul>
              ${f.affected_entities.map((e: string) => `<li><code>${e}</code></li>`).join('')}
            </ul>
          </div>
          ${
            f.recommendations && f.recommendations.length > 0
              ? `
          <div class="recommendations">
            <strong>Recommendations:</strong>
            <ul>
              ${f.recommendations.map((r: string) => `<li>${r}</li>`).join('')}
            </ul>
          </div>`
              : ''
          }
        </div>`
        )
        .join('');
    }

    webview.html = `<!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src ${webview.cspSource} 'unsafe-inline'; script-src 'nonce-${nonce}';">
      <title>${title}</title>
      <style>
        ${BASE_CSS}
        body { padding: 20px; }
        h1 { margin-bottom: 20px; font-size: 1.6rem; border-bottom: 1px solid var(--border); padding-bottom: 10px; }
        .finding-card {
          border: 1px solid var(--border);
          border-radius: 6px;
          padding: 15px;
          margin-bottom: 15px;
          background: var(--input-bg);
        }
        .finding-card.critical { border-left: 4px solid var(--error); }
        .finding-card.high { border-left: 4px solid var(--error); }
        .finding-card.medium { border-left: 4px solid var(--warn); }
        .finding-card.low { border-left: 4px solid var(--link); }
        .finding-header { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
        .badge {
          padding: 2px 6px;
          border-radius: 4px;
          font-size: 0.75rem;
          font-weight: bold;
        }
        .badge.critical, .badge.high { background: var(--error); color: white; }
        .badge.medium { background: var(--warn); color: black; }
        .badge.low { background: var(--badge-bg); color: var(--badge-fg); }
        .category { font-weight: bold; color: var(--muted); }
        .desc { margin-bottom: 12px; }
        .affected, .recommendations { margin-top: 10px; font-size: 0.9rem; }
        ul { margin-left: 20px; margin-top: 5px; }
        .empty-msg { color: var(--muted); font-style: italic; }
      </style>
    </head>
    <body>
      <h1>${title}</h1>
      <div id="findings-list">
        ${findingsListHtml}
      </div>
    </body>
    </html>`;
  }
}

export class RepositoryReview {
  private static async getRepoContext(): Promise<[string, string] | null> {
    const repo = StateService.getActiveRepository();
    if (!repo) {
      void vscode.window.showWarningMessage('No active repository selected.');
      return null;
    }
    const parts = repo.split('/');
    if (parts.length !== 2) { return null; }
    return [parts[0], parts[1]];
  }

  public static async reviewFile(extensionUri: vscode.Uri, uri?: vscode.Uri): Promise<void> {
    const fileUri = uri || vscode.window.activeTextEditor?.document.uri;
    if (!fileUri) {
      void vscode.window.showWarningMessage('No file open to review.');
      return;
    }

    const relPath = vscode.workspace.asRelativePath(fileUri, false);
    const context = await this.getRepoContext();
    if (!context) { return; }
    const [owner, repoName] = context;

    await vscode.window.withProgress(
      { location: vscode.ProgressLocation.Notification, title: `Reviewing ${relPath}...` },
      async () => {
        try {
          const findings = await client.getFindings(owner, repoName);
          // Filter findings affecting this file
          const fileFindings = (findings.findings || []).filter((f) =>
            f.affected_entities.some((e: string) => e.split(':')[0].trim() === relPath)
          );
          RepositoryReviewPanel.show(extensionUri, `Review: ${relPath}`, fileFindings);
        } catch (err) {
          void vscode.window.showErrorMessage(`Review failed: ${extractErrorMessage(err)}`);
        }
      }
    );
  }

  public static async reviewModule(extensionUri: vscode.Uri, uri?: vscode.Uri): Promise<void> {
    const fileUri = uri || vscode.window.activeTextEditor?.document.uri;
    if (!fileUri) {
      void vscode.window.showWarningMessage('No folder/module selected.');
      return;
    }

    const relPath = vscode.workspace.asRelativePath(fileUri, false);
    const context = await this.getRepoContext();
    if (!context) { return; }
    const [owner, repoName] = context;

    await vscode.window.withProgress(
      { location: vscode.ProgressLocation.Notification, title: `Reviewing Module ${relPath}...` },
      async () => {
        try {
          const findings = await client.getFindings(owner, repoName);
          // Filter findings affecting files in this module subdirectory
          const moduleFindings = (findings.findings || []).filter((f) =>
            f.affected_entities.some((e: string) => e.split(':')[0].trim().startsWith(relPath))
          );
          RepositoryReviewPanel.show(extensionUri, `Review Module: ${relPath}`, moduleFindings);
        } catch (err) {
          void vscode.window.showErrorMessage(`Review failed: ${extractErrorMessage(err)}`);
        }
      }
    );
  }

  public static async reviewChanges(extensionUri: vscode.Uri, stagedOnly = false): Promise<void> {
    const context = await this.getRepoContext();
    if (!context) { return; }
    const [owner, repoName] = context;

    const files = stagedOnly ? GitService.getStagedFiles() : GitService.getChangedFiles();
    if (files.length === 0) {
      void vscode.window.showInformationMessage(
        stagedOnly ? 'No staged changes detected.' : 'No modified changes detected.'
      );
      return;
    }

    const title = stagedOnly ? 'Review: Staged Changes' : 'Review: Working Tree Changes';

    await vscode.window.withProgress(
      { location: vscode.ProgressLocation.Notification, title: 'Reviewing Git changes...' },
      async () => {
        try {
          const findings = await client.getFindings(owner, repoName);
          // Filter findings affecting any changed file
          const filtered = (findings.findings || []).filter((f) =>
            f.affected_entities.some((e: string) => {
              const fPath = e.split(':')[0].trim();
              return files.includes(fPath);
            })
          );
          RepositoryReviewPanel.show(extensionUri, title, filtered);
        } catch (err) {
          void vscode.window.showErrorMessage(`Review failed: ${extractErrorMessage(err)}`);
        }
      }
    );
  }

  public static async reviewRepository(extensionUri: vscode.Uri): Promise<void> {
    const context = await this.getRepoContext();
    if (!context) { return; }
    const [owner, repoName] = context;

    await vscode.window.withProgress(
      { location: vscode.ProgressLocation.Notification, title: 'Reviewing Repository...' },
      async () => {
        try {
          const findings = await client.getFindings(owner, repoName);
          RepositoryReviewPanel.show(
            extensionUri,
            `Review: ${owner}/${repoName}`,
            findings.findings || []
          );
        } catch (err) {
          void vscode.window.showErrorMessage(`Review failed: ${extractErrorMessage(err)}`);
        }
      }
    );
  }
}

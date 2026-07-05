import * as vscode from 'vscode';
import { RepoIntelligenceClient, extractErrorMessage, OverviewPanel } from '../api';
import { getNonce, BASE_CSS } from '../utils/webview';

export class WorkspaceDashboardPanel {
  static readonly viewType = 'repoIntelligenceWorkspaceDashboard';
  private static _panels = new Map<string, WorkspaceDashboardPanel>();

  private readonly _panel: vscode.WebviewPanel;
  private readonly _owner: string;
  private readonly _repo: string;
  private readonly _client: RepoIntelligenceClient;

  static createOrShow(
    extensionUri: vscode.Uri,
    owner: string,
    repo: string,
    client: RepoIntelligenceClient
  ): void {
    const key = `${owner}/${repo}`;
    const existing = WorkspaceDashboardPanel._panels.get(key);
    if (existing) {
      existing._panel.reveal(vscode.ViewColumn.One);
      return;
    }

    const panel = vscode.window.createWebviewPanel(
      WorkspaceDashboardPanel.viewType,
      `Workspace Overview — ${key}`,
      vscode.ViewColumn.One,
      {
        enableScripts: true,
        retainContextWhenHidden: true,
        localResourceRoots: [vscode.Uri.joinPath(extensionUri, 'out')],
      }
    );

    const instance = new WorkspaceDashboardPanel(panel, owner, repo, client);
    WorkspaceDashboardPanel._panels.set(key, instance);
    panel.onDidDispose(() => WorkspaceDashboardPanel._panels.delete(key));
  }

  private constructor(
    panel: vscode.WebviewPanel,
    owner: string,
    repo: string,
    client: RepoIntelligenceClient
  ) {
    this._panel = panel;
    this._owner = owner;
    this._repo = repo;
    this._client = client;

    this._panel.webview.html = this._buildLoadingHtml();
    this._panel.webview.onDidReceiveMessage(this._handleMessage.bind(this));
    void this._loadData();
  }

  private async _loadData(): Promise<void> {
    try {
      const overview = await this._client.getOverview(this._owner, this._repo);
      this._panel.webview.html = this._buildHtml(overview);
    } catch (err) {
      this._panel.webview.html = this._buildErrorHtml(extractErrorMessage(err));
    }
  }

  private _handleMessage(msg: { type: string }): void {
    if (msg.type === 'refresh') {
      this._panel.webview.html = this._buildLoadingHtml();
      void this._loadData();
    }
  }

  private _buildLoadingHtml(): string {
    return /* html */ `<!DOCTYPE html>
<html><head>
<meta charset="UTF-8">
<style>${BASE_CSS}
.center{display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh;gap:12px;color:var(--muted);}
.spinner{width:28px;height:28px;border:3px solid var(--border);border-top-color:var(--link);border-radius:50%;animation:spin .7s linear infinite;}
@keyframes spin{to{transform:rotate(360deg);}}
</style></head>
<body><div class="center"><div class="spinner"></div><span>Loading overview…</span></div></body></html>`;
  }

  private _buildErrorHtml(error: string): string {
    return /* html */ `<!DOCTYPE html>
<html><head><meta charset="UTF-8"><style>${BASE_CSS}</style></head>
<body style="padding:20px"><div class="error-banner">⚠ ${error}</div></body></html>`;
  }

  private _buildHtml(overview: OverviewPanel): string {
    const nonce = getNonce();
    return /* html */ `<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-${nonce}';">
<style>
  ${BASE_CSS}
  .card { background: var(--badge-bg); border: 1px solid var(--border); border-radius: 6px; padding: 12px; margin-bottom: 12px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin-bottom: 16px; }
  .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); padding-bottom: 8px; margin-bottom: 16px; }
  .metric { font-size: 24px; font-weight: bold; margin-top: 4px; }
  .label { font-size: 11px; color: var(--muted); text-transform: uppercase; }
</style>
</head>
<body style="padding:16px;">
  <div class="header">
    <h2>📁 ${overview.repository} Overview</h2>
    <button onclick="vscode.postMessage({type:'refresh'})">Refresh</button>
  </div>

  <div class="grid">
    <div class="card">
      <div class="label">Primary Language</div>
      <div class="metric">${overview.primary_language || 'N/A'}</div>
    </div>
    <div class="card">
      <div class="label">Total Files</div>
      <div class="metric">${overview.total_files}</div>
    </div>
    <div class="card">
      <div class="label">Total Symbols</div>
      <div class="metric">${overview.total_symbols}</div>
    </div>
    <div class="card">
      <div class="label">Architecture Style</div>
      <div class="metric">${overview.architecture_style || 'N/A'}</div>
    </div>
  </div>

  <div class="card">
    <h3>🏥 Health Snapshot</h3>
    <p>Overall Score: <strong>${overview.health.overall_score !== null ? overview.health.overall_score.toFixed(1) + '%' : 'N/A'}</strong></p>
    <p>Critical: ${overview.health.critical_count} | High: ${overview.health.high_count} | Medium: ${overview.health.medium_count} | Low: ${overview.health.low_count}</p>
  </div>

  <script nonce="${nonce}">
    const vscode = acquireVsCodeApi();
  </script>
</body>
</html>`;
  }
}

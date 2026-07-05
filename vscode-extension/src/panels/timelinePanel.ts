import * as vscode from 'vscode';
import { RepoIntelligenceClient, TimelinePanel as TimelinePanelType, MonitorPanel } from '../api';
import { getNonce, BASE_CSS } from '../utils/webview';

export class TimelinePanel {
  static readonly viewType = 'repoIntelligenceTimeline';
  private static _panels = new Map<string, TimelinePanel>();

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
    const existing = TimelinePanel._panels.get(key);
    if (existing) {
      existing._panel.reveal(vscode.ViewColumn.One);
      return;
    }

    const panel = vscode.window.createWebviewPanel(
      TimelinePanel.viewType,
      `Timeline — ${key}`,
      vscode.ViewColumn.One,
      {
        enableScripts: true,
        retainContextWhenHidden: true,
        localResourceRoots: [vscode.Uri.joinPath(extensionUri, 'out')],
      }
    );

    const instance = new TimelinePanel(panel, owner, repo, client);
    TimelinePanel._panels.set(key, instance);
    panel.onDidDispose(() => TimelinePanel._panels.delete(key));
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
      const timeline = await this._client.getTimeline(this._owner, this._repo);
      const monitor = await this._client.getMonitoring(this._owner, this._repo);
      this._panel.webview.html = this._buildHtml(timeline, monitor);
    } catch (err) {
      this._panel.webview.html = this._buildHtml(
        { repository: `${this._owner}/${this._repo}`, snapshot_count: 0, timeline: [], trends: {}, metadata: {} },
        {
          repository: `${this._owner}/${this._repo}`,
          status: 'unknown',
          last_run_at: null,
          last_trigger: null,
          run_count: 0,
          health_trend: null,
          overall_health_score: null,
          recent_runs: [],
          alerts: [],
          metadata: {}
        }
      );
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
<body><div class="center"><div class="spinner"></div><span>Loading timeline…</span></div></body></html>`;
  }

  private _buildHtml(timeline: TimelinePanelType, monitor: MonitorPanel): string {
    const nonce = getNonce();
    const timelineRows = timeline.timeline.map(e => {
      const date = new Date(e.timestamp * 1000).toLocaleString();
      return `<tr>
        <td>${date}</td>
        <td><code>${e.commit_hash || 'N/A'}</code></td>
        <td>${e.summary || 'Snapshot update'}</td>
      </tr>`;
    }).join('');

    const monitorRows = (monitor.recent_runs || []).map(run => {
      return `<li>
        Run <code>${run.id?.slice(0, 8) || 'N/A'}</code> (Trigger: ${run.trigger})
      </li>`;
    }).join('');

    return /* html */ `<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-${nonce}';">
<style>
  ${BASE_CSS}
  .card { background: var(--badge-bg); border: 1px solid var(--border); border-radius: 6px; padding: 12px; margin-bottom: 12px; }
  .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); padding-bottom: 8px; margin-bottom: 16px; }
  table { width: 100%; border-collapse: collapse; margin-top: 8px; }
  th, td { text-align: left; padding: 8px; border-bottom: 1px solid var(--border); }
</style>
</head>
<body style="padding:16px;">
  <div class="header">
    <h2>📈 Evolution Timeline & Monitoring History</h2>
    <button onclick="vscode.postMessage({type:'refresh'})">Refresh</button>
  </div>

  <div class="card">
    <h3>Snapshots (${timeline.snapshot_count})</h3>
    <table>
      <thead>
        <tr>
          <th>Date</th>
          <th>Commit</th>
          <th>Description</th>
        </tr>
      </thead>
      <tbody>
        ${timelineRows || '<tr><td colspan="3">No snapshots yet.</td></tr>'}
      </tbody>
    </table>
  </div>

  <div class="card">
    <h3>Monitoring History</h3>
    <p>Status: <strong>${monitor.status}</strong> | Health Trend: <strong>${monitor.health_trend || 'N/A'}</strong></p>
    <ul>
      ${monitorRows || '<li>No monitoring runs recorded.</li>'}
    </ul>
  </div>

  <script nonce="${nonce}">
    const vscode = acquireVsCodeApi();
  </script>
</body>
</html>`;
  }
}

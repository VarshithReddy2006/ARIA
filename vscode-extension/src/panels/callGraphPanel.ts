/**
 * Interactive Call Graph panel.
 *
 * Renders function-level call relationships from
 * GET /api/call-graph/{owner}/{repo}
 *
 * Reuses the same canvas-based graph renderer as DependencyGraphPanel.
 * Supports search, node selection showing callers/callees, and blast radius.
 */

import * as vscode from 'vscode';
import { RepoIntelligenceClient, GraphData, extractErrorMessage } from '../api';
import { getNonce, BASE_CSS } from '../utils/webview';

export class CallGraphPanel {
  static readonly viewType = 'repoIntelligenceCallGraph';
  private static _panels = new Map<string, CallGraphPanel>();

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
    const existing = CallGraphPanel._panels.get(key);
    if (existing) {
      existing._panel.reveal(vscode.ViewColumn.One);
      return;
    }

    const panel = vscode.window.createWebviewPanel(
      CallGraphPanel.viewType,
      `Call Graph — ${key}`,
      vscode.ViewColumn.One,
      {
        enableScripts: true,
        retainContextWhenHidden: true,
        localResourceRoots: [vscode.Uri.joinPath(extensionUri, 'out')],
      }
    );

    const instance = new CallGraphPanel(panel, owner, repo, client);
    CallGraphPanel._panels.set(key, instance);
    panel.onDidDispose(() => CallGraphPanel._panels.delete(key));
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

    this._panel.webview.html = this._buildHtml();
    this._panel.webview.onDidReceiveMessage(this._handleMessage.bind(this));
    void this._loadGraph();
  }

  private async _loadGraph(query?: string): Promise<void> {
    try {
      const graph = await this._client.getCallGraph(this._owner, this._repo, query);
      void this._panel.webview.postMessage({ type: 'graphData', data: graph });
    } catch (err) {
      void this._panel.webview.postMessage({
        type: 'error',
        message: extractErrorMessage(err),
      });
    }
  }

  private async _handleMessage(msg: {
    type: string;
    nodeId?: string;
    query?: string;
    risk?: string;
    affected?: string[];
  }): Promise<void> {
    if (msg.type === 'search') {
      await this._loadGraph(msg.query);
    } else if (msg.type === 'resetGraph') {
      await this._loadGraph();
    } else if (msg.type === 'focusNode' && msg.nodeId) {
      try {
        const neighbors = await this._client.fetchJson<GraphData>(
          `/api/call-graph/${this._owner}/${this._repo}/neighbors/${encodeURIComponent(msg.nodeId)}`
        );
        void this._panel.webview.postMessage({ type: 'graphData', data: neighbors });
      } catch (err) {
        void this._panel.webview.postMessage({
          type: 'error',
          message: extractErrorMessage(err),
        });
      }
    } else if (msg.type === 'blastRadius' && msg.nodeId) {
      try {
        const result = await this._client.getBlastRadius(
          this._owner,
          this._repo,
          msg.nodeId
        );
        void this._panel.webview.postMessage({ type: 'blastRadius', data: result });
      } catch (err) {
        void this._panel.webview.postMessage({
          type: 'error',
          message: extractErrorMessage(err),
        });
      }
    } else if (msg.type === 'showNotification') {
      const risk = msg.risk ?? 'N/A';
      const affected = msg.affected || [];
      void vscode.window.showInformationMessage(
        `Blast Radius Risk: ${risk} — Affected functions: ${affected.join(', ')}`
      );
    }
  }

  private _buildHtml(): string {
    const nonce = getNonce();
    const csp = `default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-${nonce}';`;
    const repoId = `${this._owner}/${this._repo}`;

    return /* html */ `<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="${csp}">
<title>Call Graph — ${repoId}</title>
<style>
${BASE_CSS}
body { display: flex; flex-direction: column; height: 100vh; overflow: hidden; }
#toolbar {
  padding: 6px 12px;
  border-bottom: 1px solid var(--border);
  display: flex;
  gap: 8px;
  align-items: center;
  flex-shrink: 0;
  flex-wrap: wrap;
}
#toolbar h2 { font-size: 13px; font-weight: 600; flex: 1; }
#search {
  background: var(--input-bg);
  color: var(--input-fg);
  border: 1px solid var(--input-border);
  border-radius: 4px;
  padding: 4px 8px;
  font-size: 12px;
  width: 200px;
}
#graph-container { flex: 1; position: relative; overflow: hidden; cursor: grab; }
#graph-container:active { cursor: grabbing; }
#canvas { position: absolute; top: 0; left: 0; }
#tooltip {
  position: fixed;
  background: var(--vscode-editorWidget-background);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 6px 10px;
  font-size: 11px;
  pointer-events: none;
  display: none;
  max-width: 320px;
  z-index: 1000;
}
#side-panel {
  position: absolute;
  top: 8px; right: 8px;
  background: var(--vscode-editorWidget-background);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 10px 12px;
  font-size: 12px;
  max-width: 250px;
  display: none;
  z-index: 5;
  max-height: 60vh;
  overflow-y: auto;
}
#side-panel h3 { font-size: 12px; font-weight: 700; margin-bottom: 6px; }
#side-panel .fn-item { padding: 2px 0; color: var(--muted); cursor: pointer; }
#side-panel .fn-item:hover { color: var(--fg); }
#info-bar {
  padding: 4px 12px;
  border-top: 1px solid var(--border);
  font-size: 11px;
  color: var(--muted);
  flex-shrink: 0;
}
.spinner {
  width: 28px; height: 28px;
  border: 3px solid var(--border);
  border-top-color: var(--link);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
#loading-overlay {
  position: absolute; inset: 0;
  display: flex; align-items: center; justify-content: center;
  background: var(--bg); z-index: 10;
}
</style>
</head>
<body>
<div id="toolbar">
  <h2>📞 Call Graph — ${repoId}</h2>
  <input id="search" type="text" placeholder="Search functions…">
  <button onclick="resetGraph()">Reset</button>
  <button onclick="zoomIn()">+</button>
  <button onclick="zoomOut()">−</button>
  <button onclick="fitView()">Fit</button>
</div>
<div id="graph-container">
  <div id="loading-overlay"><div class="spinner"></div></div>
  <canvas id="canvas"></canvas>
  <div id="side-panel">
    <h3 id="side-title">Node Details</h3>
    <div id="side-content"></div>
  </div>
</div>
<div id="tooltip"></div>
<div id="info-bar">Loading call graph…</div>

<script nonce="${nonce}">
const vscode = acquireVsCodeApi();
let nodes = [], edges = [];
let scale = 1, offsetX = 0, offsetY = 0;
let dragging = false, lastMouse = { x: 0, y: 0 };
let hoveredNode = null, selectedNode = null;
const NODE_R = 16;

const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d');
const container = document.getElementById('graph-container');
const tooltip = document.getElementById('tooltip');
const infoBar = document.getElementById('info-bar');
const sidePanel = document.getElementById('side-panel');
const sideTitle = document.getElementById('side-title');
const sideContent = document.getElementById('side-content');
const loadingOverlay = document.getElementById('loading-overlay');

new ResizeObserver(() => {
  const r = container.getBoundingClientRect();
  canvas.width = r.width; canvas.height = r.height; draw();
}).observe(container);

function layoutNodes(raw) {
  const cols = Math.ceil(Math.sqrt(raw.length));
  return raw.map((n, i) => {
    if (n.position && typeof n.position.x === 'number') {
      return { ...n, x: n.position.x, y: n.position.y };
    }
    return { ...n, x: 80 + (i % cols) * 140, y: 60 + Math.floor(i / cols) * 90 };
  });
}

function draw() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.save();
  ctx.translate(offsetX, offsetY);
  ctx.scale(scale, scale);

  const fgColor = getComputedStyle(document.documentElement).getPropertyValue('--fg').trim() || '#ccc';
  const borderColor = getComputedStyle(document.documentElement).getPropertyValue('--border').trim() || '#444';
  const linkColor = getComputedStyle(document.documentElement).getPropertyValue('--link').trim() || '#4fc3f7';

  // Edges
  for (const e of edges) {
    const src = nodes.find(n => n.id === e.source);
    const tgt = nodes.find(n => n.id === e.target);
    if (!src || !tgt) continue;
    ctx.strokeStyle = borderColor;
    ctx.lineWidth = 1 / scale;
    ctx.beginPath();
    ctx.moveTo(src.x, src.y);
    ctx.lineTo(tgt.x, tgt.y);
    ctx.stroke();
  }

  // Nodes
  for (const n of nodes) {
    const isSelected = selectedNode && selectedNode.id === n.id;
    const isHovered = hoveredNode && hoveredNode.id === n.id;
    const isEntry = n.data && n.data.is_entry;

    ctx.beginPath();
    ctx.arc(n.x, n.y, NODE_R, 0, Math.PI * 2);
    ctx.fillStyle = isSelected ? linkColor : isEntry ? '#2e7d32' : isHovered ? '#555' : '#333';
    ctx.fill();
    ctx.strokeStyle = isSelected ? linkColor : borderColor;
    ctx.lineWidth = isSelected ? 2 / scale : 1 / scale;
    ctx.stroke();

    ctx.fillStyle = fgColor;
    ctx.font = (9 / scale) + 'px var(--vscode-font-family, monospace)';
    ctx.textAlign = 'center';
    const label = (n.data && n.data.label) ? String(n.data.label).slice(0, 16) : n.id.slice(0, 16);
    ctx.fillText(label, n.x, n.y + NODE_R + 11 / scale);
  }

  ctx.restore();
}

canvas.addEventListener('mousedown', e => { dragging = true; lastMouse = { x: e.clientX, y: e.clientY }; });
canvas.addEventListener('mousemove', e => {
  if (dragging) {
    offsetX += e.clientX - lastMouse.x; offsetY += e.clientY - lastMouse.y;
    lastMouse = { x: e.clientX, y: e.clientY }; draw(); return;
  }
  const [wx, wy] = screenToWorld(e.clientX, e.clientY);
  const node = hitTest(wx, wy);
  if (node !== hoveredNode) { hoveredNode = node; draw(); }
  if (node) {
    const label = node.data && node.data.label ? node.data.label : node.id;
    const fanIn = node.data && node.data.fan_in !== undefined ? '  fan-in: ' + node.data.fan_in : '';
    const fanOut = node.data && node.data.fan_out !== undefined ? '  fan-out: ' + node.data.fan_out : '';
    tooltip.textContent = label + fanIn + fanOut;
    tooltip.style.display = 'block';
    tooltip.style.left = (e.clientX + 12) + 'px';
    tooltip.style.top = (e.clientY - 8) + 'px';
  } else { tooltip.style.display = 'none'; }
});
canvas.addEventListener('mouseup', e => {
  dragging = false;
  const [wx, wy] = screenToWorld(e.clientX, e.clientY);
  const node = hitTest(wx, wy);
  if (node) {
    selectedNode = node;
    draw();
    showSidePanel(node);
    vscode.postMessage({ type: 'focusNode', nodeId: node.id });
  }
});
canvas.addEventListener('mouseleave', () => { dragging = false; hoveredNode = null; tooltip.style.display = 'none'; draw(); });
canvas.addEventListener('wheel', e => {
  e.preventDefault();
  const factor = e.deltaY < 0 ? 1.1 : 0.9;
  const [wx, wy] = screenToWorld(e.clientX, e.clientY);
  scale = Math.max(0.05, Math.min(scale * factor, 5));
  offsetX = e.clientX - wx * scale; offsetY = e.clientY - wy * scale;
  draw();
}, { passive: false });

function screenToWorld(sx, sy) {
  const rect = canvas.getBoundingClientRect();
  return [(sx - rect.left - offsetX) / scale, (sy - rect.top - offsetY) / scale];
}
function hitTest(wx, wy) {
  for (let i = nodes.length - 1; i >= 0; i--) {
    const n = nodes[i];
    const dx = wx - n.x, dy = wy - n.y;
    if (dx*dx + dy*dy <= NODE_R*NODE_R*1.5) return n;
  }
  return null;
}
function zoomIn()  { scale = Math.min(scale * 1.2, 5); draw(); }
function zoomOut() { scale = Math.max(scale * 0.8, 0.05); draw(); }
function fitView() {
  if (!nodes.length) return;
  const xs = nodes.map(n => n.x), ys = nodes.map(n => n.y);
  const minX = Math.min(...xs) - 40, maxX = Math.max(...xs) + 40;
  const minY = Math.min(...ys) - 40, maxY = Math.max(...ys) + 40;
  scale = Math.min(canvas.width / (maxX - minX), canvas.height / (maxY - minY), 2) * 0.9;
  offsetX = (canvas.width - (maxX + minX) * scale) / 2;
  offsetY = (canvas.height - (maxY + minY) * scale) / 2;
  draw();
}
function resetGraph() { selectedNode = null; sidePanel.style.display = 'none'; vscode.postMessage({ type: 'resetGraph' }); }

function showSidePanel(node) {
  const d = node.data || {};
  sideTitle.textContent = d.label || node.id;
  let html = '';
  if (d.file_path) html += '<div class="fn-item">📄 ' + d.file_path + '</div>';
  if (d.line_number) html += '<div class="fn-item">Line: ' + d.line_number + '</div>';
  if (d.fan_in !== undefined) html += '<div class="fn-item">Callers: ' + d.fan_in + '</div>';
  if (d.fan_out !== undefined) html += '<div class="fn-item">Callees: ' + d.fan_out + '</div>';
  if (d.is_entry) html += '<div class="fn-item">⭐ Entry function</div>';
  if (d.is_recursive) html += '<div class="fn-item">🔄 Recursive</div>';
  html += '<div style="margin-top:8px;"><button onclick="getBlastRadius()">Blast Radius</button></div>';
  sideContent.innerHTML = html;
  sidePanel.style.display = 'block';
}

function getBlastRadius() {
  if (selectedNode) vscode.postMessage({ type: 'blastRadius', nodeId: selectedNode.id });
}

let searchTimer;
document.getElementById('search').addEventListener('input', e => {
  clearTimeout(searchTimer);
  const q = e.target.value.trim();
  searchTimer = setTimeout(() => vscode.postMessage({ type: 'search', query: q }), 400);
});

window.addEventListener('message', e => {
  const msg = e.data;
  if (msg.type === 'graphData') {
    loadingOverlay.style.display = 'none';
    const raw = msg.data;
    nodes = layoutNodes(raw.nodes || []);
    edges = raw.edges || [];
    selectedNode = null;
    sidePanel.style.display = 'none';
    infoBar.textContent = nodes.length + ' functions, ' + edges.length + ' call edges';
    fitView(); draw();
  } else if (msg.type === 'blastRadius') {
    const r = msg.data;
    vscode.postMessage({ type: 'showNotification', risk: r.risk_level, affected: r.affected_functions });
  } else if (msg.type === 'error') {
    loadingOverlay.style.display = 'none';
    infoBar.textContent = '⚠ ' + msg.message;
  }
});
</script>
</body></html>`;
  }
}

/**
 * Repository Chat — embedded webview panel.
 *
 * Streams responses from POST /api/chat using the same SSE pipeline as the
 * frontend. No AI logic is implemented here — this is a pure client.
 */

import * as vscode from 'vscode';
import { RepoIntelligenceClient, extractErrorMessage } from '../api';
import { getNonce } from '../utils/webview';

export class ChatProvider {
  private static _panels = new Map<string, ChatProvider>();

  private readonly _panel: vscode.WebviewPanel;
  private readonly _repo: string;
  private readonly _client: RepoIntelligenceClient;
  private readonly _history: Array<{ role: string; content: string }> = [];
  private _cancelStream?: () => void;

  static createOrShow(
    context: vscode.ExtensionContext,
    repo: string,
    client: RepoIntelligenceClient
  ): ChatProvider {
    const existing = ChatProvider._panels.get(repo);
    if (existing) {
      existing._panel.reveal(vscode.ViewColumn.Beside);
      return existing;
    }

    const panel = vscode.window.createWebviewPanel(
      'repoIntelligenceChat',
      `Chat — ${repo}`,
      vscode.ViewColumn.Beside,
      {
        enableScripts: true,
        retainContextWhenHidden: true,
        localResourceRoots: [
          vscode.Uri.joinPath(context.extensionUri, 'out'),
          vscode.Uri.joinPath(context.extensionUri, 'webview'),
        ],
      }
    );

    const provider = new ChatProvider(panel, repo, client);
    ChatProvider._panels.set(repo, provider);

    panel.onDidDispose(() => {
      ChatProvider._panels.delete(repo);
      provider._cancelStream?.();
    });

    return provider;
  }

  public triggerQuery(userText: string): void {
    void this._sendMessage(userText);
  }

  private constructor(
    panel: vscode.WebviewPanel,
    repo: string,
    client: RepoIntelligenceClient
  ) {
    this._panel = panel;
    this._repo = repo;
    this._client = client;

    this._panel.webview.html = this._buildHtml();
    this._panel.webview.onDidReceiveMessage(this._handleMessage.bind(this));
  }

  private async _handleMessage(message: { type: string; text?: string }): Promise<void> {
    if (message.type === 'sendMessage' && message.text) {
      await this._sendMessage(message.text);
    }
    if (message.type === 'clearHistory') {
      this._history.length = 0;
      void this._panel.webview.postMessage({ type: 'historyCleared' });
    }
  }

  private async _sendMessage(userText: string): Promise<void> {
    this._history.push({ role: 'user', content: userText });
    void this._panel.webview.postMessage({
      type: 'userMessage',
      text: userText,
    });
    void this._panel.webview.postMessage({ type: 'streamStart' });

    let accumulated = '';

    this._cancelStream?.();
    this._cancelStream = this._client.streamChat(
      this._repo,
      userText,
      this._history,
      (token) => {
        accumulated += token;
        void this._panel.webview.postMessage({ type: 'streamToken', text: token });
      },
      (sources, confidence) => {
        this._history.push({ role: 'assistant', content: accumulated });
        void this._panel.webview.postMessage({
          type: 'streamDone',
          sources,
          confidence,
        });
        this._cancelStream = undefined;
      },
      (err) => {
        void this._panel.webview.postMessage({
          type: 'streamError',
          message: extractErrorMessage(err),
        });
        this._cancelStream = undefined;
      }
    );
  }

  private _buildHtml(): string {
    const nonce = getNonce();
    const csp = `default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-${nonce}';`;

    return /* html */ `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta http-equiv="Content-Security-Policy" content="${csp}">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Repo Chat</title>
  <style>
    :root {
      --bg: var(--vscode-editor-background);
      --fg: var(--vscode-editor-foreground);
      --input-bg: var(--vscode-input-background);
      --input-fg: var(--vscode-input-foreground);
      --input-border: var(--vscode-input-border);
      --btn-bg: var(--vscode-button-background);
      --btn-fg: var(--vscode-button-foreground);
      --user-bubble: var(--vscode-editorWidget-background);
      --assistant-bubble: var(--vscode-editor-selectionBackground);
      --border: var(--vscode-panel-border);
      --muted: var(--vscode-descriptionForeground);
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--bg);
      color: var(--fg);
      font-family: var(--vscode-font-family);
      font-size: var(--vscode-font-size);
      display: flex;
      flex-direction: column;
      height: 100vh;
      overflow: hidden;
    }
    #header {
      padding: 8px 12px;
      border-bottom: 1px solid var(--border);
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-shrink: 0;
    }
    #header h2 { font-size: 13px; font-weight: 600; }
    #clear-btn {
      background: none;
      border: 1px solid var(--input-border);
      color: var(--fg);
      padding: 2px 8px;
      border-radius: 3px;
      cursor: pointer;
      font-size: 11px;
    }
    #messages {
      flex: 1;
      overflow-y: auto;
      padding: 12px;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .message {
      max-width: 90%;
      padding: 8px 12px;
      border-radius: 6px;
      line-height: 1.5;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .message.user {
      align-self: flex-end;
      background: var(--user-bubble);
      border: 1px solid var(--border);
    }
    .message.assistant {
      align-self: flex-start;
      background: var(--assistant-bubble);
    }
    .message.streaming::after {
      content: '▌';
      animation: blink 1s infinite;
    }
    @keyframes blink { 50% { opacity: 0; } }
    .sources {
      margin-top: 6px;
      font-size: 11px;
      color: var(--muted);
    }
    .sources span { display: block; }
    .confidence {
      display: inline-block;
      margin-top: 4px;
      font-size: 10px;
      background: var(--vscode-badge-background);
      color: var(--vscode-badge-foreground);
      padding: 1px 6px;
      border-radius: 10px;
    }
    #input-area {
      border-top: 1px solid var(--border);
      padding: 10px 12px;
      display: flex;
      gap: 8px;
      flex-shrink: 0;
    }
    #user-input {
      flex: 1;
      background: var(--input-bg);
      color: var(--input-fg);
      border: 1px solid var(--input-border);
      border-radius: 4px;
      padding: 6px 10px;
      font-family: inherit;
      font-size: inherit;
      resize: none;
      min-height: 36px;
      max-height: 120px;
    }
    #user-input:focus { outline: 1px solid var(--vscode-focusBorder); }
    #send-btn {
      background: var(--btn-bg);
      color: var(--btn-fg);
      border: none;
      border-radius: 4px;
      padding: 6px 14px;
      cursor: pointer;
      font-size: 13px;
      flex-shrink: 0;
    }
    #send-btn:disabled { opacity: 0.5; cursor: not-allowed; }
    #empty-state {
      flex: 1;
      display: flex;
      align-items: center;
      justify-content: center;
      color: var(--muted);
      font-size: 13px;
      text-align: center;
      padding: 20px;
    }
  </style>
</head>
<body>
  <div id="header">
    <h2>💬 Repository Chat</h2>
    <button id="clear-btn">Clear</button>
  </div>
  <div id="messages">
    <div id="empty-state">Ask anything about the repository.<br>
      <small>Responses are grounded in the indexed code.</small>
    </div>
  </div>
  <div id="input-area">
    <textarea
      id="user-input"
      placeholder="Ask a question about the codebase…"
      rows="1"
    ></textarea>
    <button id="send-btn">Send</button>
  </div>

  <script nonce="${nonce}">
    const vscode = acquireVsCodeApi();
    const messagesEl = document.getElementById('messages');
    const inputEl = document.getElementById('user-input');
    const sendBtn = document.getElementById('send-btn');
    const clearBtn = document.getElementById('clear-btn');
    const emptyState = document.getElementById('empty-state');
    let streamingEl = null;

    function removeEmptyState() {
      if (emptyState && emptyState.parentNode) {
        emptyState.parentNode.removeChild(emptyState);
      }
    }

    function addMessage(role, text) {
      removeEmptyState();
      const div = document.createElement('div');
      div.className = 'message ' + role;
      div.textContent = text;
      messagesEl.appendChild(div);
      messagesEl.scrollTop = messagesEl.scrollHeight;
      return div;
    }

    sendBtn.addEventListener('click', send);
    inputEl.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        send();
      }
    });
    clearBtn.addEventListener('click', () => {
      vscode.postMessage({ type: 'clearHistory' });
    });

    function send() {
      const text = inputEl.value.trim();
      if (!text) return;
      inputEl.value = '';
      sendBtn.disabled = true;
      vscode.postMessage({ type: 'sendMessage', text });
    }

    window.addEventListener('message', (e) => {
      const msg = e.data;
      if (msg.type === 'userMessage') {
        addMessage('user', msg.text);
      } else if (msg.type === 'streamStart') {
        streamingEl = addMessage('assistant', '');
        streamingEl.classList.add('streaming');
      } else if (msg.type === 'streamToken' && streamingEl) {
        streamingEl.textContent += msg.text;
        messagesEl.scrollTop = messagesEl.scrollHeight;
      } else if (msg.type === 'streamDone' && streamingEl) {
        streamingEl.classList.remove('streaming');
        if (msg.sources && msg.sources.length > 0) {
          const src = document.createElement('div');
          src.className = 'sources';
          src.innerHTML = '<strong>Sources:</strong> ' +
            msg.sources.map(s => '<span>• ' + s + '</span>').join('');
          streamingEl.appendChild(src);
        }
        if (typeof msg.confidence === 'number') {
          const conf = document.createElement('span');
          conf.className = 'confidence';
          conf.textContent = 'Confidence: ' + msg.confidence + '%';
          streamingEl.appendChild(conf);
        }
        streamingEl = null;
        sendBtn.disabled = false;
      } else if (msg.type === 'streamError') {
        if (streamingEl) {
          streamingEl.classList.remove('streaming');
          streamingEl.textContent += '\\n\\n⚠ Error: ' + msg.message;
          streamingEl = null;
        }
        sendBtn.disabled = false;
      } else if (msg.type === 'historyCleared') {
        messagesEl.innerHTML = '';
        const empty = document.createElement('div');
        empty.id = 'empty-state';
        empty.innerHTML = 'Ask anything about the repository.<br><small>Responses are grounded in the indexed code.</small>';
        messagesEl.appendChild(empty);
      }
    });
  </script>
</body>
</html>`;
  }
}

import * as vscode from 'vscode';
import { WebviewHost } from './WebviewHost';

/**
 * DiagramPanel rendering Mermaid / PlantUML architecture & sequence diagrams.
 */
export class DiagramPanel {
  public static currentPanel: DiagramPanel | undefined;
  private readonly _panel: vscode.WebviewPanel;

  private constructor(panel: vscode.WebviewPanel, diagramText: string) {
    this._panel = panel;
    this._panel.webview.html = this.getHtmlForWebview(diagramText);
    this._panel.onDidDispose(() => this.dispose());
  }

  public static show(diagramText: string = ''): void {
    if (DiagramPanel.currentPanel) {
      DiagramPanel.currentPanel._panel.reveal(vscode.ViewColumn.Two);
      return;
    }

    const panel = WebviewHost.createPanel('repoIntelligenceDiagram', 'Architecture Diagram', vscode.ViewColumn.Two);
    DiagramPanel.currentPanel = new DiagramPanel(panel, diagramText);
  }

  public dispose(): void {
    DiagramPanel.currentPanel = undefined;
    this._panel.dispose();
  }

  private getHtmlForWebview(diagramText: string): string {
    return `<!DOCTYPE html>
<html>
<head>
  <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
  <style>body { font-family: sans-serif; background: #09090b; color: #f4f4f5; padding: 16px; }</style>
</head>
<body>
  <h2>Repository Component & Sequence Diagram</h2>
  <div class="mermaid">
${diagramText || `
sequenceDiagram
    autonumber
    actor Developer
    participant VSCode as VS Code Extension
    participant Backend as Copilot Backend
    participant Skills as Skill Framework
    Developer->>VSCode: Trigger /diagram
    VSCode->>Backend: POST /api/copilot/chat
    Backend->>Skills: Select DiagramSkill
    Skills-->>Backend: Mermaid Diagram Output
    Backend-->>VSCode: Rendered Response
    VSCode-->>Developer: Interactive Diagram Panel
`}
  </div>
  <script>mermaid.initialize({ startOnLoad: true, theme: 'dark' });</script>
</body>
</html>`;
  }
}

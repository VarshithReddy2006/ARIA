import * as vscode from 'vscode';
import { BackendClient } from './backendClient';
import { DiagramPanel } from '../panels/DiagramPanel';

/**
 * Command Dispatcher registering VS Code Extension commands.
 */
export class ExtensionCommands {
  constructor(
    private readonly context: vscode.ExtensionContext,
    private readonly backendClient: BackendClient
  ) {}

  public registerAll(): void {
    const register = (cmdId: string, handler: (...args: any[]) => any) => {
      this.context.subscriptions.push(vscode.commands.registerCommand(cmdId, handler));
    };

    // 1. Explain Current File
    register('repoIntelligence.explainCurrentFile', async () => {
      const editor = vscode.window.activeTextEditor;
      const file = editor ? editor.document.fileName : 'backend/api.py';
      const res = await this.backendClient.processCopilotChat('/explain', file, 'Explain Repository');
      vscode.window.showInformationMessage(`Explain Result: ${res.summary}`);
    });

    // 2. Trace Current Function
    register('repoIntelligence.traceCurrentFunction', async () => {
      const editor = vscode.window.activeTextEditor;
      const file = editor ? editor.document.fileName : 'backend/api.py';
      const res = await this.backendClient.processCopilotChat('/trace', file, 'Trace Execution Flow');
      vscode.window.showInformationMessage(`Trace Result: ${res.summary}`);
    });

    // 3. Review Current File
    register('repoIntelligence.reviewCurrentFile', async () => {
      const editor = vscode.window.activeTextEditor;
      const file = editor ? editor.document.fileName : 'backend/api.py';
      const res = await this.backendClient.processCopilotChat('/review', file, 'Engineering Review');
      vscode.window.showInformationMessage(`Review Result: ${res.summary}`);
    });

    // 4. Generate Documentation
    register('repoIntelligence.generateDocumentation', async () => {
      const editor = vscode.window.activeTextEditor;
      const file = editor ? editor.document.fileName : 'backend/api.py';
      const res = await this.backendClient.processCopilotChat('/document', file, 'Generate Documentation');
      vscode.window.showInformationMessage(`Documentation Generated for ${file}`);
    });

    // 5. Generate Diagram
    register('repoIntelligence.generateDiagram', async () => {
      const editor = vscode.window.activeTextEditor;
      const file = editor ? editor.document.fileName : 'backend/api.py';
      const res = await this.backendClient.processCopilotChat('/diagram', file, 'Generate Architecture Diagram');
      DiagramPanel.show(res.answer);
    });

    // 6. Architecture Overview
    register('repoIntelligence.architectureOverview', async () => {
      const res = await this.backendClient.processCopilotChat('/architecture', 'backend/api.py', 'Architecture Explanation');
      vscode.window.showInformationMessage(`Architecture Overview: ${res.summary}`);
    });

    // 7. Search Repository
    register('repoIntelligence.searchRepository', async () => {
      const query = await vscode.window.showInputBox({ prompt: 'Enter engineering search query' });
      if (query) {
        const res = await this.backendClient.processCopilotChat(`/search ${query}`, 'backend/api.py', 'Engineering Search');
        vscode.window.showInformationMessage(`Search Results: ${res.summary}`);
      }
    });

    // 8. Impact Analysis
    register('repoIntelligence.impactAnalysis', async () => {
      const editor = vscode.window.activeTextEditor;
      const file = editor ? editor.document.fileName : 'backend/api.py';
      const res = await this.backendClient.processCopilotChat('/impact', file, 'Change Impact Analysis');
      vscode.window.showInformationMessage(`Impact Analysis: ${res.summary}`);
    });

    // 9. Learning Journey
    register('repoIntelligence.learningJourney', async () => {
      const res = await this.backendClient.processCopilotChat('/learn', 'backend/api.py', 'Teach Repository Concepts');
      vscode.window.showInformationMessage(`Learning Pathway: ${res.summary}`);
    });

    // 10. Open Repository Graph & Call Graph
    register('repoIntelligence.openRepositoryGraph', () => {
      vscode.window.showInformationMessage('Opening Repository Graph Webview');
    });

    register('repoIntelligence.openCallGraph', () => {
      vscode.window.showInformationMessage('Opening Call Graph Webview');
    });
  }
}

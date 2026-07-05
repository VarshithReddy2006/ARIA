import * as vscode from 'vscode';
import { client, extractErrorMessage } from '../api';
import { StateService } from '../utils/stateService';

export class RepoIntelGraphProvider {
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

  public static async findCallers(uri?: vscode.Uri): Promise<void> {
    const fileUri = uri || vscode.window.activeTextEditor?.document.uri;
    if (!fileUri) { return; }
    const relPath = vscode.workspace.asRelativePath(fileUri, false);
    const context = await this.getRepoContext();
    if (!context) { return; }
    const [owner, repoName] = context;

    try {
      const result = await client.getFileSymbols(owner, repoName, relPath);
      const symbols = (result.symbols || []).filter(
        (s) => s.symbol_type === 'function' || s.symbol_type === 'method'
      );
      if (symbols.length === 0) {
        void vscode.window.showInformationMessage('No functions or methods found in this file.');
        return;
      }

      const picked = await vscode.window.showQuickPick(
        symbols.map((s) => ({ label: s.name, description: s.qualified, symbol: s })),
        { placeHolder: 'Select symbol to find callers' }
      );
      if (picked) {
        void vscode.commands.executeCommand('repoIntelligence.showCallers', {
          owner,
          repo: repoName,
          functionId: `${relPath}::${picked.symbol.qualified}`
        });
      }
    } catch (err) {
      void vscode.window.showErrorMessage(`Failed to find callers: ${extractErrorMessage(err)}`);
    }
  }

  public static async findCallees(uri?: vscode.Uri): Promise<void> {
    const fileUri = uri || vscode.window.activeTextEditor?.document.uri;
    if (!fileUri) { return; }
    const relPath = vscode.workspace.asRelativePath(fileUri, false);
    const context = await this.getRepoContext();
    if (!context) { return; }
    const [owner, repoName] = context;

    try {
      const result = await client.getFileSymbols(owner, repoName, relPath);
      const symbols = (result.symbols || []).filter(
        (s) => s.symbol_type === 'function' || s.symbol_type === 'method'
      );
      if (symbols.length === 0) {
        void vscode.window.showInformationMessage('No functions or methods found in this file.');
        return;
      }

      const picked = await vscode.window.showQuickPick(
        symbols.map((s) => ({ label: s.name, description: s.qualified, symbol: s })),
        { placeHolder: 'Select symbol to find callees' }
      );
      if (picked) {
        void vscode.commands.executeCommand('repoIntelligence.showCallees', {
          owner,
          repo: repoName,
          functionId: `${relPath}::${picked.symbol.qualified}`
        });
      }
    } catch (err) {
      void vscode.window.showErrorMessage(`Failed to find callees: ${extractErrorMessage(err)}`);
    }
  }

  public static async showBlastRadius(uri?: vscode.Uri): Promise<void> {
    const fileUri = uri || vscode.window.activeTextEditor?.document.uri;
    if (!fileUri) { return; }
    const relPath = vscode.workspace.asRelativePath(fileUri, false);
    const context = await this.getRepoContext();
    if (!context) { return; }
    const [owner, repoName] = context;

    try {
      const result = await client.getFileSymbols(owner, repoName, relPath);
      const symbols = (result.symbols || []).filter(
        (s) => s.symbol_type === 'function' || s.symbol_type === 'method'
      );
      if (symbols.length === 0) {
        void vscode.window.showInformationMessage('No functions or methods found in this file.');
        return;
      }

      const picked = await vscode.window.showQuickPick(
        symbols.map((s) => ({ label: s.name, description: s.qualified, symbol: s })),
        { placeHolder: 'Select symbol to analyze blast radius' }
      );
      if (picked) {
        void vscode.commands.executeCommand('repoIntelligence.showBlastRadius', {
          owner,
          repo: repoName,
          functionId: `${relPath}::${picked.symbol.qualified}`
        });
      }
    } catch (err) {
      void vscode.window.showErrorMessage(`Failed to show blast radius: ${extractErrorMessage(err)}`);
    }
  }

  public static async showDependencyChain(): Promise<void> {
    const context = await this.getRepoContext();
    if (!context) { return; }
    const [owner, repoName] = context;

    try {
      const graph = await client.getDependencyGraph(owner, repoName);
      const nodes = graph.nodes || [];
      if (nodes.length === 0) {
        void vscode.window.showInformationMessage('No dependency nodes found in the graph.');
        return;
      }

      const picked = await vscode.window.showQuickPick(
        nodes.map((n: any) => ({ label: n.label, description: n.id })),
        { placeHolder: 'Select file node to inspect dependencies' }
      );

      if (picked) {
        const fileNode = picked.description;
        // Find all outgoing edges from this node
        const edges = (graph.edges || []).filter((e: any) => e.from === fileNode);
        if (edges.length === 0) {
          void vscode.window.showInformationMessage(`${picked.label} has no dependencies.`);
          return;
        }

        const targetFiles = edges.map((e: any) => e.to);
        const nextPick = await vscode.window.showQuickPick(
          targetFiles.map((f: string) => ({ label: f })),
          { placeHolder: `Dependencies of ${picked.label} (Select to open)` }
        );

        if (nextPick) {
          const workspaceFolders = vscode.workspace.workspaceFolders;
          if (workspaceFolders) {
            const targetUri = vscode.Uri.joinPath(workspaceFolders[0].uri, nextPick.label);
            const doc = await vscode.workspace.openTextDocument(targetUri);
            await vscode.window.showTextDocument(doc);
          }
        }
      }
    } catch (err) {
      void vscode.window.showErrorMessage(`Failed to fetch dependency chain: ${extractErrorMessage(err)}`);
    }
  }
}

import * as vscode from 'vscode';

/**
 * Webview Host helper utility for creating standalone webview panels.
 */
export class WebviewHost {
  public static createPanel(
    viewType: string,
    title: string,
    showOptions: vscode.ViewColumn = vscode.ViewColumn.One
  ): vscode.WebviewPanel {
    return vscode.window.createWebviewPanel(
      viewType,
      title,
      showOptions,
      {
        enableScripts: true,
        retainContextWhenHidden: true
      }
    );
  }
}

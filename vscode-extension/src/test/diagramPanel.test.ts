import * as assert from 'assert';
import * as vscode from 'vscode';
import { DiagramPanel } from '../panels/DiagramPanel';

describe('DiagramPanel', () => {
  it('replaces the displayed diagram when the command is run again', () => {
    const originalCreatePanel = vscode.window.createWebviewPanel;
    const mockedWindow = vscode.window as unknown as {
      createWebviewPanel: typeof vscode.window.createWebviewPanel;
    };
    let disposeHandler: (() => void) | undefined;
    const panel = {
      webview: { html: '' },
      reveal: () => {},
      onDidDispose: (handler: () => void) => {
        disposeHandler = handler;
        return { dispose: () => {} };
      },
      dispose: () => disposeHandler?.(),
    };
    mockedWindow.createWebviewPanel = () => panel as unknown as vscode.WebviewPanel;

    try {
      DiagramPanel.show('sequenceDiagram\n  A->>B: first result');
      assert.ok(panel.webview.html.includes('first result'));

      DiagramPanel.show('sequenceDiagram\n  A->>B: updated result');
      assert.ok(panel.webview.html.includes('updated result'));
      assert.ok(!panel.webview.html.includes('first result'));
    } finally {
      DiagramPanel.currentPanel = undefined;
      mockedWindow.createWebviewPanel = originalCreatePanel;
    }
  });
});

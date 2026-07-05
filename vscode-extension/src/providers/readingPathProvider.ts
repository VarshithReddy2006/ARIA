import * as vscode from 'vscode';
import { StateService } from '../utils/stateService';
import { client } from '../api';
import { WorkspaceEventBus } from '../services/workspaceEventBus';

export class ReadingPathProvider {
  private static steps: string[] = [];
  private static currentIndex = -1;
  private static statusBarItem: vscode.StatusBarItem;
  private static disposables: vscode.Disposable[] = [];

  public static initialize(context: vscode.ExtensionContext): void {
    this.statusBarItem = vscode.window.createStatusBarItem(
      vscode.StatusBarAlignment.Right,
      200
    );
    this.statusBarItem.command = 'repoIntelligence.openWorkspace';
    this.disposables.push(this.statusBarItem);

    // Register navigation commands
    this.disposables.push(
      vscode.commands.registerCommand('repoIntelligence.nextReadingStep', () => this.nextStep()),
      vscode.commands.registerCommand('repoIntelligence.previousReadingStep', () => this.previousStep())
    );

    // Sync when active editor changes
    this.disposables.push(
      vscode.window.onDidChangeActiveTextEditor((editor) => {
        if (editor) {
          this.syncWithEditor(editor.document);
        }
      })
    );

    // Subscribe to Event Bus to reload reading paths
    this.disposables.push(
      WorkspaceEventBus.onEvent((e) => {
        if (e.type === 'RepositoryChanged' || e.type === 'WorkspaceReloaded') {
          void this.loadReadingPath();
        }
      })
    );

    context.subscriptions.push({
      dispose: () => this.dispose(),
    });

    void this.loadReadingPath();
  }

  public static async loadReadingPath(): Promise<void> {
    const repo = StateService.getActiveRepository();
    if (!repo) {
      this.steps = [];
      this.currentIndex = -1;
      this.updateStatus();
      return;
    }

    try {
      const order = await client.getReadingOrder(repo);
      this.steps = (order.entries || []).map((e) => e.file);
      this.currentIndex = -1;

      const editor = vscode.window.activeTextEditor;
      if (editor) {
        this.syncWithEditor(editor.document);
      } else {
        this.updateStatus();
      }
    } catch {
      this.steps = [];
      this.currentIndex = -1;
      this.updateStatus();
    }
  }

  private static syncWithEditor(document: vscode.TextDocument): void {
    const relPath = vscode.workspace.asRelativePath(document.uri, false);
    const idx = this.steps.indexOf(relPath);
    if (idx !== -1) {
      this.currentIndex = idx;
    }
    this.updateStatus();
  }

  private static updateStatus(): void {
    if (this.steps.length === 0) {
      this.statusBarItem.hide();
      return;
    }

    if (this.currentIndex === -1) {
      this.statusBarItem.text = `$(book) Reading Path (${this.steps.length} files)`;
      this.statusBarItem.tooltip = 'Click to open active repository workspace dashboard';
      this.statusBarItem.show();
      return;
    }

    const percentage = Math.round(((this.currentIndex + 1) / this.steps.length) * 100);
    this.statusBarItem.text = `$(book) Reading Step ${this.currentIndex + 1}/${this.steps.length} (${percentage}%)`;
    this.statusBarItem.tooltip = [
      `Current File: ${this.steps[this.currentIndex]}`,
      `Progress: ${percentage}%`,
      'Commands:',
      ' - Next Reading Step',
      ' - Previous Reading Step',
    ].join('\n');
    this.statusBarItem.show();
  }

  public static async nextStep(): Promise<void> {
    if (this.steps.length === 0) {
      await this.loadReadingPath();
    }
    if (this.steps.length === 0) { return; }

    this.currentIndex = Math.min(this.steps.length - 1, this.currentIndex + 1);
    await this.openCurrentStep();
  }

  public static async previousStep(): Promise<void> {
    if (this.steps.length === 0) {
      await this.loadReadingPath();
    }
    if (this.steps.length === 0) { return; }

    this.currentIndex = Math.max(0, this.currentIndex - 1);
    await this.openCurrentStep();
  }

  private static async openCurrentStep(): Promise<void> {
    if (this.currentIndex < 0 || this.currentIndex >= this.steps.length) { return; }
    const relPath = this.steps[this.currentIndex];

    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (!workspaceFolders) { return; }
    const uri = vscode.Uri.joinPath(workspaceFolders[0].uri, relPath);

    try {
      const doc = await vscode.workspace.openTextDocument(uri);
      await vscode.window.showTextDocument(doc);
      this.updateStatus();
    } catch {
      void vscode.window.showErrorMessage(`Failed to open reading path file: ${relPath}`);
    }
  }

  public static dispose(): void {
    for (const d of this.disposables) {
      d.dispose();
    }
    this.disposables = [];
  }
}

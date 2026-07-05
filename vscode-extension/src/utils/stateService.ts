import * as vscode from 'vscode';

export class StateService {
  private static workspaceState: vscode.Memento;

  public static initialize(context: vscode.ExtensionContext): void {
    this.workspaceState = context.workspaceState;
    this.migrateLegacySettings();
  }

  public static getActiveRepository(): string {
    if (!this.workspaceState) {
      try {
        return vscode.workspace.getConfiguration('repoIntelligence').get<string>('activeRepository') ?? '';
      } catch {
        return '';
      }
    }
    return this.workspaceState.get<string>('activeRepository') ?? '';
  }

  public static async setActiveRepository(repo: string): Promise<void> {
    if (!this.workspaceState) {
      try {
        const cfg = vscode.workspace.getConfiguration('repoIntelligence');
        await cfg.update('activeRepository', repo, vscode.ConfigurationTarget.Workspace);
      } catch {
        // ignore
      }
      return;
    }
    await this.workspaceState.update('activeRepository', repo);
  }

  public static getSelectedPanel(): string {
    if (!this.workspaceState) {
      try {
        return vscode.workspace.getConfiguration('repoIntelligence').get<string>('selectedPanel') ?? '';
      } catch {
        return '';
      }
    }
    return this.workspaceState.get<string>('selectedPanel') ?? '';
  }

  public static async setSelectedPanel(panel: string): Promise<void> {
    if (!this.workspaceState) {
      try {
        const cfg = vscode.workspace.getConfiguration('repoIntelligence');
        await cfg.update('selectedPanel', panel, vscode.ConfigurationTarget.Workspace);
      } catch {
        // ignore
      }
      return;
    }
    await this.workspaceState.update('selectedPanel', panel);
  }

  public static getLastViewedReport(): string {
    if (!this.workspaceState) {
      try {
        return vscode.workspace.getConfiguration('repoIntelligence').get<string>('lastViewedReport') ?? '';
      } catch {
        return '';
      }
    }
    return this.workspaceState.get<string>('lastViewedReport') ?? '';
  }

  public static async setLastViewedReport(report: string): Promise<void> {
    if (!this.workspaceState) {
      try {
        const cfg = vscode.workspace.getConfiguration('repoIntelligence');
        await cfg.update('lastViewedReport', report, vscode.ConfigurationTarget.Workspace);
      } catch {
        // ignore
      }
      return;
    }
    await this.workspaceState.update('lastViewedReport', report);
  }

  private static migrateLegacySettings(): void {
    const cfg = vscode.workspace.getConfiguration('repoIntelligence');

    // Migrate activeRepository
    const legacyRepo = cfg.get<string>('activeRepository');
    if (legacyRepo) {
      void this.setActiveRepository(legacyRepo);
      void cfg.update('activeRepository', undefined, vscode.ConfigurationTarget.Global);
      void cfg.update('activeRepository', undefined, vscode.ConfigurationTarget.Workspace);
    }

    // Migrate selectedPanel
    const legacyPanel = cfg.get<string>('selectedPanel');
    if (legacyPanel) {
      void this.setSelectedPanel(legacyPanel);
      void cfg.update('selectedPanel', undefined, vscode.ConfigurationTarget.Global);
      void cfg.update('selectedPanel', undefined, vscode.ConfigurationTarget.Workspace);
    }

    // Migrate lastViewedReport
    const legacyReport = cfg.get<string>('lastViewedReport');
    if (legacyReport) {
      void this.setLastViewedReport(legacyReport);
      void cfg.update('lastViewedReport', undefined, vscode.ConfigurationTarget.Global);
      void cfg.update('lastViewedReport', undefined, vscode.ConfigurationTarget.Workspace);
    }
  }
}

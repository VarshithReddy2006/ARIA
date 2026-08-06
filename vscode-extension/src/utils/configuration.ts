import * as vscode from 'vscode';

/**
 * Configuration Utility managing VS Code extension settings.
 */
export class ConfigurationManager {
  public static get backendUrl(): string {
    return vscode.workspace.getConfiguration('repoIntelligence').get<string>('backendUrl', 'http://127.0.0.1:8001');
  }

  public static get apiToken(): string {
    return vscode.workspace.getConfiguration('repoIntelligence').get<string>('apiToken', '');
  }

  public static get theme(): string {
    return vscode.workspace.getConfiguration('repoIntelligence').get<string>('theme', 'auto');
  }

  public static get streaming(): boolean {
    return vscode.workspace.getConfiguration('repoIntelligence').get<boolean>('streaming', true);
  }

  public static get autoSync(): boolean {
    return vscode.workspace.getConfiguration('repoIntelligence').get<boolean>('autoSync', true);
  }

  public static get evidenceDisplay(): boolean {
    return vscode.workspace.getConfiguration('repoIntelligence').get<boolean>('evidenceDisplay', true);
  }

  public static get learningMode(): boolean {
    return vscode.workspace.getConfiguration('repoIntelligence').get<boolean>('learningMode', true);
  }

  public static get telemetry(): boolean {
    return vscode.workspace.getConfiguration('repoIntelligence').get<boolean>('telemetry', true);
  }

  public static get codeLensEnabled(): boolean {
    return vscode.workspace.getConfiguration('repoIntelligence').get<boolean>('codeLens.enabled', true);
  }

  public static get hoverEnabled(): boolean {
    return vscode.workspace.getConfiguration('repoIntelligence').get<boolean>('hover.enabled', true);
  }
}

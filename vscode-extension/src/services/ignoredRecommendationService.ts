import * as vscode from 'vscode';

/**
 * Service to manage ignored recommendations.
 * 
 * Strategy:
 * - Recommendations are ignored at the repository scope and persisted in `workspaceState`.
 * - The storage key format is `ignoredRecommendations/{owner}/{repo}`.
 * - To ensure ignores survive reloads and refreshes but reset on new analysis:
 *   - We store the last analysis timestamp (`last_indexed_at` from overview) under `analysisIdentifier/{owner}/{repo}`.
 *   - When a new analysis completes (`InspectionFinished` event), we fetch the repository overview.
 *   - If the new analysis timestamp differs from the stored one, the ignores for that repository are cleared.
 */
export class IgnoredRecommendationService {
  private static workspaceState: vscode.Memento;

  public static initialize(context: vscode.ExtensionContext): void {
    this.workspaceState = context.workspaceState;
  }

  private static getKey(owner: string, repo: string): string {
    return `ignoredRecommendations/${owner}/${repo}`;
  }

  private static getAnalysisIdKey(owner: string, repo: string): string {
    return `analysisIdentifier/${owner}/${repo}`;
  }

  public static getIgnored(owner: string, repo: string): string[] {
    if (!this.workspaceState) {
      return [];
    }
    return this.workspaceState.get<string[]>(this.getKey(owner, repo), []);
  }

  public static async ignore(owner: string, repo: string, id: string): Promise<void> {
    if (!this.workspaceState) {
      return;
    }
    const current = this.getIgnored(owner, repo);
    if (!current.includes(id)) {
      current.push(id);
      await this.workspaceState.update(this.getKey(owner, repo), current);
    }
  }

  public static async clear(owner: string, repo: string): Promise<void> {
    if (!this.workspaceState) {
      return;
    }
    await this.workspaceState.update(this.getKey(owner, repo), undefined);
    await this.workspaceState.update(this.getAnalysisIdKey(owner, repo), undefined);
  }

  public static async checkAndClearIfAnalysisChanged(
    owner: string,
    repo: string,
    newAnalysisId: string
  ): Promise<void> {
    if (!this.workspaceState) {
      return;
    }
    const currentAnalysisId = this.workspaceState.get<string>(this.getAnalysisIdKey(owner, repo));
    if (currentAnalysisId && currentAnalysisId !== newAnalysisId) {
      // Analysis identifier changed! Clear ignored recommendations.
      await this.clear(owner, repo);
    }
    // Update the saved analysis identifier
    await this.workspaceState.update(this.getAnalysisIdKey(owner, repo), newAnalysisId);
  }
}

import * as vscode from 'vscode';

export class GitService {
  public static getAPI(): any {
    const extension = vscode.extensions.getExtension<any>('vscode.git');
    if (!extension) { return undefined; }
    return extension.exports.getAPI(1);
  }

  public static getCurrentBranch(): string | undefined {
    const git = this.getAPI();
    if (!git) { return undefined; }
    const repo = git.repositories[0];
    return repo?.state.HEAD?.name;
  }

  public static getChangedFiles(): string[] {
    const git = this.getAPI();
    if (!git) { return []; }
    const repo = git.repositories[0];
    if (!repo) { return []; }

    const changes: string[] = [];
    const indexChanges = repo.state.indexChanges || [];
    const workingTreeChanges = repo.state.workingTreeChanges || [];

    for (const change of [...indexChanges, ...workingTreeChanges]) {
      if (change.uri) {
        changes.push(vscode.workspace.asRelativePath(change.uri, false));
      }
    }
    return Array.from(new Set(changes));
  }

  public static getStagedFiles(): string[] {
    const git = this.getAPI();
    if (!git) { return []; }
    const repo = git.repositories[0];
    if (!repo) { return []; }

    const changes: string[] = [];
    const indexChanges = repo.state.indexChanges || [];

    for (const change of indexChanges) {
      if (change.uri) {
        changes.push(vscode.workspace.asRelativePath(change.uri, false));
      }
    }
    return Array.from(new Set(changes));
  }

  public static getRepositoryRoot(): string | undefined {
    const git = this.getAPI();
    if (!git) { return undefined; }
    const repo = git.repositories[0];
    return repo?.rootUri?.fsPath;
  }
}

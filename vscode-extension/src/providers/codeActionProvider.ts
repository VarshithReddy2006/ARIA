import * as vscode from 'vscode';

export class RepoIntelCodeActionProvider implements vscode.CodeActionProvider {
  provideCodeActions(
    document: vscode.TextDocument,
    range: vscode.Range | vscode.Selection,
    _context: vscode.CodeActionContext,
    _token: vscode.CancellationToken
  ): vscode.CodeAction[] {
    const actions: vscode.CodeAction[] = [];

    // ── Symbol Actions ─────────────────────────────────────────────────────
    const explainSymbolAction = new vscode.CodeAction('Explain Symbol (Repo Intel)', vscode.CodeActionKind.Refactor);
    explainSymbolAction.command = {
      command: 'repoIntelligence.explainSymbol',
      title: 'Explain Symbol',
      arguments: [document.uri, range],
    };
    actions.push(explainSymbolAction);

    const blastRadiusAction = new vscode.CodeAction('Analyze Blast Radius (Repo Intel)', vscode.CodeActionKind.Refactor);
    blastRadiusAction.command = {
      command: 'repoIntelligence.showBlastRadius',
      title: 'Analyze Blast Radius',
      arguments: [{ documentUri: document.uri, range }],
    };
    actions.push(blastRadiusAction);

    const findReferencesAction = new vscode.CodeAction('Find References in Repository Graph (Repo Intel)', vscode.CodeActionKind.Refactor);
    findReferencesAction.command = {
      command: 'repoIntelligence.findReferencesInGraph',
      title: 'Find References in Repository Graph',
      arguments: [document.uri, range],
    };
    actions.push(findReferencesAction);

    const showHierarchyAction = new vscode.CodeAction('Show Call Hierarchy (Repo Intel)', vscode.CodeActionKind.Refactor);
    showHierarchyAction.command = {
      command: 'repoIntelligence.showCallHierarchy',
      title: 'Show Call Hierarchy',
      arguments: [document.uri, range],
    };
    actions.push(showHierarchyAction);

    // ── File Actions ───────────────────────────────────────────────────────
    const explainFileAction = new vscode.CodeAction('Explain File (Repo Intel)', vscode.CodeActionKind.Refactor);
    explainFileAction.command = {
      command: 'repoIntelligence.explainFile',
      title: 'Explain File',
      arguments: [document.uri],
    };
    actions.push(explainFileAction);

    const askRepoAction = new vscode.CodeAction('Ask Repository (Repo Intel)', vscode.CodeActionKind.Refactor);
    askRepoAction.command = {
      command: 'repoIntelligence.askAboutFile',
      title: 'Ask Repository About This File',
      arguments: [document.uri],
    };
    actions.push(askRepoAction);

    const readingPathAction = new vscode.CodeAction('Generate Reading Path (Repo Intel)', vscode.CodeActionKind.Refactor);
    readingPathAction.command = {
      command: 'repoIntelligence.showReadingPathForFile',
      title: 'Generate Reading Path',
      arguments: [{ file: vscode.workspace.asRelativePath(document.uri, false) }],
    };
    actions.push(readingPathAction);

    // ── Module Actions ─────────────────────────────────────────────────────
    const inspectModuleAction = new vscode.CodeAction('Inspect Current Module (Repo Intel)', vscode.CodeActionKind.Refactor);
    inspectModuleAction.command = {
      command: 'repoIntelligence.inspectModule',
      title: 'Inspect Current Module',
      arguments: [document.uri],
    };
    actions.push(inspectModuleAction);

    const roadmapAction = new vscode.CodeAction('Generate Module Roadmap (Repo Intel)', vscode.CodeActionKind.Refactor);
    roadmapAction.command = {
      command: 'repoIntelligence.generateRoadmap',
      title: 'Generate Module Roadmap',
      arguments: [document.uri],
    };
    actions.push(roadmapAction);

    return actions;
  }
}

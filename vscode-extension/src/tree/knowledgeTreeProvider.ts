import * as vscode from 'vscode';
import { RepositoryTreeItem } from './repositoryTreeProvider';

/**
 * TreeDataProvider for Knowledge Graph & Concept Graph in Sidebar.
 */
export class KnowledgeTreeProvider implements vscode.TreeDataProvider<RepositoryTreeItem> {
  private _onDidChangeTreeData = new vscode.EventEmitter<RepositoryTreeItem | undefined | void>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  refresh(): void {
    this._onDidChangeTreeData.fire();
  }

  getTreeItem(element: RepositoryTreeItem): vscode.TreeItem {
    return element;
  }

  async getChildren(element?: RepositoryTreeItem): Promise<RepositoryTreeItem[]> {
    if (!element) {
      return [
        new RepositoryTreeItem('Repository Knowledge Graph', vscode.TreeItemCollapsibleState.Expanded, 'Active Graph', 'kg', 'graph'),
        new RepositoryTreeItem('Concept Graph', vscode.TreeItemCollapsibleState.Collapsed, '14 Concepts', 'concepts', 'lightbulb'),
        new RepositoryTreeItem('Pinned Entities', vscode.TreeItemCollapsibleState.Collapsed, '2 Pinned', 'pinned', 'pin')
      ];
    }

    if (element.label === 'Repository Knowledge Graph') {
      return [
        new RepositoryTreeItem('CopilotController (Node)', vscode.TreeItemCollapsibleState.None, 'Application Orchestrator', 'node', 'symbol-class'),
        new RepositoryTreeItem('SkillSelector (Node)', vscode.TreeItemCollapsibleState.None, 'Intent & Confidence Engine', 'node', 'symbol-method'),
        new RepositoryTreeItem('SkillRegistry (Node)', vscode.TreeItemCollapsibleState.None, 'Skill Registry Container', 'node', 'symbol-interface')
      ];
    }

    return [];
  }
}

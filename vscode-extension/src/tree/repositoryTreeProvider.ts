import * as vscode from 'vscode';

export class RepositoryTreeItem extends vscode.TreeItem {
  constructor(
    public readonly label: string,
    public readonly collapsibleState: vscode.TreeItemCollapsibleState,
    public readonly description?: string,
    public readonly contextValue?: string,
    public readonly iconName?: string
  ) {
    super(label, collapsibleState);
    this.description = description;
    this.contextValue = contextValue;
    if (iconName) {
      this.iconPath = new vscode.ThemeIcon(iconName);
    }
  }
}

/**
 * TreeDataProvider for Repository Explorer & Architecture Layers.
 */
export class RepositoryTreeProvider implements vscode.TreeDataProvider<RepositoryTreeItem> {
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
        new RepositoryTreeItem('Active Workspace', vscode.TreeItemCollapsibleState.Expanded, 'Repo Intelligence', 'workspace', 'repo'),
        new RepositoryTreeItem('Architecture Layers', vscode.TreeItemCollapsibleState.Collapsed, '9 Layers', 'architecture', 'layers'),
        new RepositoryTreeItem('Learning Journey', vscode.TreeItemCollapsibleState.Collapsed, 'Active Path', 'learning', 'book'),
        new RepositoryTreeItem('Bookmarks & Pinned Entities', vscode.TreeItemCollapsibleState.Collapsed, '3 Pinned', 'bookmarks', 'bookmark'),
        new RepositoryTreeItem('Recent Conversations', vscode.TreeItemCollapsibleState.Collapsed, '5 Turns', 'history', 'history')
      ];
    }

    if (element.label === 'Architecture Layers') {
      return [
        new RepositoryTreeItem('Presentation Layer', vscode.TreeItemCollapsibleState.None, 'HTTP API & Routers', 'layer', 'symbol-interface'),
        new RepositoryTreeItem('Application Layer', vscode.TreeItemCollapsibleState.None, 'Controllers & Handlers', 'layer', 'symbol-class'),
        new RepositoryTreeItem('Copilot Subsystem', vscode.TreeItemCollapsibleState.None, 'Skills & Reasoning', 'layer', 'cpu'),
        new RepositoryTreeItem('Domain Layer', vscode.TreeItemCollapsibleState.None, 'Entities & Rules', 'layer', 'shield')
      ];
    }

    if (element.label === 'Bookmarks & Pinned Entities') {
      return [
        new RepositoryTreeItem('backend/api.py', vscode.TreeItemCollapsibleState.None, 'Presentation Entry', 'entity', 'file-code'),
        new RepositoryTreeItem('backend/copilot/skills/skill_registry.py', vscode.TreeItemCollapsibleState.None, 'Copilot Registry', 'entity', 'file-code')
      ];
    }

    return [];
  }
}

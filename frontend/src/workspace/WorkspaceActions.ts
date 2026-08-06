export class WorkspaceActions {
  public executeAction(actionName: string, target?: string): void {
    if (actionName === 'Open Source' && target) {
      window.open(`vscode://file/${target}`);
    } else if (actionName === 'Generate Sequence Diagram') {
      alert(`Generated sequence diagram for ${target || 'selected component'}`);
    }
  }
}

export class WorkspaceHistory {
  private stack: string[] = ['backend/api.py'];
  private index: number = 0;

  public push(path: string): void {
    if (this.stack[this.index] === path) return;
    this.stack = this.stack.slice(0, this.index + 1);
    this.stack.push(path);
    this.index = this.stack.length - 1;
  }

  public back(): string | null {
    if (this.index > 0) {
      this.index -= 1;
      return this.stack[this.index];
    }
    return null;
  }

  public forward(): string | null {
    if (this.index < this.stack.length - 1) {
      this.index += 1;
      return this.stack[this.index];
    }
    return null;
  }

  public getBreadcrumbs(): string[] {
    const curr = this.stack[this.index] || 'Repository';
    const parts = curr.split('/');
    return ['Repo', ...parts];
  }
}

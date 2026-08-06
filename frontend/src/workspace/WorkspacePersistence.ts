export class WorkspacePersistence {
  private STORAGE_KEY = 'repo_workspace_settings_v11';

  public save(data: any): void {
    try {
      localStorage.setItem(this.STORAGE_KEY, JSON.stringify(data));
    } catch {
      /* ignore */
    }
  }

  public load(): any {
    try {
      const raw = localStorage.getItem(this.STORAGE_KEY);
      if (raw) return JSON.parse(raw);
    } catch {
      /* ignore */
    }
    return null;
  }
}

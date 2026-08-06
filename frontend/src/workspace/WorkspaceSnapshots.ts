import type { WorkspaceSnapshot, EngineeringIntent, WorkspaceMode, PinnedItem } from './types';

export class WorkspaceSnapshots {
  private STORAGE_KEY = 'repo_workspace_snapshots_v11';

  public getSnapshots(): WorkspaceSnapshot[] {
    try {
      const raw = localStorage.getItem(this.STORAGE_KEY);
      if (raw) return JSON.parse(raw);
    } catch {
      /* ignore */
    }
    return [
      {
        snapshot_id: 'snap-default',
        name: 'Authentication Debug Session',
        created_at: '2026-07-26',
        intent: 'Debug Issue',
        mode: 'debug',
        selected_files: ['backend/api.py', 'services/auth/service.py'],
        pinned_items: [{ id: 'backend/api.py', label: 'api.py', type: 'file' }],
        breadcrumbs: ['Repo', 'Auth', 'api.py'],
      },
    ];
  }

  public saveSnapshot(
    name: string,
    intent: EngineeringIntent,
    mode: WorkspaceMode,
    selected_files: string[],
    pinned_items: PinnedItem[],
    breadcrumbs: string[]
  ): WorkspaceSnapshot {
    const snap: WorkspaceSnapshot = {
      snapshot_id: `snap-${Date.now()}`,
      name,
      created_at: new Date().toISOString().split('T')[0],
      intent,
      mode,
      selected_files,
      pinned_items,
      breadcrumbs,
    };

    const current = this.getSnapshots();
    const updated = [snap, ...current];
    try {
      localStorage.setItem(this.STORAGE_KEY, JSON.stringify(updated));
    } catch {
      /* ignore */
    }
    return snap;
  }
}

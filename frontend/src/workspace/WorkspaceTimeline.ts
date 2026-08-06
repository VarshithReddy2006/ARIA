import type { TimelineLog } from './types';

export class WorkspaceTimeline {
  private logs: TimelineLog[] = [
    {
      log_id: 'l1',
      timestamp: new Date().toLocaleTimeString(),
      action: 'Opened File',
      target: 'backend/api.py',
      details: 'Initial workspace loading',
    },
    {
      log_id: 'l2',
      timestamp: new Date().toLocaleTimeString(),
      action: 'Inspected Architecture',
      target: 'Presentation Layer',
      details: 'Explored 9 architectural layers',
    },
  ];

  public getLogs(): TimelineLog[] {
    return [...this.logs];
  }

  public recordAction(action: string, target: string, details?: string): void {
    const newLog: TimelineLog = {
      log_id: `l-${Date.now()}`,
      timestamp: new Date().toLocaleTimeString(),
      action,
      target,
      details,
    };
    this.logs.unshift(newLog);
  }
}

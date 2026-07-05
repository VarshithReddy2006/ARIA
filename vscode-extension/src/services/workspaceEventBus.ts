import * as vscode from 'vscode';

export type WorkspaceEventType =
  | 'RepositoryChanged'
  | 'InspectionFinished'
  | 'MonitoringUpdated'
  | 'WorkspaceReloaded'
  | 'AdvisorUpdated'
  | 'ExecutionPlanUpdated';

export interface WorkspaceEvent {
  type: WorkspaceEventType;
  data?: any;
}

export class WorkspaceEventBus {
  private static _emitter = new vscode.EventEmitter<WorkspaceEvent>();
  public static readonly onEvent = WorkspaceEventBus._emitter.event;

  public static fire(type: WorkspaceEventType, data?: any): void {
    this._emitter.fire({ type, data });
  }

  public static dispose(): void {
    this._emitter.dispose();
  }
}

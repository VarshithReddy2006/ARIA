import { SelectionStore } from './SelectionStore';
import { ContextEngine } from './ContextEngine';
import { WorkspaceEvents } from './WorkspaceEvents';
import { WorkspaceHistory } from './WorkspaceHistory';
import { WorkspaceTimeline } from './WorkspaceTimeline';
import { WorkspaceSnapshots } from './WorkspaceSnapshots';
import { WorkspaceLayout } from './WorkspaceLayout';

import type { EngineeringIntent, WorkspaceMode, ContextState } from './types';

export class WorkspaceController {
  private static instance: WorkspaceController;

  public selection = new SelectionStore();
  public contextEngine = new ContextEngine();
  public events = new WorkspaceEvents();
  public history = new WorkspaceHistory();
  public timeline = new WorkspaceTimeline();
  public snapshots = new WorkspaceSnapshots();
  public layout = new WorkspaceLayout();

  private activeIntent: EngineeringIntent = 'Understand Repository';
  private activeMode: WorkspaceMode = 'explore';
  private contextState: ContextState = 'API Layer';
  private confidencePct: number = 94;

  public static getInstance(): WorkspaceController {
    if (!WorkspaceController.instance) {
      WorkspaceController.instance = new WorkspaceController();
    }
    return WorkspaceController.instance;
  }

  public getActiveIntent(): EngineeringIntent {
    return this.activeIntent;
  }

  public getActiveMode(): WorkspaceMode {
    return this.activeMode;
  }

  public getContextState(): ContextState {
    return this.contextState;
  }

  public getConfidencePct(): number {
    return this.confidencePct;
  }

  public setIntent(intent: EngineeringIntent): void {
    this.activeIntent = intent;
    const l = this.layout.getLayoutForIntent(intent);
    this.activeMode = l.mode;
    this.timeline.recordAction('Changed Intent', intent);
    this.events.emit('state_changed');
  }

  public selectFile(file_path: string): void {
    this.selection.setSelectedFile(file_path);
    this.history.push(file_path);
    this.timeline.recordAction('Opened File', file_path);

    const inferred = this.contextEngine.inferContext(file_path);
    this.contextState = inferred.contextState;
    this.confidencePct = inferred.confidencePct;

    this.events.emit('selection_changed', { file_path });
    this.events.emit('state_changed');
  }
}

export const workspaceController = WorkspaceController.getInstance();

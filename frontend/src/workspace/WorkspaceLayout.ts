import type { EngineeringIntent, WorkspaceMode } from './types';

export class WorkspaceLayout {
  public getLayoutForIntent(intent: EngineeringIntent): {
    mode: WorkspaceMode;
    leftPanelTab: string;
    showBottomDock: boolean;
    dockTab: string;
  } {
    switch (intent) {
      case 'Debug Issue':
        return { mode: 'debug', leftPanelTab: 'challenges', showBottomDock: true, dockTab: 'call_graph' };
      case 'Learn Architecture':
      case 'Understand Repository':
        return { mode: 'explore', leftPanelTab: 'explorer', showBottomDock: false, dockTab: 'scenarios' };
      case 'Implement Feature':
        return { mode: 'develop', leftPanelTab: 'apis', showBottomDock: true, dockTab: 'scenarios' };
      case 'Review Pull Request':
        return { mode: 'review', leftPanelTab: 'architecture', showBottomDock: true, dockTab: 'architecture' };
      default:
        return { mode: 'understand', leftPanelTab: 'explorer', showBottomDock: false, dockTab: 'scenarios' };
    }
  }
}

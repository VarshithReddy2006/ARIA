/**
 * Shared TypeScript types for Unified Intelligence Workspace v11, 11.1 & 11.2.
 */

export type EngineeringIntent =
  | 'Understand Repository'
  | 'Understand Feature'
  | 'Debug Issue'
  | 'Implement Feature'
  | 'Review Pull Request'
  | 'Refactor Code'
  | 'Trace Execution'
  | 'Investigate Performance'
  | 'Investigate Security'
  | 'Learn Architecture'
  | 'Prepare Documentation'
  | 'Onboard Contributor';

export type WorkspaceMode =
  | 'explore'
  | 'understand'
  | 'debug'
  | 'develop'
  | 'review';

export type ContextState =
  | 'Authentication'
  | 'Routing'
  | 'Persistence'
  | 'Caching'
  | 'Messaging'
  | 'API Layer'
  | 'Frontend'
  | 'Infrastructure'
  | 'Configuration'
  | 'Testing'
  | 'Deployment'
  | 'Documentation';

export interface PinnedItem {
  id: string;
  label: string;
  type: 'file' | 'concept' | 'layer' | 'graph' | 'scenario';
}

export interface TaskCard {
  task_id: string;
  title: string;
  description: string;
  steps: string[];
  current_step_index: number;
  completed: boolean;
}

export interface WorkspaceSnapshot {
  snapshot_id: string;
  name: string;
  created_at: string;
  intent: EngineeringIntent;
  mode: WorkspaceMode;
  selected_files: string[];
  pinned_items: PinnedItem[];
  breadcrumbs: string[];
}

export interface TimelineLog {
  log_id: string;
  timestamp: string;
  action: string;
  target: string;
  details?: string;
}

export interface CommandItem {
  id: string;
  title: string;
  category: 'Actions' | 'Navigation' | 'Intents' | 'Tools';
  shortcut?: string;
  action: () => void;
}

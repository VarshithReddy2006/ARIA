/**
 * Models for VS Code Extension Workspace State & Context Signals.
 */

export interface ActiveFileContext {
  filePath: string;
  relativeFilePath: string;
  languageId: string;
  cursorLine: number;
  selectionText?: string;
  architectureLayer?: string;
}

export interface WorkspaceState {
  repositoryId: string;
  repositoryName: string;
  activeFile?: ActiveFileContext;
  pinnedEntities: string[];
  currentIntent: string;
  isConnectedToBackend: boolean;
  backendVersion?: string;
}

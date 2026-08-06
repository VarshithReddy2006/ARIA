import React, { createContext, useContext, useState, useEffect } from 'react';
import { workspaceController } from './WorkspaceController';
import type { EngineeringIntent, WorkspaceMode, ContextState } from './types';

interface WorkspaceContextState {
  intent: EngineeringIntent;
  mode: WorkspaceMode;
  contextState: ContextState;
  confidencePct: number;
  selectedFile: string | null;
  breadcrumbs: string[];
  setIntent: (intent: EngineeringIntent) => void;
  selectFile: (path: string) => void;
  navigateBack: () => void;
  navigateForward: () => void;
}

const WorkspaceContext = createContext<WorkspaceContextState | null>(null);

export const WorkspaceProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [intent, setIntentState] = useState<EngineeringIntent>(workspaceController.getActiveIntent());
  const [mode, setModeState] = useState<WorkspaceMode>(workspaceController.getActiveMode());
  const [contextState, setContextState] = useState<ContextState>(workspaceController.getContextState());
  const [confidencePct, setConfidencePct] = useState<number>(workspaceController.getConfidencePct());
  const [selectedFile, setSelectedFile] = useState<string | null>(workspaceController.selection.getSelectedFile());
  const [breadcrumbs, setBreadcrumbs] = useState<string[]>(workspaceController.history.getBreadcrumbs());

  useEffect(() => {
    const handleStateChange = () => {
      setIntentState(workspaceController.getActiveIntent());
      setModeState(workspaceController.getActiveMode());
      setContextState(workspaceController.getContextState());
      setConfidencePct(workspaceController.getConfidencePct());
      setSelectedFile(workspaceController.selection.getSelectedFile());
      setBreadcrumbs(workspaceController.history.getBreadcrumbs());
    };

    workspaceController.events.on('state_changed', handleStateChange);
    return () => workspaceController.events.off('state_changed', handleStateChange);
  }, []);

  const setIntent = (newIntent: EngineeringIntent) => {
    workspaceController.setIntent(newIntent);
  };

  const selectFile = (path: string) => {
    workspaceController.selectFile(path);
  };

  const navigateBack = () => {
    const prev = workspaceController.history.back();
    if (prev) workspaceController.selectFile(prev);
  };

  const navigateForward = () => {
    const next = workspaceController.history.forward();
    if (next) workspaceController.selectFile(next);
  };

  return (
    <WorkspaceContext.Provider
      value={{
        intent,
        mode,
        contextState,
        confidencePct,
        selectedFile,
        breadcrumbs,
        setIntent,
        selectFile,
        navigateBack,
        navigateForward,
      }}
    >
      {children}
    </WorkspaceContext.Provider>
  );
};

export const useWorkspace = () => {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) {
    throw new Error('useWorkspace must be used within WorkspaceProvider');
  }
  return ctx;
};

/**
 * Minimal vscode module mock for unit tests running outside the VS Code host.
 *
 * Registered as a module alias so `import * as vscode from 'vscode'`
 * resolves to this file during testing.
 */

export const workspace = {
  getConfiguration: (_section?: string) => ({
    get: <T>(key: string, defaultValue?: T): T => {
      // Tests override global.__vscodeConfig__ to control values
      const overrides = (global as unknown as Record<string, Record<string, unknown>>).__vscodeConfig__ ?? {};
      if (key in overrides) {
        return overrides[key] as T;
      }
      const defaults: Record<string, unknown> = {
        backendUrl: 'http://127.0.0.1:8001',
        apiToken: '',
        requestTimeoutMs: 5000,
        activeRepository: 'owner/repo',
        'codeLens.enabled': true,
        'hover.enabled': true,
        autoRefresh: false,
        graphLayout: 'dagre',
        theme: 'auto',
      };
      return (key in defaults ? defaults[key] : defaultValue) as T;
    },
    update: async (key: string, value: unknown, target?: unknown) => {
      const updates = (global as any).__vscodeConfigUpdates__ || [];
      updates.push({ key, value, target });
      (global as any).__vscodeConfigUpdates__ = updates;
      const overrides = (global as any).__vscodeConfig__ || {};
      if (value === undefined) {
        delete overrides[key];
      } else {
        overrides[key] = value;
      }
      (global as any).__vscodeConfig__ = overrides;
    },
  }),
  asRelativePath: (uri: any, _includeWorkspaceFolder?: boolean) => {
    const fsPath = (uri && uri.fsPath) ? uri.fsPath : String(uri);
    const normalized = fsPath.replace(/\\/g, '/');
    if (normalized.startsWith('/workspace/')) {
      return normalized.substring('/workspace/'.length);
    }
    return normalized;
  },
  getWorkspaceFolder: (_uri: unknown) => ({ uri: { fsPath: '/workspace', toString: () => '/workspace' } }),
  workspaceFolders: [
    { uri: { fsPath: '/workspace', toString: () => '/workspace' } }
  ],
  onDidChangeConfiguration: (_handler: unknown) => ({ dispose: () => {} }),
  onDidSaveTextDocument: (_handler: unknown) => ({ dispose: () => {} }),
};

export const window = {
  showInformationMessage: async (_msg: string) => {},
  showErrorMessage: async (_msg: string) => {},
  showWarningMessage: async (_msg: string) => {},
  showInputBox: async (_options?: unknown) => undefined as string | undefined,
  showQuickPick: async (_items: unknown, _options?: unknown) => undefined,
  withProgress: async <T>(_options: unknown, task: () => Promise<T>) => task(),
  createOutputChannel: (_name: string) => ({
    appendLine: (_text: string) => {},
    show: () => {},
    dispose: () => {},
  }),
  createWebviewPanel: (_viewType: string, _title: string, _column: unknown, _options?: unknown) => ({
    webview: {
      html: '',
      onDidReceiveMessage: (_handler: unknown) => ({ dispose: () => {} }),
      postMessage: async (_msg: unknown) => {},
      asWebviewUri: (uri: unknown) => uri,
    },
    reveal: (_column: unknown) => {},
    onDidDispose: (_handler: () => void) => ({ dispose: () => {} }),
    dispose: () => {},
  }),
  createStatusBarItem: (_alignment?: unknown, _priority?: number) => ({
    text: '',
    tooltip: '',
    backgroundColor: undefined as unknown,
    command: '' as string | undefined,
    show: () => {},
    hide: () => {},
    dispose: () => {},
  }),
  createTreeView: (_id: string, _options: unknown) => ({
    reveal: async (_element: unknown) => {},
    dispose: () => {},
  }),
  activeTextEditor: undefined as unknown,
  visibleTextEditors: [] as any[],
  registerTreeDataProvider: (_id: string, _provider: unknown) => ({ dispose: () => {} }),
  onDidChangeActiveTextEditor: (_handler: unknown) => ({ dispose: () => {} }),
  registerFileDecorationProvider: (_provider: unknown) => ({ dispose: () => {} }),
  createTextEditorDecorationType: (_options: any) => ({
    dispose: () => {},
  }),
};

class MockDiagnosticCollection {
  private map = new Map<string, any>();
  clear() { this.map.clear(); }
  delete(uri: any) { this.map.delete(uri.toString()); }
  set(uri: any, diagnostics: any) { this.map.set(uri.toString(), diagnostics); }
  get(uri: any) { return this.map.get(uri.toString()); }
  has(uri: any) { return this.map.has(uri.toString()); }
  dispose() { this.clear(); }
}

export const languages = {
  registerHoverProvider: (_selector: unknown, _provider: unknown) => ({ dispose: () => {} }),
  registerCodeLensProvider: (_selector: unknown, _provider: unknown) => ({ dispose: () => {} }),
  createDiagnosticCollection: (_name: string) => new MockDiagnosticCollection(),
};

export const commands = {
  registerCommand: (_command: string, _callback: (...args: unknown[]) => unknown) => ({ dispose: () => {} }),
  executeCommand: async (_command: string, ..._args: unknown[]) => {},
};

export const Uri = {
  file: (path: string) => {
    const normalized = path.replace(/\\/g, '/');
    return { fsPath: normalized, toString: () => normalized };
  },
  joinPath: (base: any, ...segments: string[]) => {
    const basePath = (base && base.fsPath) ? base.fsPath : String(base);
    const joined = [basePath, ...segments].join('/').replace(/\\/g, '/');
    return { fsPath: joined, toString: () => joined };
  },
  parse: (str: string) => {
    const normalized = str.replace(/\\/g, '/');
    return { fsPath: normalized, toString: () => normalized };
  },
};

export class MarkdownString {
  public value = '';
  public isTrusted = false;
  public supportHtml = false;
  appendMarkdown(md: string) { this.value += md; return this; }
  appendCodeblock(code: string, _lang?: string) { this.value += code; return this; }
}

export class Hover {
  constructor(public contents: unknown, public range?: unknown) {}
}

export class CodeLens {
  constructor(public range: unknown, public command?: unknown) {}
}

export class Position {
  constructor(public line: number, public character: number) {}
}

export class Range {
  public start: Position;
  public end: Position;
  constructor(startLine: number, startChar: number, endLine: number, endChar: number) {
    this.start = new Position(startLine, startChar);
    this.end = new Position(endLine, endChar);
  }
}

export class ThemeColor {
  constructor(public id: string) {}
}

export class ThemeIcon {
  constructor(public id: string, public color?: unknown) {}
}

export class EventEmitter<T> {
  private _listeners: Array<(e: T) => void> = [];
  get event() {
    return (listener: (e: T) => void) => {
      this._listeners.push(listener);
      return { dispose: () => { this._listeners = this._listeners.filter((l) => l !== listener); } };
    };
  }
  fire(e: T) { this._listeners.forEach((l) => l(e)); }
  dispose() { this._listeners = []; }
}

export enum ViewColumn {
  One = 1,
  Beside = -2,
}

export enum TreeItemCollapsibleState {
  None = 0,
  Collapsed = 1,
  Expanded = 2,
}

export class TreeItem {
  public description?: string;
  public tooltip?: string;
  public command?: unknown;
  public iconPath?: unknown;
  public contextValue?: string;
  constructor(public label: string, public collapsibleState?: TreeItemCollapsibleState) {}
}

export enum StatusBarAlignment {
  Left = 1,
  Right = 2,
}

export enum ProgressLocation {
  Notification = 15,
  SourceControl = 1,
  Window = 10,
}

export enum ConfigurationTarget {
  Global = 1,
  Workspace = 2,
  WorkspaceFolder = 3,
}

export const CancellationToken = {
  isCancellationRequested: false,
  onCancellationRequested: (_handler: unknown) => ({ dispose: () => {} }),
};

export class CancellationTokenSource {
  public token = {
    isCancellationRequested: false,
    onCancellationRequested: (_handler: unknown) => ({ dispose: () => {} }),
  };
  cancel() {}
  dispose() {}
}

export enum DiagnosticSeverity {
  Error = 0,
  Warning = 1,
  Information = 2,
  Hint = 3,
}

export class Diagnostic {
  public source?: string;
  public code?: string | number;
  constructor(
    public range: Range,
    public message: string,
    public severity: DiagnosticSeverity = DiagnosticSeverity.Error
  ) {}
}

export const CodeActionKind = {
  Refactor: 'refactor',
};

export class CodeAction {
  public command?: any;
  constructor(public title: string, public kind?: any) {}
}

export enum OverviewRulerLane {
  Left = 1,
  Center = 2,
  Right = 4,
  Full = 7,
}

export const extensions = {
  getExtension: (_id: string) => undefined,
};

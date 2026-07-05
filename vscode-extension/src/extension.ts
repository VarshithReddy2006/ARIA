/**
 * Extension entry point — activate and deactivate lifecycle hooks.
 *
 * Responsibilities:
 *  - Register all commands
 *  - Register language providers (hover, CodeLens)
 *  - Register tree-view data providers
 *  - Check backend health on activation
 *
 * No analysis logic lives here. Every feature delegates to a dedicated
 * provider, panel, or API client module.
 */

import * as vscode from 'vscode';
import { registerCommands } from './commands';
import { RepoIntelligenceHoverProvider, hoverCache } from './providers/hoverProvider';
import { RepoIntelligenceCodeLensProvider, codeLensCache } from './providers/codeLensProvider';
import { RepositoryExplorerProvider } from './providers/treeViewProvider';
import { FindingsTreeProvider, AdvisorTreeProvider, ExecutionTreeProvider, BackendConnectionProvider } from './providers/workspaceTreeProviders';
import { RepoIntelDiagnosticProvider } from './providers/diagnosticProvider';
import { RepoIntelFileDecorationProvider } from './providers/fileDecorationProvider';
import { ReadingPathProvider } from './providers/readingPathProvider';
import { StatusBarService } from './services/statusBarService';
import { WorkspaceEventBus } from './services/workspaceEventBus';
import { client, extractErrorMessage } from './api';
import { StateService } from './utils/stateService';
import { OutputChannelService } from './utils/outputChannelService';
import { RepoIntelCodeActionProvider } from './providers/codeActionProvider';
import { RepoIntelInlineDecorationProvider } from './providers/inlineDecorationProvider';
import { NotificationWatcher } from './services/notificationWatcher';
import { Logger } from './utils/logger';
import { IgnoredRecommendationService } from './services/ignoredRecommendationService';
import { splitRepo } from './utils/repoUtils';

// Status bar item shared across the extension
let statusBarItem: vscode.StatusBarItem;

export function activate(context: vscode.ExtensionContext): void {
  // ── [DIAG] Startup diagnostics — remove after confirming views appear ──
  console.log('Repo Intelligence activating...');
  console.log('Extension path:', context.extensionPath);
  console.log('Extension URI:', context.extensionUri.toString());
  console.log('Extension package:', context.extension.packageJSON.name);
  console.log('VS Code version:', vscode.version);
  // ── [/DIAG] ────────────────────────────────────────────────────────────

  // Initialize State
  StateService.initialize(context);

  // Initialize IgnoredRecommendationService
  IgnoredRecommendationService.initialize(context);

  // Initialize Logger
  Logger.initialize();
  context.subscriptions.push(new vscode.Disposable(() => Logger.dispose()));

  const cfg = vscode.workspace.getConfiguration('repoIntelligence');

  // Migrate API token to SecretStorage
  void (async () => {
    const apiToken = cfg.get<string>('apiToken');
    if (apiToken) {
      await context.secrets.store('repoIntelligence.apiToken', apiToken);
      await cfg.update('apiToken', undefined, vscode.ConfigurationTarget.Global);
      await cfg.update('apiToken', undefined, vscode.ConfigurationTarget.Workspace);
    }
    const currentSecretToken = await context.secrets.get('repoIntelligence.apiToken');
    client.setToken(currentSecretToken ?? '');
  })();

  // Listen for SecretStorage changes
  context.subscriptions.push(
    context.secrets.onDidChange(async (e) => {
      if (e.key === 'repoIntelligence.apiToken') {
        client.setToken(await context.secrets.get(e.key) ?? '');
      }
    })
  );

  // Configure unauthorized callback for prompt-and-retry
  client.onUnauthorized = async () => {
    const input = await vscode.window.showInputBox({
      prompt: 'Enter API Token for Repo Intelligence',
      password: true,
      ignoreFocusOut: true,
    });
    if (input !== undefined) {
      await context.secrets.store('repoIntelligence.apiToken', input);
      return input;
    }
    return undefined;
  };

  // Register Update API Token command
  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.updateApiToken', async () => {
      const input = await vscode.window.showInputBox({
        prompt: 'Update API Token for Repo Intelligence',
        password: true,
        ignoreFocusOut: true,
      });
      if (input !== undefined) {
        await context.secrets.store('repoIntelligence.apiToken', input);
        void vscode.window.showInformationMessage('API token updated successfully.');
      }
    })
  );

  // Evict closed documents from LRU caches
  context.subscriptions.push(
    vscode.workspace.onDidCloseTextDocument((doc) => {
      hoverCache.delete(doc.uri.toString());
      codeLensCache.delete(doc.uri.toString());
    })
  );

  // ── Services & Event Bus ────────────────────────────────────────────────
  StatusBarService.initialize(context);
  statusBarItem = StatusBarService.statusBarItem;
  ReadingPathProvider.initialize(context);

  // ── Providers ──────────────────────────────────────────────────────────
  context.subscriptions.push(new RepoIntelDiagnosticProvider(context));
  const fileDecoProvider = new RepoIntelFileDecorationProvider(context);
  context.subscriptions.push(fileDecoProvider);
  context.subscriptions.push(
    vscode.window.registerFileDecorationProvider(fileDecoProvider)
  );
  context.subscriptions.push(new RepoIntelInlineDecorationProvider(context));
  context.subscriptions.push(new NotificationWatcher(context));

  // Code Actions Provider
  context.subscriptions.push(
    vscode.languages.registerCodeActionsProvider(
      [
        { language: 'python' },
        { language: 'javascript' },
        { language: 'typescript' },
        { language: 'javascriptreact' },
        { language: 'typescriptreact' },
      ],
      new RepoIntelCodeActionProvider(),
      {
        providedCodeActionKinds: [vscode.CodeActionKind.Refactor]
      }
    )
  );

  // ── Language providers ─────────────────────────────────────────────────

  if (cfg.get<boolean>('hover.enabled') !== false) {
    const hoverProvider = new RepoIntelligenceHoverProvider();
    context.subscriptions.push(
      vscode.languages.registerHoverProvider(
        [
          { language: 'python' },
          { language: 'javascript' },
          { language: 'typescript' },
          { language: 'javascriptreact' },
          { language: 'typescriptreact' },
        ],
        hoverProvider
      )
    );
  }

  if (cfg.get<boolean>('codeLens.enabled') !== false) {
    const codeLensProvider = new RepoIntelligenceCodeLensProvider();
    context.subscriptions.push(codeLensProvider);
    context.subscriptions.push(
      vscode.languages.registerCodeLensProvider(
        [
          { language: 'python' },
          { language: 'javascript' },
          { language: 'typescript' },
          { language: 'javascriptreact' },
          { language: 'typescriptreact' },
        ],
        codeLensProvider
      )
    );
  }

  // ── Tree views ─────────────────────────────────────────────────────────
  const explorerProvider = new RepositoryExplorerProvider(context);
  try {
    Logger.info('Registering TreeView: repoIntelligenceExplorer');
    const explorerView = vscode.window.createTreeView('repoIntelligenceExplorer', {
      treeDataProvider: explorerProvider,
      showCollapseAll: true,
    });
    context.subscriptions.push(explorerView);
    Logger.info('TreeView registered: repoIntelligenceExplorer');
  } catch (err) {
    Logger.error('TreeView registration FAILED: repoIntelligenceExplorer', err);
  }

  const findingsProvider = new FindingsTreeProvider();
  context.subscriptions.push(findingsProvider);
  try {
    Logger.info('Registering TreeView: repoIntelligenceFindings');
    const findingsView = vscode.window.createTreeView('repoIntelligenceFindings', {
      treeDataProvider: findingsProvider,
      showCollapseAll: true,
    });
    context.subscriptions.push(findingsView);
    Logger.info('TreeView registered: repoIntelligenceFindings');
  } catch (err) {
    Logger.error('TreeView registration FAILED: repoIntelligenceFindings', err);
  }

  const advisorProvider = new AdvisorTreeProvider();
  context.subscriptions.push(advisorProvider);
  try {
    Logger.info('Registering TreeView: repoIntelligenceAdvisor');
    const advisorView = vscode.window.createTreeView('repoIntelligenceAdvisor', {
      treeDataProvider: advisorProvider,
      showCollapseAll: true,
    });
    context.subscriptions.push(advisorView);
    Logger.info('TreeView registered: repoIntelligenceAdvisor');
  } catch (err) {
    Logger.error('TreeView registration FAILED: repoIntelligenceAdvisor', err);
  }

  const executionProvider = new ExecutionTreeProvider();
  context.subscriptions.push(executionProvider);
  try {
    Logger.info('Registering TreeView: repoIntelligenceExecution');
    const executionView = vscode.window.createTreeView('repoIntelligenceExecution', {
      treeDataProvider: executionProvider,
      showCollapseAll: true,
    });
    context.subscriptions.push(executionView);
    Logger.info('TreeView registered: repoIntelligenceExecution');
  } catch (err) {
    Logger.error('TreeView registration FAILED: repoIntelligenceExecution', err);
  }

  const connectionProvider = new BackendConnectionProvider();
  context.subscriptions.push(connectionProvider);
  try {
    Logger.info('Registering TreeView: repoIntelligenceConnection');
    const connectionView = vscode.window.createTreeView('repoIntelligenceConnection', {
      treeDataProvider: connectionProvider,
      showCollapseAll: false,
    });
    context.subscriptions.push(connectionView);
    Logger.info('TreeView registered: repoIntelligenceConnection');
  } catch (err) {
    Logger.error('TreeView registration FAILED: repoIntelligenceConnection', err);
  }

  // Allow commands to refresh the trees
  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.explorerRefresh', () => {
      explorerProvider.refresh();
      findingsProvider.refresh();
      advisorProvider.refresh();
      executionProvider.refresh();
      connectionProvider.refresh();
    })
  );

  // ── All other commands ─────────────────────────────────────────────────
  registerCommands(context, explorerProvider);

  // ── Configuration changes ──────────────────────────────────────────────
  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration('repoIntelligence.logLevel')) {
        Logger.updateLogLevel();
      }
      if (e.affectsConfiguration('repoIntelligence')) {
        explorerProvider.refresh();
        findingsProvider.refresh();
        advisorProvider.refresh();
        executionProvider.refresh();
        connectionProvider.refresh();
      }
    })
  );

  // ── Auto-refresh on save ───────────────────────────────────────────────
  context.subscriptions.push(
    vscode.workspace.onDidSaveTextDocument(() => {
      const autoCfg = vscode.workspace.getConfiguration('repoIntelligence');
      if (autoCfg.get<boolean>('autoRefresh')) {
        explorerProvider.refresh();
        findingsProvider.refresh();
        advisorProvider.refresh();
        executionProvider.refresh();
        connectionProvider.refresh();
      }
    })
  );

  // ── Clear ignored recommendations on new repository analysis ───────────
  context.subscriptions.push(
    WorkspaceEventBus.onEvent((e) => {
      if (e.type === 'InspectionFinished') {
        const activeRepo = StateService.getActiveRepository();
        if (activeRepo) {
          void (async () => {
            try {
              const [owner, repoName] = splitRepo(activeRepo);
              const overview = await client.getOverview(owner, repoName);
              const lastIndexed = overview.last_indexed_at;
              if (lastIndexed) {
                await IgnoredRecommendationService.checkAndClearIfAnalysisChanged(owner, repoName, lastIndexed.toString());
              }
            } catch (err) {
              Logger.error('Failed to check and clear ignored recommendations', err);
            }
          })();
        }
      }
    })
  );

  // ── Initial health probe ───────────────────────────────────────────────
  void checkBackendHealth(statusBarItem);
}

export function deactivate(): void {
  OutputChannelService.dispose();
  WorkspaceEventBus.dispose();
}

/**
 * Probe the backend on startup and update the status bar.
 * Never throws — failure just changes the status bar icon.
 */
async function checkBackendHealth(bar: vscode.StatusBarItem): Promise<void> {
  try {
    const health = await client.health();
    if (health.status === 'healthy') {
      bar.text = '$(check) Repo Intelligence';
      bar.tooltip = `Backend online — ${health.llm_model}`;
      bar.backgroundColor = undefined;
    } else {
      bar.text = '$(warning) Repo Intelligence';
      bar.tooltip = 'Backend reachable but reported unhealthy status.';
    }
  } catch (err) {
    bar.text = '$(circle-slash) Repo Intelligence';
    bar.tooltip = `Backend offline: ${extractErrorMessage(err)}. Click to open dashboard.`;
    bar.backgroundColor = new vscode.ThemeColor('statusBarItem.warningBackground');
  }
}

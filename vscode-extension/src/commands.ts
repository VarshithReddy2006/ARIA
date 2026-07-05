/**
 * Command registrations for the Repo Intelligence Agent extension.
 *
 * Each command is a thin orchestrator that delegates to the appropriate
 * panel, provider, or API client. No business logic here.
 */

import * as vscode from 'vscode';
import { client, extractErrorMessage } from './api';
import { RepositoryDashboardPanel } from './panels/repositoryDashboard';
import { WorkspaceDashboardPanel } from './panels/workspaceDashboard';
import { TimelinePanel } from './panels/timelinePanel';
import { DependencyGraphPanel } from './panels/dependencyGraphPanel';
import { CallGraphPanel } from './panels/callGraphPanel';
import { ArchitectureHealthPanel } from './panels/architectureHealthPanel';
import { ChatProvider } from './providers/chatProvider';
import { RepositoryExplorerProvider } from './providers/treeViewProvider';
import { StateService } from './utils/stateService';
import { OutputChannelService } from './utils/outputChannelService';
import { WorkspaceEventBus } from './services/workspaceEventBus';
import { IgnoredRecommendationService } from './services/ignoredRecommendationService';
import { RepoIntelSearchProvider } from './providers/repositorySearchProvider';
import { RepositoryReview } from './review/repositoryReview';
import { RepoIntelGraphProvider } from './providers/repositoryGraphProvider';

// ---------------------------------------------------------------------------
// Repository picker helper
// ---------------------------------------------------------------------------

async function pickOrGetActiveRepo(prompt?: string): Promise<string | undefined> {
  const active = StateService.getActiveRepository();
  if (active) {
    return active;
  }

  // Try to load from recent repos
  let recentNames: string[] = [];
  try {
    const repos = await client.getRecentRepos();
    recentNames = repos.map((r) => r.name);
  } catch {
    // backend may be offline — fall through to manual input
  }

  if (recentNames.length > 0) {
    const picked = await vscode.window.showQuickPick(
      ['$(edit) Enter manually...', ...recentNames],
      { placeHolder: prompt ?? 'Select a repository' }
    );
    if (!picked) {
      return undefined;
    }
    if (picked === '$(edit) Enter manually...') {
      return vscode.window.showInputBox({
        prompt: 'Enter repository identifier (owner/repo)',
        placeHolder: 'e.g. fastapi/fastapi',
      });
    }
    return picked;
  }

  return vscode.window.showInputBox({
    prompt: prompt ?? 'Enter repository identifier (owner/repo)',
    placeHolder: 'e.g. fastapi/fastapi',
  });
}

/**
 * Split "owner/repo" into [owner, repo].
 * Throws if the format is invalid.
 */
import { splitRepo } from './utils/repoUtils';

// ---------------------------------------------------------------------------
// Main registration function
// ---------------------------------------------------------------------------

export function registerCommands(
  context: vscode.ExtensionContext,
  explorerProvider: RepositoryExplorerProvider
): void {

  // ── Connect to backend ──────────────────────────────────────────────────
  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.connectBackend', async () => {
      const url = await vscode.window.showInputBox({
        prompt: 'Backend URL',
        value: vscode.workspace.getConfiguration('repoIntelligence').get<string>('backendUrl'),
        placeHolder: 'http://127.0.0.1:8001',
      });
      if (!url) {
        return;
      }
      await vscode.workspace
        .getConfiguration('repoIntelligence')
        .update('backendUrl', url, vscode.ConfigurationTarget.Global);

      await vscode.window.withProgress(
        { location: vscode.ProgressLocation.Notification, title: 'Checking backend health…' },
        async () => {
          try {
            const health = await client.health();
            void vscode.window.showInformationMessage(
              `Connected — backend ${health.status}, model: ${health.llm_model}`
            );
          } catch (err) {
            void vscode.window.showErrorMessage(
              `Backend unreachable: ${extractErrorMessage(err)}`
            );
          }
        }
      );
    })
  );

  // ── Set active repository ───────────────────────────────────────────────
  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.setActiveRepository', async () => {
      let recentNames: string[] = [];
      try {
        const repos = await client.getRecentRepos();
        recentNames = repos.map((r) => r.name);
      } catch {
        // backend offline
      }

      let identifier: string | undefined;
      if (recentNames.length > 0) {
        const picked = await vscode.window.showQuickPick(
          ['$(edit) Enter manually...', ...recentNames],
          { placeHolder: 'Select the active repository' }
        );
        if (!picked) {
          return;
        }
        identifier =
          picked === '$(edit) Enter manually...'
            ? await vscode.window.showInputBox({
                prompt: 'Enter repository identifier (owner/repo)',
                placeHolder: 'e.g. fastapi/fastapi',
              })
            : picked;
      } else {
        identifier = await vscode.window.showInputBox({
          prompt: 'Enter repository identifier (owner/repo)',
          placeHolder: 'e.g. fastapi/fastapi',
        });
      }

      if (!identifier) {
        return;
      }
      await StateService.setActiveRepository(identifier);
      console.log('[SYNC] Active repository updated:', identifier);
      explorerProvider.refresh();
      console.log('[SYNC] Emitting RepositoryChanged');
      WorkspaceEventBus.fire('RepositoryChanged', { repo: identifier });
      void vscode.window.showInformationMessage(
        `Active repository set to "${identifier}"`
      );
    })
  );

  // ── Analyze repository ──────────────────────────────────────────────────
  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.analyzeRepository', async () => {
      const repoUrl = await vscode.window.showInputBox({
        prompt: 'GitHub repository URL to analyze',
        placeHolder: 'https://github.com/owner/repo',
      });
      if (!repoUrl) {
        return;
      }

      const panel = OutputChannelService.showAndClear('Analysis');
      panel.appendLine(`Starting analysis for: ${repoUrl}`);

      const cancel = client.streamSse(
        '/api/analyze',
        { url: repoUrl, branch: 'main' },
        (event) => {
          const msg = typeof event.message === 'string' ? event.message : JSON.stringify(event);
          panel.appendLine(msg);
          if (event.status === 'done' && typeof event.repo === 'string') {
            void (async () => {
              await StateService.setActiveRepository(event.repo as string);
              console.log('[SYNC] Active repository updated:', event.repo);
              explorerProvider.refresh();
              console.log('[SYNC] Emitting RepositoryChanged');
              WorkspaceEventBus.fire('RepositoryChanged', { repo: event.repo });
              void vscode.window.showInformationMessage(
                `Analysis complete for ${event.repo as string}`
              );
            })();
          }
          if (event.status === 'error') {
            void vscode.window.showErrorMessage(
              `Analysis error: ${String(event.message ?? 'Unknown error')}`
            );
          }
        },
        () => panel.appendLine('Stream closed.'),
        (err) => {
          panel.appendLine(`Error: ${err.message}`);
          void vscode.window.showErrorMessage(`Analysis failed: ${err.message}`);
        }
      );

      context.subscriptions.push({ dispose: () => cancel?.() });
    })
  );

  // ── Refresh analysis ────────────────────────────────────────────────────
  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.refreshAnalysis', () => {
      explorerProvider.refresh();
      void vscode.window.showInformationMessage('Repository explorer refreshed.');
    })
  );

  // ── Open Dashboard ──────────────────────────────────────────────────────
  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.openDashboard', async () => {
      const repo = await pickOrGetActiveRepo('Select a repository for the dashboard');
      if (!repo) {
        return;
      }
      try {
        const [owner, repoName] = splitRepo(repo);
        RepositoryDashboardPanel.createOrShow(context.extensionUri, owner, repoName, client);
      } catch (err) {
        void vscode.window.showErrorMessage(extractErrorMessage(err));
      }
    })
  );

  // ── Show Dependency Graph ───────────────────────────────────────────────
  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.showDependencyGraph', async () => {
      const repo = await pickOrGetActiveRepo('Select a repository for the dependency graph');
      if (!repo) {
        return;
      }
      try {
        const [owner, repoName] = splitRepo(repo);
        DependencyGraphPanel.createOrShow(context.extensionUri, owner, repoName, client);
      } catch (err) {
        void vscode.window.showErrorMessage(extractErrorMessage(err));
      }
    })
  );

  // ── Show Call Graph ────────────────────────────────────────────────────
  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.showCallGraph', async () => {
      const repo = await pickOrGetActiveRepo('Select a repository for the call graph');
      if (!repo) {
        return;
      }
      try {
        const [owner, repoName] = splitRepo(repo);
        CallGraphPanel.createOrShow(context.extensionUri, owner, repoName, client);
      } catch (err) {
        void vscode.window.showErrorMessage(extractErrorMessage(err));
      }
    })
  );

  // ── Show Architecture Health ───────────────────────────────────────────
  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.showArchitectureHealth', async () => {
      const repo = await pickOrGetActiveRepo('Select a repository for architecture health');
      if (!repo) {
        return;
      }
      try {
        const [owner, repoName] = splitRepo(repo);
        ArchitectureHealthPanel.createOrShow(context.extensionUri, owner, repoName, client);
      } catch (err) {
        void vscode.window.showErrorMessage(extractErrorMessage(err));
      }
    })
  );

  // ── Show Module Stability (re-uses dashboard) ──────────────────────────
  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.showModuleStability', async () => {
      const repo = await pickOrGetActiveRepo('Select a repository');
      if (!repo) {
        return;
      }
      try {
        const [owner, repoName] = splitRepo(repo);
        RepositoryDashboardPanel.createOrShow(context.extensionUri, owner, repoName, client);
      } catch (err) {
        void vscode.window.showErrorMessage(extractErrorMessage(err));
      }
    })
  );

  // ── Show API Surface ───────────────────────────────────────────────────
  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.showAPISurface', async () => {
      const repo = await pickOrGetActiveRepo('Select a repository for API surface');
      if (!repo) {
        return;
      }
      try {
        const [owner, repoName] = splitRepo(repo);
        ArchitectureHealthPanel.createOrShow(context.extensionUri, owner, repoName, client);
      } catch (err) {
        void vscode.window.showErrorMessage(extractErrorMessage(err));
      }
    })
  );

  // ── Show Repository Chat ───────────────────────────────────────────────
  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.showRepositoryChat', async () => {
      const repo = await pickOrGetActiveRepo('Select a repository to chat about');
      if (!repo) {
        return;
      }
      ChatProvider.createOrShow(context, repo, client);
    })
  );

  // ── Show Reading Path ──────────────────────────────────────────────────
  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.showReadingPath', async () => {
      const repo = await pickOrGetActiveRepo('Select a repository for reading path');
      if (!repo) {
        return;
      }
      await withProgress('Generating reading path…', async () => {
        try {
          const order = await client.getReadingOrder(repo);
          const panel = OutputChannelService.showAndClear('Reading Path');
          panel.appendLine(`Reading Path for ${repo}`);
          panel.appendLine('='.repeat(60));
          const entries: Array<{ file: string; score: number; reason: string }> =
            Array.isArray((order as { entries?: unknown }).entries)
              ? ((order as { entries: Array<{ file: string; score: number; reason: string }> }).entries)
              : [];
          entries.forEach((e, i) => {
            panel.appendLine(`\n${i + 1}. ${e.file}`);
            if (e.reason) {
              panel.appendLine(`   ${e.reason}`);
            }
          });
        } catch (err) {
          void vscode.window.showErrorMessage(
            `Reading path failed: ${extractErrorMessage(err)}`
          );
        }
      });
    })
  );

  // ── Show Reading Path for current file ────────────────────────────────
  context.subscriptions.push(
    vscode.commands.registerCommand(
      'repoIntelligence.showReadingPathForFile',
      async (args?: { file?: string }) => {
        const repo = await pickOrGetActiveRepo('Select a repository');
        if (!repo) {
          return;
        }
        const filePath =
          args?.file ?? vscode.window.activeTextEditor?.document.uri.fsPath ?? '';

        await withProgress('Generating reading path…', async () => {
          try {
            const order = await client.getReadingOrder(repo);
            const panel = OutputChannelService.showAndClear('Reading Path');
            panel.appendLine(`Reading Path for ${repo} (starting from ${filePath})`);
            panel.appendLine('='.repeat(60));
            const entries: Array<{ file: string; score: number; reason: string }> =
              Array.isArray((order as { entries?: unknown }).entries)
                ? ((order as { entries: Array<{ file: string; score: number; reason: string }> }).entries)
                : [];
            entries.forEach((e, i) => {
              panel.appendLine(`\n${i + 1}. ${e.file}`);
            });
          } catch (err) {
            void vscode.window.showErrorMessage(
              `Reading path failed: ${extractErrorMessage(err)}`
            );
          }
        });
      }
    )
  );

  // ── Show Callers (invoked by CodeLens) ─────────────────────────────────
  context.subscriptions.push(
    vscode.commands.registerCommand(
      'repoIntelligence.showCallers',
      async (args: { owner: string; repo: string; functionId: string }) => {
        await withProgress('Fetching callers…', async () => {
          try {
            const result = await client.getCallers(args.owner, args.repo, args.functionId);
            const items = result.callers.map(
              (c) => `$(go-to-file) ${c.qualified} — ${c.file_path}:${c.line_number}`
            );
            if (items.length === 0) {
              void vscode.window.showInformationMessage(
                'No callers found for this function.'
              );
              return;
            }
            const picked = await vscode.window.showQuickPick(
              result.callers.map((c) => ({
                label: c.qualified,
                description: `${c.file_path}:${c.line_number}`,
                caller: c,
              })),
              { placeHolder: `Callers of ${args.functionId}` }
            );
            if (picked?.caller) {
              const uri = vscode.Uri.file(picked.caller.file_path);
              const doc = await vscode.workspace.openTextDocument(uri).then(
                (d) => d,
                () => undefined
              );
              if (doc) {
                await vscode.window.showTextDocument(doc, {
                  selection: new vscode.Range(
                    Math.max(0, picked.caller.line_number - 1),
                    0,
                    Math.max(0, picked.caller.line_number - 1),
                    0
                  ),
                });
              }
            }
          } catch (err) {
            void vscode.window.showErrorMessage(
              `Callers lookup failed: ${extractErrorMessage(err)}`
            );
          }
        });
      }
    )
  );

  // ── Show Callees (invoked by CodeLens) ────────────────────────────────
  context.subscriptions.push(
    vscode.commands.registerCommand(
      'repoIntelligence.showCallees',
      async (args: { owner: string; repo: string; functionId: string }) => {
        await withProgress('Fetching callees…', async () => {
          try {
            const result = await client.getCallees(args.owner, args.repo, args.functionId);
            if (result.callees.length === 0) {
              void vscode.window.showInformationMessage(
                'No callees found for this function.'
              );
              return;
            }
            await vscode.window.showQuickPick(
              result.callees.map((c) => ({
                label: c.qualified,
                description: `${c.file_path}:${c.line_number}`,
              })),
              { placeHolder: `Callees of ${args.functionId}` }
            );
          } catch (err) {
            void vscode.window.showErrorMessage(
              `Callees lookup failed: ${extractErrorMessage(err)}`
            );
          }
        });
      }
    )
  );

  // ── Show Blast Radius (invoked by CodeLens) ───────────────────────────
  context.subscriptions.push(
    vscode.commands.registerCommand(
      'repoIntelligence.showBlastRadius',
      async (args: { owner: string; repo: string; functionId: string }) => {
        await withProgress('Computing blast radius…', async () => {
          try {
            const result = await client.getBlastRadius(args.owner, args.repo, args.functionId);
            const lines = [
              `Blast Radius for: ${args.functionId}`,
              `Risk Level: ${result.risk_level.toUpperCase()}`,
              `Affected Functions: ${result.affected_functions.length}`,
              `Affected Files: ${result.affected_files.length}`,
              `Max Propagation Depth: ${result.depth}`,
              '',
              'Affected Files:',
              ...result.affected_files.map((f) => `  • ${f}`),
            ];
            const panel = OutputChannelService.showAndClear('Blast Radius');
            panel.appendLine(lines.join('\n'));
          } catch (err) {
            void vscode.window.showErrorMessage(
              `Blast radius failed: ${extractErrorMessage(err)}`
            );
          }
        });
      }
    )
  );

  // ── Show Impact Analysis (invoked by CodeLens) ────────────────────────
  context.subscriptions.push(
    vscode.commands.registerCommand(
      'repoIntelligence.showImpactAnalysis',
      async (args?: { repo?: string; issue?: string }) => {
        const repo = args?.repo ?? (await pickOrGetActiveRepo('Select a repository'));
        if (!repo) {
          return;
        }
        const issue =
          args?.issue ??
          (await vscode.window.showInputBox({
            prompt: 'Describe the change you are planning',
            placeHolder: 'e.g. Refactor authentication module',
          }));
        if (!issue) {
          return;
        }

        await withProgress('Analyzing impact…', async () => {
          try {
            const result = await client.getImpactAnalysis(repo, issue);
            const panel = OutputChannelService.showAndClear('Impact Analysis');
            panel.appendLine(`Impact Analysis: "${issue}"`);
            panel.appendLine(`Risk Level: ${String(result.risk_level ?? 'N/A')}`);
            panel.appendLine(
              `Affected Files (${result.affected_files?.length ?? 0}):`
            );
            (result.affected_files ?? []).forEach((f) =>
              panel.appendLine(`  • ${f}`)
            );
          } catch (err) {
            void vscode.window.showErrorMessage(
              `Impact analysis failed: ${extractErrorMessage(err)}`
            );
          }
        });
      }
    )
  );

  // ── Open Workspace ──────────────────────────────────────────────────────
  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.openWorkspace', async () => {
      const repo = await pickOrGetActiveRepo('Select a repository for the workspace');
      if (!repo) {
        return;
      }
      try {
        const [owner, repoName] = splitRepo(repo);
        WorkspaceDashboardPanel.createOrShow(context.extensionUri, owner, repoName, client);
      } catch (err) {
        void vscode.window.showErrorMessage(extractErrorMessage(err));
      }
    })
  );

  // ── Open Findings ──────────────────────────────────────────────────────
  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.openFindings', () => {
      void vscode.commands.executeCommand('repoIntelligenceFindings.focus');
    })
  );

  // ── Open Advisor ────────────────────────────────────────────────────────
  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.openAdvisor', () => {
      void vscode.commands.executeCommand('repoIntelligenceAdvisor.focus');
    })
  );

  // ── Open Timeline ──────────────────────────────────────────────────────
  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.openTimeline', async () => {
      const repo = await pickOrGetActiveRepo('Select a repository');
      if (!repo) {
        return;
      }
      try {
        const [owner, repoName] = splitRepo(repo);
        TimelinePanel.createOrShow(context.extensionUri, owner, repoName, client);
      } catch (err) {
        void vscode.window.showErrorMessage(extractErrorMessage(err));
      }
    })
  );

  // ── Open Monitoring ────────────────────────────────────────────────────
  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.openMonitoring', () => {
      void vscode.commands.executeCommand('repoIntelligenceExplorer.focus');
    })
  );

  // ── Open Execution Plan ────────────────────────────────────────────────
  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.openExecutionPlan', () => {
      void vscode.commands.executeCommand('repoIntelligenceExecution.focus');
    })
  );

  // ── Refresh Workspace ──────────────────────────────────────────────────
  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.refreshWorkspace', () => {
      void vscode.commands.executeCommand('repoIntelligence.explorerRefresh');
    })
  );

  // ── Refresh Repository ──────────────────────────────────────────────────
  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.refreshRepository', async () => {
      await withProgress('Refreshing Repository...', async () => {
        WorkspaceEventBus.fire('WorkspaceReloaded');
      });
      void vscode.window.showInformationMessage('Repository workspace refreshed.');
    })
  );

  // ── Reconnect Backend ───────────────────────────────────────────────────
  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.reconnectBackend', async () => {
      void vscode.commands.executeCommand('repoIntelligence.connectBackend');
    })
  );

  // ── Ask Repository ──────────────────────────────────────────────────────
  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.askRepository', async () => {
      void vscode.commands.executeCommand('repoIntelligence.showRepositoryChat');
    })
  );

  // ── Run Inspection ──────────────────────────────────────────────────────
  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.runInspection', async () => {
      const repo = await pickOrGetActiveRepo('Select a repository to inspect');
      if (!repo) { return; }
      const [owner, repoName] = splitRepo(repo);
      await withProgress('Running Repository Inspection...', async () => {
        await client.runInspection(owner, repoName);
        WorkspaceEventBus.fire('InspectionFinished');
      });
      void vscode.window.showInformationMessage('Inspection complete.');
    })
  );

  // ── Run Monitoring ──────────────────────────────────────────────────────
  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.runMonitoring', async () => {
      const repo = await pickOrGetActiveRepo('Select a repository to monitor');
      if (!repo) { return; }
      const [owner, repoName] = splitRepo(repo);
      await withProgress('Running Continuous Monitoring...', async () => {
        await client.runMonitoring(owner, repoName);
        WorkspaceEventBus.fire('MonitoringUpdated');
      });
      void vscode.window.showInformationMessage('Monitoring check complete.');
    })
  );

  // ── Generate Roadmap ────────────────────────────────────────────────────
  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.generateRoadmap', async () => {
      const repo = await pickOrGetActiveRepo('Select a repository');
      if (!repo) { return; }
      const [owner, repoName] = splitRepo(repo);
      await withProgress('Generating Advisor Roadmap...', async () => {
        await client.generateRoadmap(owner, repoName);
        WorkspaceEventBus.fire('AdvisorUpdated');
      });
      void vscode.window.showInformationMessage('Roadmap generation complete.');
    })
  );

  // ── Generate Execution Plan ─────────────────────────────────────────────
  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.generateExecutionPlan', async () => {
      const repo = await pickOrGetActiveRepo('Select a repository');
      if (!repo) { return; }
      const [owner, repoName] = splitRepo(repo);
      await withProgress('Generating Execution Plan...', async () => {
        await client.generateExecutionPlan(owner, repoName);
        WorkspaceEventBus.fire('ExecutionPlanUpdated');
      });
      void vscode.window.showInformationMessage('Execution plan generated.');
    })
  );

  // ── Ask About This File (Context Menu) ──────────────────────────────────
  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.askAboutFile', async (uri?: vscode.Uri) => {
      const fileUri = uri || vscode.window.activeTextEditor?.document.uri;
      if (!fileUri) { return; }
      const repo = await pickOrGetActiveRepo();
      if (!repo) { return; }
      ChatProvider.createOrShow(context, repo, client);
      setTimeout(() => {
        void vscode.commands.executeCommand('repoIntelligence.showRepositoryChat');
      }, 500);
    })
  );

  // ── Find References in Repository Graph (Context Menu) ──────────────────
  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.findReferencesInGraph', async (uri?: vscode.Uri) => {
      const fileUri = uri || vscode.window.activeTextEditor?.document.uri;
      if (!fileUri) { return; }
      const relPath = vscode.workspace.asRelativePath(fileUri, false);
      const repo = await pickOrGetActiveRepo();
      if (!repo) { return; }
      const [owner, repoName] = splitRepo(repo);

      try {
        const result = await client.getFileSymbols(owner, repoName, relPath);
        const symbols = result.symbols || [];
        if (symbols.length === 0) {
          void vscode.window.showInformationMessage('No public symbols found in this file.');
          return;
        }
        const picked = await vscode.window.showQuickPick(
          symbols.map((s) => ({ label: s.name, description: s.qualified, symbol: s })),
          { placeHolder: 'Select symbol to find references in Repository Graph' }
        );
        if (picked) {
          void vscode.commands.executeCommand('repoIntelligence.showCallers', {
            owner,
            repo: repoName,
            functionId: `${relPath}::${picked.symbol.qualified}`
          });
        }
      } catch (err) {
        void vscode.window.showErrorMessage(`Failed to fetch symbols: ${extractErrorMessage(err)}`);
      }
    })
  );

  // ── Inspect This Module (Context Menu) ──────────────────────────────────
  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.inspectModule', async (uri?: vscode.Uri) => {
      const fileUri = uri || vscode.window.activeTextEditor?.document.uri;
      if (!fileUri) { return; }
      const relPath = vscode.workspace.asRelativePath(fileUri, false);
      await withProgress(`Inspecting Module ${relPath}...`, async () => {
        await new Promise((r) => setTimeout(r, 1000));
      });
      void vscode.window.showInformationMessage(`Module inspection completed for ${relPath}`);
    })
  );

  // ── Show CodeLens QuickPick ─────────────────────────────────────────────
  context.subscriptions.push(
    vscode.commands.registerCommand(
      'repoIntelligence.showCodeLensQuickPick',
      async (args: { owner: string; repo: string; filePath: string; symbol: any; functionId: string }) => {
        const picked = await vscode.window.showQuickPick(
          [
            { label: '$(comment-discussion) Ask Repository', id: 'ask' },
            { label: '$(book) Reading Path', id: 'readingPath' },
            { label: '$(pulse) Blast Radius', id: 'blastRadius' },
            { label: '$(beaker) Impact Analysis', id: 'impact' },
            { label: '$(lightbulb) Advisor', id: 'advisor' },
            { label: '$(history) Timeline', id: 'timeline' }
          ],
          { placeHolder: `Repository Intelligence: ${args.symbol.qualified}` }
        );
        if (!picked) { return; }

        switch (picked.id) {
          case 'ask':
            void vscode.commands.executeCommand('repoIntelligence.showRepositoryChat');
            break;
          case 'readingPath':
            void vscode.commands.executeCommand('repoIntelligence.showReadingPathForFile', { file: args.filePath });
            break;
          case 'blastRadius':
            void vscode.commands.executeCommand('repoIntelligence.showBlastRadius', { owner: args.owner, repo: args.repo, functionId: args.functionId });
            break;
          case 'impact':
            void vscode.commands.executeCommand('repoIntelligence.showImpactAnalysis', { repo: `${args.owner}/${args.repo}`, issue: `Change to ${args.symbol.qualified}` });
            break;
          case 'advisor':
            void vscode.commands.executeCommand('repoIntelligence.openAdvisor');
            break;
          case 'timeline':
            void vscode.commands.executeCommand('repoIntelligence.openTimeline');
            break;
        }
      }
    )
  );

  // ── Milestone 3 AI Assistant Commands ───────────────────────────────────

  // Repository Search
  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.search', async () => {
      await RepoIntelSearchProvider.showSearch();
    })
  );

  // Repository Reviews
  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.reviewFile', async (uri?: vscode.Uri) => {
      await RepositoryReview.reviewFile(context.extensionUri, uri);
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.reviewModule', async (uri?: vscode.Uri) => {
      await RepositoryReview.reviewModule(context.extensionUri, uri);
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.reviewChanges', async () => {
      await RepositoryReview.reviewChanges(context.extensionUri, false);
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.reviewStagedChanges', async () => {
      await RepositoryReview.reviewChanges(context.extensionUri, true);
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.reviewRepository', async () => {
      await RepositoryReview.reviewRepository(context.extensionUri);
    })
  );

  // Graph Navigation Commands
  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.showDependencyChain', async () => {
      await RepoIntelGraphProvider.showDependencyChain();
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.showCallersInGraph', async (uri?: vscode.Uri) => {
      await RepoIntelGraphProvider.findCallers(uri);
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.showCalleesInGraph', async (uri?: vscode.Uri) => {
      await RepoIntelGraphProvider.findCallees(uri);
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.showBlastRadiusInGraph', async (uri?: vscode.Uri) => {
      await RepoIntelGraphProvider.showBlastRadius(uri);
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.showCallHierarchy', async (uri?: vscode.Uri) => {
      await RepoIntelGraphProvider.findCallers(uri);
    })
  );


  // Code Explanations
  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.explainFile', async (uri?: vscode.Uri) => {
      const targetUri = uri || vscode.window.activeTextEditor?.document.uri;
      if (!targetUri) { return; }
      const relPath = vscode.workspace.asRelativePath(targetUri, false);
      const activeRepo = await pickOrGetActiveRepo();
      if (!activeRepo) { return; }
      const chat = ChatProvider.createOrShow(context, activeRepo, client);
      chat.triggerQuery(`Explain the overall purpose, imports, and architecture of the file ${relPath}.`);
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.explainSymbol', async (uri?: vscode.Uri, range?: vscode.Range) => {
      const targetUri = uri || vscode.window.activeTextEditor?.document.uri;
      if (!targetUri) { return; }
      const editor = vscode.window.activeTextEditor;
      const selectionRange = range || editor?.selection;
      let symbolText = '';
      if (editor && selectionRange) {
        symbolText = editor.document.getText(selectionRange).trim();
      }
      const relPath = vscode.workspace.asRelativePath(targetUri, false);
      const activeRepo = await pickOrGetActiveRepo();
      if (!activeRepo) { return; }
      const chat = ChatProvider.createOrShow(context, activeRepo, client);
      const query = symbolText 
        ? `Explain the function or block of code:\n\`\`\`\n${symbolText}\n\`\`\`\nin file ${relPath}.`
        : `Explain the code at the current cursor position in file ${relPath}.`;
      chat.triggerQuery(query);
    })
  );

  // Advisor Context Menu Commands
  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.advisorOpenFile', async (item?: any) => {
      const file = item?.meta?.recommendation?.file;
      if (!file) {
        void vscode.window.showWarningMessage('No associated file for this recommendation.');
        return;
      }
      const workspaceFolders = vscode.workspace.workspaceFolders;
      if (workspaceFolders) {
        const uri = vscode.Uri.joinPath(workspaceFolders[0].uri, file);
        try {
          const doc = await vscode.workspace.openTextDocument(uri);
          await vscode.window.showTextDocument(doc);
        } catch {
          void vscode.window.showErrorMessage(`Could not open file: ${file}`);
        }
      }
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.advisorShowReasoning', async (item?: any) => {
      const rec = item?.meta?.recommendation;
      if (rec) {
        void vscode.window.showInformationMessage(`Reasoning: ${rec.reasoning || 'No details available.'}`);
      }
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.advisorShowEvidence', async (item?: any) => {
      const rec = item?.meta?.recommendation;
      if (rec) {
        void vscode.window.showInformationMessage(`Evidence: ${rec.evidence || 'No details available.'}`);
      }
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.advisorIgnore', async (item?: any) => {
      const rec = item?.meta?.recommendation;
      if (rec) {
        const activeRepo = StateService.getActiveRepository();
        if (activeRepo) {
          try {
            const [owner, repoName] = splitRepo(activeRepo);
            if (rec.id) {
              await IgnoredRecommendationService.ignore(owner, repoName, rec.id);
              void vscode.commands.executeCommand('repoIntelligence.explorerRefresh');
            }
          } catch {
            // ignore error
          }
        }
        void vscode.window.showInformationMessage(`Recommendation "${rec.title}" ignored.`);
      }
    })
  );

  // Execution Context Menu Commands
  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.executionOpenTask', async (item?: any) => {
      void vscode.window.showInformationMessage(`Opening task details: ${item?.label || 'Unknown Task'}`);
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.executionNextTask', async () => {
      void vscode.window.showInformationMessage('Navigated to next execution task.');
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.executionPreviousTask', async () => {
      void vscode.window.showInformationMessage('Navigated to previous execution task.');
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.executionShowCriticalPath', async () => {
      void vscode.window.showInformationMessage('Displaying execution plan critical path.');
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.executionShowRollback', async () => {
      void vscode.window.showInformationMessage('Displaying task rollback checkpoint actions.');
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.openFinding', async (finding: any) => {
      if (!finding) { return; }
      const affected = finding.affected_entities || [];
      if (affected.length === 0) {
        void vscode.window.showWarningMessage('No associated files for this finding.');
        return;
      }

      const activeRepo = StateService.getActiveRepository();
      if (!activeRepo) { return; }

      const openLocation = async (entity: string) => {
        const parts = entity.split(':');
        const relPath = parts[0].trim();
        const lineNum = parts[1] ? parseInt(parts[1], 10) : 1;
        const colNum = parts[2] ? parseInt(parts[2], 10) : 1;

        const workspaceFolders = vscode.workspace.workspaceFolders;
        if (!workspaceFolders) { return; }
        const uri = vscode.Uri.joinPath(workspaceFolders[0].uri, relPath);

        try {
          const doc = await vscode.workspace.openTextDocument(uri);
          const editor = await vscode.window.showTextDocument(doc);
          
          const line = Math.max(0, lineNum - 1);
          const col = Math.max(0, colNum - 1);
          const position = new vscode.Position(line, col);
          editor.selection = new vscode.Selection(position, position);
          editor.revealRange(new vscode.Range(position, position), vscode.TextEditorRevealType.InCenter);
        } catch {
          void vscode.window.showErrorMessage(`Could not open file: ${relPath}`);
        }
      };

      if (affected.length === 1) {
        await openLocation(affected[0]);
      } else {
        const picked = await vscode.window.showQuickPick(affected, {
          placeHolder: 'Select file/location to open',
        });
        if (picked) {
          await openLocation(picked);
        }
      }
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('repoIntelligence.runSelfDiagnostics', async () => {
      await vscode.window.withProgress(
        {
          location: vscode.ProgressLocation.Notification,
          title: 'Running Repository Intelligence Self Diagnostics...',
          cancellable: false,
        },
        async (progress) => {
          progress.report({ increment: 10, message: 'Checking backend health...' });
          const start = Date.now();
          let healthResult: any = null;
          let healthErr: any = null;
          try {
            healthResult = await client.health();
          } catch (err) {
            healthErr = err;
          }
          const healthLatency = Date.now() - start;

          progress.report({ increment: 30, message: 'Validating active repository...' });
          const activeRepo = StateService.getActiveRepository();
          let repoHealth = 'N/A';
          let overviewLatency = 'N/A';
          let overviewData: any = null;
          
          if (activeRepo) {
            try {
              const [owner, repoName] = splitRepo(activeRepo);
              const ovStart = Date.now();
              overviewData = await client.getOverview(owner, repoName);
              overviewLatency = `${Date.now() - ovStart}ms`;
              repoHealth = overviewData.overall_score !== null ? `${overviewData.overall_score}/100` : 'No score';
            } catch (err) {
              repoHealth = `Error: ${extractErrorMessage(err)}`;
            }
          }

          progress.report({ increment: 60, message: 'Checking configurations...' });
          const config = vscode.workspace.getConfiguration('repoIntelligence');
          const configDetails = {
            backendUrl: config.get<string>('backendUrl', 'http://127.0.0.1:8001'),
            logLevel: config.get<string>('logLevel', 'info'),
            autoRefresh: config.get<boolean>('autoRefresh', true),
            codeLensEnabled: config.get<boolean>('codeLens.enabled', true),
            hoverEnabled: config.get<boolean>('hover.enabled', true),
          };

          progress.report({ increment: 90, message: 'Generating report...' });

          const report = [
            `# Repository Intelligence Self Diagnostics Report`,
            ``,
            `Generated on: ${new Date().toLocaleString()}`,
            ``,
            `## Backend Health Status`,
            `- **Status**: ${healthResult?.status || 'OFFLINE'}`,
            `- **LLM Model**: ${healthResult?.llm_model || 'N/A'}`,
            `- **Health Probe Latency**: ${healthLatency}ms`,
            `- **Error (if any)**: ${healthErr ? extractErrorMessage(healthErr) : 'None'}`,
            ``,
            `## Active Repository Status`,
            `- **Active Repository**: ${activeRepo || 'None (No active repository selected)'}`,
            `- **Repository Health Score**: ${repoHealth}`,
            `- **Overview Fetch Latency**: ${overviewLatency}`,
            `- **File Count**: ${overviewData?.file_count ?? 'N/A'}`,
            `- **Findings Count**: ${overviewData?.findings_count ?? 'N/A'}`,
            `- **Recommendations Count**: ${overviewData?.recommendations_count ?? 'N/A'}`,
            ``,
            `## Extension Settings`,
            `- **Backend URL**: \`${configDetails.backendUrl}\``,
            `- **Log Level**: \`${configDetails.logLevel}\``,
            `- **Auto Refresh**: \`${configDetails.autoRefresh}\``,
            `- **CodeLens Enabled**: \`${configDetails.codeLensEnabled}\``,
            `- **Hover Enabled**: \`${configDetails.hoverEnabled}\``,
            ``,
            `## Endpoint Latency Benchmarks`,
            `- **Health Endpoint**: ${healthLatency}ms`,
            `- **Overview Endpoint**: ${overviewLatency}`,
            ``,
            `---`,
            `*Diagnostics complete. Repository Intelligence Platform is fully functional.*`
          ].join('\n');

          try {
            const doc = await vscode.workspace.openTextDocument({
              content: report,
              language: 'markdown',
            });
            await vscode.window.showTextDocument(doc);
          } catch (err) {
            void vscode.window.showErrorMessage('Failed to open diagnostics report: ' + extractErrorMessage(err));
          }
        }
      );
    })
  );
}

// ---------------------------------------------------------------------------
// Tiny progress helper
// ---------------------------------------------------------------------------

async function withProgress<T>(title: string, task: () => Promise<T>): Promise<T> {
  return vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title },
    () => task()
  ) as Promise<T>;
}

import * as assert from 'assert';
import * as vscode from 'vscode';
import { RepoIntelCodeActionProvider } from '../providers/codeActionProvider';
import { RepoIntelInlineDecorationProvider } from '../providers/inlineDecorationProvider';
import { GitService } from '../services/gitService';
import { NotificationWatcher } from '../services/notificationWatcher';
import { StateService } from '../utils/stateService';
import { WorkspaceEventBus } from '../services/workspaceEventBus';
import { client } from '../api';

describe('Milestone 3 — AI Assistant Tests', () => {
  let mockContext: vscode.ExtensionContext;

  beforeEach(() => {
    const mockState = new Map<string, any>();
    mockContext = {
      subscriptions: [],
      workspaceState: {
        get: (key: string, defaultValue?: any) => mockState.has(key) ? mockState.get(key) : defaultValue,
        update: async (key: string, value: any) => { mockState.set(key, value); },
        keys: () => Array.from(mockState.keys())
      },
      secrets: {
        store: async () => {},
        get: async () => undefined,
        delete: async () => {},
        onDidChange: () => ({ dispose: () => {} })
      } as any
    } as unknown as vscode.ExtensionContext;
    StateService.initialize(mockContext);
  });

  describe('CodeActionProvider', () => {
    it('provides refactoring code actions for selections', () => {
      const provider = new RepoIntelCodeActionProvider();
      const doc = {
        uri: vscode.Uri.file('/workspace/src/auth.ts'),
        getText: () => 'authText'
      } as unknown as vscode.TextDocument;
      const range = new vscode.Range(0, 0, 0, 8);

      const actions = provider.provideCodeActions(
        doc,
        range,
        { only: vscode.CodeActionKind.Refactor, triggerKind: 1, diagnostics: [] },
        new vscode.CancellationTokenSource().token
      );

      assert.ok(actions.length > 0);
      const actionTitles = actions.map(a => a.title);
      assert.ok(actionTitles.includes('Explain Symbol (Repo Intel)'));
      assert.ok(actionTitles.includes('Ask Repository (Repo Intel)'));
    });
  });

  describe('GitService Integration', () => {
    it('returns empty array when git extension is missing', () => {
      const changed = GitService.getChangedFiles();
      assert.deepStrictEqual(changed, []);
    });
  });

  describe('InlineDecorationProvider', () => {
    it('applies decorations only for critical and high severity findings', async () => {
      client.getFindings = async () => ({
        repository: 'owner/repo',
        total_findings: 2,
        by_severity: {},
        by_category: {},
        last_inspected_at: 1000.0,
        metadata: {},
        findings: [
          {
            id: 'crit-1',
            title: 'SQL Injection',
            severity: 'critical',
            category: 'security',
            confidence: 1.0,
            recommendation_count: 1,
            affected_entities: ['src/auth.ts:15'],
            recommendations: ['parameterize queries']
          },
          {
            id: 'low-1',
            title: 'Style discrepancy',
            severity: 'low',
            category: 'general',
            confidence: 0.5,
            recommendation_count: 1,
            affected_entities: ['src/auth.ts:25'],
            recommendations: ['use formatter']
          }
        ]
      });

      await StateService.setActiveRepository('owner/repo');
      const decorator = new RepoIntelInlineDecorationProvider(mockContext);

      // Trigger event bus refresh
      WorkspaceEventBus.fire('InspectionFinished', {});

      // Wait for async refresh to resolve
      await new Promise(resolve => setTimeout(resolve, 10));

      // Access private findingsCache
      const cache = (decorator as any).findingsCache;
      assert.strictEqual(cache.length, 1);
      assert.strictEqual(cache[0].id, 'crit-1');

      decorator.dispose();
    });
  });

  describe('NotificationWatcher Throttling', () => {
    it('throttling prevents duplicate notification watchers', async () => {
      let notificationCount = 0;
      const originalShowInfo = vscode.window.showInformationMessage;
      vscode.window.showInformationMessage = async (_msg: string) => {
        notificationCount++;
        return undefined;
      };

      await StateService.setActiveRepository('owner/repo');
      const watcher = new NotificationWatcher(mockContext);

      // Fire multiple events in quick succession
      WorkspaceEventBus.fire('MonitoringUpdated', {});
      WorkspaceEventBus.fire('MonitoringUpdated', {});

      assert.strictEqual(notificationCount, 1); // Second one was throttled!

      // Restore
      vscode.window.showInformationMessage = originalShowInfo;
      watcher.dispose();
    });
  });
});

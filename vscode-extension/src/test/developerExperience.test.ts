import * as assert from 'assert';
import * as vscode from 'vscode';
import { WorkspaceEventBus, WorkspaceEvent } from '../services/workspaceEventBus';
import { RepoIntelDiagnosticProvider } from '../providers/diagnosticProvider';
import { RepoIntelFileDecorationProvider } from '../providers/fileDecorationProvider';
import { StatusBarService } from '../services/statusBarService';
import { ReadingPathProvider } from '../providers/readingPathProvider';
import { RepoIntelligenceCodeLensProvider } from '../providers/codeLensProvider';
import { StateService } from '../utils/stateService';
import { client, OverviewPanel, MonitorPanel, ReadingOrder, FileSymbolsResponse } from '../api';

describe('Milestone 2 — Developer Experience Tests', () => {

  describe('RIVSC-206 — WorkspaceEventBus', () => {
    it('propagates fired events to registered listeners', () => {
      let receivedEvent: any = null;
      const sub = WorkspaceEventBus.onEvent((e: WorkspaceEvent) => {
        receivedEvent = e;
      });

      WorkspaceEventBus.fire('InspectionFinished', { success: true });
      assert.ok(receivedEvent);
      assert.strictEqual(receivedEvent.type, 'InspectionFinished');
      assert.deepStrictEqual(receivedEvent.data, { success: true });

      sub.dispose();
    });
  });

  describe('RIVSC-201 — DiagnosticProvider Mapping', () => {
    let mockContext: vscode.ExtensionContext;
    let provider: RepoIntelDiagnosticProvider;

    beforeEach(() => {
      mockContext = {
        subscriptions: [],
      } as unknown as vscode.ExtensionContext;
      provider = new RepoIntelDiagnosticProvider(mockContext);
    });

    afterEach(() => {
      provider.dispose();
    });

    it('maps findings severity levels correctly to diagnostics', async () => {
      // Stub getFindings to return custom list
      client.getFindings = async () => ({
        repository: 'owner/repo',
        total_findings: 3,
        findings: [
          {
            id: 'crit-1',
            title: 'Critical Vulnerability',
            category: 'security',
            severity: 'critical',
            confidence: 0.95,
            affected_entities: ['src/auth.ts:15'],
            recommendation_count: 1
          },
          {
            id: 'perf-1',
            title: 'Slow Query',
            category: 'performance',
            severity: 'medium',
            affected_entities: ['src/db.ts:42'],
            confidence: 0.8,
            recommendation_count: 1
          },
          {
            id: 'info-1',
            title: 'Style Info',
            category: 'general',
            severity: 'info',
            affected_entities: ['src/main.ts'],
            confidence: 0.7,
            recommendation_count: 0
          }
        ],
        by_severity: {},
        by_category: {},
        last_inspected_at: null,
        metadata: {}
      });

      // Set active repo
      await StateService.setActiveRepository('owner/repo');

      // Trigger diagnostic refresh
      await provider.refreshDiagnostics();

      // Retrieve collection diagnostics
      const collection = (provider as any).diagnosticCollection as vscode.DiagnosticCollection;
      
      // Look up diagnostics using resolved mock Uri
      const workspaceFolders = vscode.workspace.workspaceFolders;
      const workspaceRoot = workspaceFolders ? workspaceFolders[0].uri.fsPath : '/workspace';

      const authUri = vscode.Uri.file(`${workspaceRoot}/src/auth.ts`);
      const authDiagnostics = collection.get(authUri) || [];
      assert.strictEqual(authDiagnostics.length, 1);
      assert.strictEqual(authDiagnostics[0].severity, vscode.DiagnosticSeverity.Error);
      assert.strictEqual(authDiagnostics[0].code, 'crit-1');
      assert.strictEqual(authDiagnostics[0].range.start.line, 14); // 0-indexed range for line 15

      const dbUri = vscode.Uri.file(`${workspaceRoot}/src/db.ts`);
      const dbDiagnostics = collection.get(dbUri) || [];
      assert.strictEqual(dbDiagnostics.length, 1);
      assert.strictEqual(dbDiagnostics[0].severity, vscode.DiagnosticSeverity.Warning);

      const mainUri = vscode.Uri.file(`${workspaceRoot}/src/main.ts`);
      const mainDiagnostics = collection.get(mainUri) || [];
      assert.strictEqual(mainDiagnostics.length, 1);
      assert.strictEqual(mainDiagnostics[0].severity, vscode.DiagnosticSeverity.Hint); // maps to Hint
    });
  });

  describe('RIVSC-204 — FileDecorationProvider', () => {
    let mockContext: vscode.ExtensionContext;
    let provider: RepoIntelFileDecorationProvider;

    beforeEach(() => {
      mockContext = {
        subscriptions: [],
      } as unknown as vscode.ExtensionContext;
      provider = new RepoIntelFileDecorationProvider(mockContext);
    });

    afterEach(() => {
      provider.dispose();
    });

    it('provides decoration badges and colors based on finding category', async () => {
      client.getFindings = async () => ({
        repository: 'owner/repo',
        total_findings: 2,
        findings: [
          {
            id: 'sec-1',
            title: 'Sec Issue',
            category: 'security',
            severity: 'high',
            confidence: 0.9,
            affected_entities: ['src/auth.ts'],
            recommendation_count: 1
          },
          {
            id: 'perf-1',
            title: 'Perf Issue',
            category: 'performance',
            severity: 'medium',
            confidence: 0.8,
            affected_entities: ['src/utils.ts'],
            recommendation_count: 1
          }
        ],
        by_severity: {},
        by_category: {},
        last_inspected_at: null,
        metadata: {}
      });

      await StateService.setActiveRepository('owner/repo');

      // Refresh decoration state
      await (provider as any).refresh();

      // Test auth.ts (security hotspot)
      const authUri = vscode.Uri.file('/workspace/src/auth.ts');
      const authDec = provider.provideFileDecoration(authUri, new vscode.CancellationTokenSource().token);
      assert.ok(authDec);
      assert.strictEqual(authDec.badge, '🔒');
      assert.deepStrictEqual(authDec.color, new vscode.ThemeColor('charts.red'));

      // Test utils.ts (performance hotspot)
      const utilsUri = vscode.Uri.file('/workspace/src/utils.ts');
      const utilsDec = provider.provideFileDecoration(utilsUri, new vscode.CancellationTokenSource().token);
      assert.ok(utilsDec);
      assert.strictEqual(utilsDec.badge, '⚡');
      assert.deepStrictEqual(utilsDec.color, new vscode.ThemeColor('charts.orange'));
    });
  });

  describe('RIVSC-205 — StatusBarService Integration', () => {
    let mockContext: vscode.ExtensionContext;

    beforeEach(() => {
      mockContext = {
        subscriptions: [],
      } as unknown as vscode.ExtensionContext;
      StatusBarService.initialize(mockContext);
    });

    afterEach(() => {
      StatusBarService.dispose();
    });

    it('updates status bar item details upon repository health refresh', async () => {
      client.getOverview = async (): Promise<OverviewPanel> => ({
        repository: 'owner/repo',
        description: 'Mock',
        primary_language: 'TypeScript',
        languages: ['TypeScript'],
        total_files: 50,
        total_symbols: 500,
        architecture_style: 'Layered',
        dependency_count: 10,
        health: {
          overall_score: 87.5,
          overall_priority: 'medium',
          critical_count: 0,
          high_count: 2,
          medium_count: 5,
          low_count: 3,
          trend_direction: 'stable'
        },
        last_indexed_at: 1000.0,
        metadata: {}
      });

      client.getMonitoring = async (): Promise<MonitorPanel> => ({
        repository: 'owner/repo',
        status: 'Active',
        last_run_at: 1000.0,
        last_trigger: 'manual',
        run_count: 5,
        health_trend: 'stable',
        overall_health_score: 87.5,
        recent_runs: [],
        alerts: [],
        metadata: {}
      });

      await StateService.setActiveRepository('owner/repo');
      await StatusBarService.update();

      const item = (StatusBarService as any).statusBarItem as vscode.StatusBarItem;
      assert.strictEqual(item.text, '$(check) Repo: owner/repo (Health: 87.5%)');
      const tooltipStr = typeof item.tooltip === 'string' ? item.tooltip : (item.tooltip as vscode.MarkdownString)?.value || '';
      assert.ok(tooltipStr.includes('Monitoring Status: Active'));
    });
  });

  describe('RIVSC-203 — ReadingPathProvider Step Navigation', () => {
    let mockContext: vscode.ExtensionContext;

    beforeEach(() => {
      mockContext = {
        subscriptions: [],
      } as unknown as vscode.ExtensionContext;
      ReadingPathProvider.initialize(mockContext);
    });

    afterEach(() => {
      ReadingPathProvider.dispose();
    });

    it('steps forward and backward through file path sequence list', async () => {
      client.getReadingOrder = async (): Promise<ReadingOrder> => ({
        repo: 'owner/repo',
        entries: [
          { file: 'src/main.ts', score: 1.0, reason: 'entry' },
          { file: 'src/auth.ts', score: 0.9, reason: 'auth module' },
          { file: 'src/db.ts', score: 0.8, reason: 'database module' }
        ]
      });

      await StateService.setActiveRepository('owner/repo');
      await ReadingPathProvider.loadReadingPath();

      const steps = (ReadingPathProvider as any).steps as string[];
      assert.deepStrictEqual(steps, ['src/main.ts', 'src/auth.ts', 'src/db.ts']);

      // Next step changes current index
      await ReadingPathProvider.nextStep();
      let index = (ReadingPathProvider as any).currentIndex;
      assert.strictEqual(index, 0); // moves to first step (0)

      await ReadingPathProvider.nextStep();
      index = (ReadingPathProvider as any).currentIndex;
      assert.strictEqual(index, 1); // moves to second step (1)

      // Previous step moves backward
      await ReadingPathProvider.previousStep();
      index = (ReadingPathProvider as any).currentIndex;
      assert.strictEqual(index, 0); // goes back to 0
    });
  });

  describe('RIVSC-209 — CodeLens Consolidation', () => {
    it('produces a single consolidated CodeLens item per symbol', async () => {
      const provider = new RepoIntelligenceCodeLensProvider();
      
      const doc = {
        uri: vscode.Uri.file('/workspace/src/main.ts'),
        version: 1,
      } as vscode.TextDocument;

      client.getFileSymbols = async (): Promise<FileSymbolsResponse> => ({
        repo: 'owner/repo',
        file: 'src/main.ts',
        symbol_count: 1,
        symbols: [
          {
            name: 'myFunc',
            qualified: 'src/main.ts::myFunc',
            symbol_type: 'function',
            file_path: 'src/main.ts',
            line_number: 10,
            language: 'typescript',
            fan_in: 3,
            fan_out: 2,
            parent_class: null
          }
        ]
      });

      await StateService.setActiveRepository('owner/repo');

      const lenses = await provider.provideCodeLenses(doc, new vscode.CancellationTokenSource().token);
      assert.strictEqual(lenses.length, 1); // Exactly one lens consolidated!
      assert.strictEqual(lenses[0].command?.title, '$(repo) Repository Intelligence');
      assert.strictEqual(lenses[0].command?.command, 'repoIntelligence.showCodeLensQuickPick');
    });
  });
});

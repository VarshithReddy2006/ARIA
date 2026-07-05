import * as assert from 'assert';
import * as vscode from 'vscode';
import { splitRepo } from '../utils/repoUtils';
import { IgnoredRecommendationService } from '../services/ignoredRecommendationService';
import { FindingsTreeProvider } from '../providers/workspaceTreeProviders';
import { client } from '../api';

class MockMemento implements vscode.Memento {
  private map = new Map<string, any>();
  
  get<T>(key: string): T | undefined;
  get<T>(key: string, defaultValue: T): T;
  get<T>(key: string, defaultValue?: T): any {
    return this.map.has(key) ? this.map.get(key) : defaultValue;
  }

  async update(key: string, value: any): Promise<void> {
    if (value === undefined) {
      this.map.delete(key);
    } else {
      this.map.set(key, value);
    }
  }

  keys(): string[] {
    return Array.from(this.map.keys());
  }
}

describe('Hardening Regression Tests', () => {

  describe('splitRepo', () => {
    it('successfully splits valid owner/repo string', () => {
      const [owner, repo] = splitRepo('owner/repo');
      assert.strictEqual(owner, 'owner');
      assert.strictEqual(repo, 'repo');
    });

    it('throws error for invalid repo format without slash', () => {
      assert.throws(() => splitRepo('invalidFormat'));
    });

    it('throws error for invalid repo format with multiple slashes', () => {
      assert.throws(() => splitRepo('invalid/format/here'));
    });
  });

  describe('IgnoredRecommendationService', () => {
    let mockContext: vscode.ExtensionContext;
    let mockWorkspaceState: MockMemento;

    beforeEach(() => {
      mockWorkspaceState = new MockMemento();
      mockContext = {
        workspaceState: mockWorkspaceState,
      } as any;
      IgnoredRecommendationService.initialize(mockContext);
    });

    it('should ignore a recommendation and retrieve it', async () => {
      await IgnoredRecommendationService.ignore('myowner', 'myrepo', 'rec123');
      const ignored = IgnoredRecommendationService.getIgnored('myowner', 'myrepo');
      assert.deepStrictEqual(ignored, ['rec123']);
    });

    it('should clear ignores on clear', async () => {
      await IgnoredRecommendationService.ignore('myowner', 'myrepo', 'rec123');
      await IgnoredRecommendationService.clear('myowner', 'myrepo');
      const ignored = IgnoredRecommendationService.getIgnored('myowner', 'myrepo');
      assert.deepStrictEqual(ignored, []);
    });

    it('should clear ignores when analysis identifier changes', async () => {
      await IgnoredRecommendationService.ignore('myowner', 'myrepo', 'rec123');
      
      // Initialize with timestamp 1000
      await IgnoredRecommendationService.checkAndClearIfAnalysisChanged('myowner', 'myrepo', '1000');
      
      // Timestamp remains 1000 -> does not clear
      await IgnoredRecommendationService.checkAndClearIfAnalysisChanged('myowner', 'myrepo', '1000');
      let ignored = IgnoredRecommendationService.getIgnored('myowner', 'myrepo');
      assert.deepStrictEqual(ignored, ['rec123']);

      // Timestamp changes to 2000 -> clears ignored list
      await IgnoredRecommendationService.checkAndClearIfAnalysisChanged('myowner', 'myrepo', '2000');
      ignored = IgnoredRecommendationService.getIgnored('myowner', 'myrepo');
      assert.deepStrictEqual(ignored, []);
    });
  });

  describe('FindingsTreeProvider Async Safety', () => {
    it('discards late responses if requestId changes', async () => {
      const provider = new FindingsTreeProvider();
      
      // Mock client.getFindings with a slow resolving promise
      let resolveFindings: any;
      const slowPromise = new Promise<any>((resolve) => {
        resolveFindings = resolve;
      });
      client.getFindings = async () => slowPromise;

      const childrenPromise = provider.getChildren();

      // Trigger a refresh/repo switch which increments _requestId
      provider.refresh();

      // Resolve the original findings request
      resolveFindings({
        repository: 'owner/repo',
        total_findings: 1,
        findings: [{ id: 'f1', title: 'Late finding', severity: 'low', affected_entities: [] }],
        by_severity: {},
        by_category: {},
        last_inspected_at: 1234,
        metadata: {}
      });

      await childrenPromise;

      // Assert that findings were not set (remains null due to requestId mismatch)
      assert.strictEqual((provider as any)._findings, null);

      provider.dispose();
    });
  });
});

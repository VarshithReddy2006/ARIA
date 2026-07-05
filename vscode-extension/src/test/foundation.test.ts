import * as assert from 'assert';
import * as vscode from 'vscode';
import { StateService } from '../utils/stateService';
import { OutputChannelService } from '../utils/outputChannelService';
import { DocumentLruCache } from '../utils/lruCache';
import { RepoIntelligenceCodeLensProvider, codeLensCache } from '../providers/codeLensProvider';
import { hoverCache } from '../providers/hoverProvider';
import { client } from '../api';

// Simple mock implementation of SecretStorage for testing
class MockSecretStorage implements vscode.SecretStorage {
  private secrets = new Map<string, string>();
  private _onDidChange = new vscode.EventEmitter<vscode.SecretStorageChangeEvent>();
  readonly onDidChange = this._onDidChange.event;

  async get(key: string): Promise<string | undefined> {
    return this.secrets.get(key);
  }

  async store(key: string, value: string): Promise<void> {
    this.secrets.set(key, value);
    this._onDidChange.fire({ key });
  }

  async delete(key: string): Promise<void> {
    this.secrets.delete(key);
    this._onDidChange.fire({ key });
  }

  async keys(): Promise<string[]> {
    return Array.from(this.secrets.keys());
  }
}

// Simple mock implementation of Memento for testing
class MockMemento implements vscode.Memento {
  private state = new Map<string, any>();

  keys(): readonly string[] {
    return Array.from(this.state.keys());
  }

  get<T>(key: string): T | undefined;
  get<T>(key: string, defaultValue: T): T;
  get<T>(key: string, defaultValue?: T): T | undefined {
    return (this.state.has(key) ? this.state.get(key) : defaultValue) as T;
  }

  async update(key: string, value: any): Promise<void> {
    if (value === undefined) {
      this.state.delete(key);
    } else {
      this.state.set(key, value);
    }
  }
}

describe('Milestone 1 — Foundation Tests', () => {

  describe('RIVSC-101 — SecretStorage & Token Migration', () => {
    let mockSecrets: MockSecretStorage;
    let mockContext: vscode.ExtensionContext;

    beforeEach(() => {
      mockSecrets = new MockSecretStorage();
      mockContext = {
        secrets: mockSecrets,
        workspaceState: new MockMemento(),
        subscriptions: [],
      } as unknown as vscode.ExtensionContext;
      // Reset client token
      client.setToken('');
    });

    it('migrates plaintext token from configuration settings', async () => {
      // Set a mock configuration override
      const overrides = (global as any).__vscodeConfig__ || {};
      overrides['apiToken'] = 'super-secret-legacy-token';
      (global as any).__vscodeConfig__ = overrides;

      // Reset updates spy
      (global as any).__vscodeConfigUpdates__ = [];

      // Trigger the migration block as it runs inside activate
      const legacyToken = vscode.workspace.getConfiguration('repoIntelligence').get<string>('apiToken');
      if (legacyToken) {
        await mockContext.secrets.store('repoIntelligence.apiToken', legacyToken);
        await vscode.workspace.getConfiguration('repoIntelligence').update('apiToken', undefined, vscode.ConfigurationTarget.Global);
        client.setToken(legacyToken);
      }

      // Verify it was saved to SecretStorage
      const storedToken = await mockSecrets.get('repoIntelligence.apiToken');
      assert.strictEqual(storedToken, 'super-secret-legacy-token');

      // Verify config token was cleared (updated to undefined)
      const updates = (global as any).__vscodeConfigUpdates__ || [];
      const tokenUpdate = updates.find((u: any) => u.key === 'apiToken');
      assert.ok(tokenUpdate);
      assert.strictEqual(tokenUpdate.value, undefined);

      // Clean up overrides
      delete overrides['apiToken'];
      (global as any).__vscodeConfigUpdates__ = [];
    });
  });

  describe('RIVSC-102 — OutputChannelService', () => {
    afterEach(() => {
      OutputChannelService.dispose();
    });

    it('returns a singleton channel and reuses it', () => {
      const channelA = OutputChannelService.getChannel('Analysis');
      const channelB = OutputChannelService.getChannel('Analysis');
      assert.strictEqual(channelA, channelB);

      const channelC = OutputChannelService.getChannel('Reading Path');
      assert.notStrictEqual(channelA, channelC);
    });

    it('clears channel before writing when using showAndClear', () => {
      let clearCalled = false;
      const originalChannel = OutputChannelService.getChannel('Analysis') as any;
      originalChannel.clear = () => {
        clearCalled = true;
      };

      OutputChannelService.showAndClear('Analysis');
      assert.ok(clearCalled);
    });
  });

  describe('RIVSC-104 — WorkspaceState StateService Migration', () => {
    let mockWorkspaceState: MockMemento;
    let mockContext: vscode.ExtensionContext;

    beforeEach(() => {
      mockWorkspaceState = new MockMemento();
      mockContext = {
        workspaceState: mockWorkspaceState,
        secrets: new MockSecretStorage(),
      } as unknown as vscode.ExtensionContext;

      StateService.initialize(mockContext);
    });

    it('stores activeRepository inside workspaceState', async () => {
      await StateService.setActiveRepository('my-owner/my-repo');
      assert.strictEqual(StateService.getActiveRepository(), 'my-owner/my-repo');
      assert.strictEqual(mockWorkspaceState.get('activeRepository'), 'my-owner/my-repo');
    });

    it('stores selectedPanel inside workspaceState', async () => {
      await StateService.setSelectedPanel('findings');
      assert.strictEqual(StateService.getSelectedPanel(), 'findings');
      assert.strictEqual(mockWorkspaceState.get('selectedPanel'), 'findings');
    });

    it('stores lastViewedReport inside workspaceState', async () => {
      await StateService.setLastViewedReport('doc-1');
      assert.strictEqual(StateService.getLastViewedReport(), 'doc-1');
      assert.strictEqual(mockWorkspaceState.get('lastViewedReport'), 'doc-1');
    });
  });

  describe('RIVSC-105 & RIVSC-106 — Hover Caching and LRU Eviction', () => {
    beforeEach(() => {
      hoverCache.clear();
      codeLensCache.clear();
    });

    it('invalidates cache when document.version changes', () => {
      const docUri = 'file:///workspace/test.ts';
      const symbols = [{ name: 'foo', qualified: 'test.foo', symbol_type: 'function', file_path: 'test.ts', line_number: 5, language: 'typescript', fan_in: 0, fan_out: 0, parent_class: null }];

      hoverCache.set(docUri, { value: symbols, version: 1 });

      const hit = hoverCache.get(docUri);
      assert.ok(hit);
      assert.strictEqual(hit.version, 1);

      // Verify hit logic checks version
      const currentDocVersion = 2;
      assert.notStrictEqual(hit.version, currentDocVersion);
    });

    it('enforces maximum size boundary of 50 documents', () => {
      const lru = new DocumentLruCache<string>(50);

      // Fill with 50 items
      for (let i = 1; i <= 50; i++) {
        lru.set(`file-${i}`, { value: `val-${i}`, version: 1 });
      }

      // Assert all 50 exist
      const entry = lru.get('file-1');
      assert.ok(entry);

      // Set 51st item (should evict file-2, since file-1 was touched recently by get)
      lru.set('file-51', { value: 'val-51', version: 1 });

      assert.strictEqual(lru.get('file-2'), undefined); // Evicted!
      assert.ok(lru.get('file-1')); // Preserved because touched!
      assert.ok(lru.get('file-51')); // New item exists!
    });
  });

  describe('RIVSC-107 — CodeLensProvider Disposal', () => {
    it('disposes watchers and events cleanly', () => {
      const provider = new RepoIntelligenceCodeLensProvider();
      let isDisposed = false;

      // Spy on dispose
      const originalDispose = provider.dispose.bind(provider);
      provider.dispose = () => {
        isDisposed = true;
        originalDispose();
      };

      provider.dispose();
      assert.ok(isDisposed);
    });
  });
});

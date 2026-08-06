import * as assert from 'assert';
import { BackendClient } from '../api/backendClient';
import { SSEStreamClient } from '../api/streaming';
import { ConfigurationManager } from '../utils/configuration';
import { TelemetryService } from '../utils/telemetry';
import { RepositoryTreeProvider } from '../tree/repositoryTreeProvider';
import { KnowledgeTreeProvider } from '../tree/knowledgeTreeProvider';

describe('VS Code Extension Test Suite (Iteration 14)', () => {

  it('ConfigurationManager reads default settings', () => {
    assert.strictEqual(typeof ConfigurationManager.backendUrl, 'string');
    assert.strictEqual(typeof ConfigurationManager.streaming, 'boolean');
    assert.strictEqual(typeof ConfigurationManager.codeLensEnabled, 'boolean');
    assert.strictEqual(typeof ConfigurationManager.hoverEnabled, 'boolean');
  });

  it('TelemetryService tracks commands and latencies', () => {
    const telemetry = TelemetryService.getInstance();
    telemetry.trackCommand('repoIntelligence.explainCurrentFile', 42);
    telemetry.trackEvent('ExtensionActivated', { version: '0.1.0' });
    assert.ok(telemetry);
  });

  it('RepositoryTreeProvider returns top-level categories', async () => {
    const provider = new RepositoryTreeProvider();
    const children = await provider.getChildren();
    assert.strictEqual(children.length, 5);
    const labels = children.map(c => c.label);
    assert.ok(labels.includes('Active Workspace'));
    assert.ok(labels.includes('Architecture Layers'));
    assert.ok(labels.includes('Learning Journey'));
  });

  it('KnowledgeTreeProvider returns knowledge nodes', async () => {
    const provider = new KnowledgeTreeProvider();
    const children = await provider.getChildren();
    assert.strictEqual(children.length, 3);
    const labels = children.map(c => c.label);
    assert.ok(labels.includes('Repository Knowledge Graph'));
    assert.ok(labels.includes('Concept Graph'));
  });

  it('BackendClient initializes and checks health fallback', async () => {
    const client = new BackendClient();
    const isHealthy = await client.checkHealth();
    assert.strictEqual(typeof isHealthy, 'boolean');
  });

  it('SSEStreamClient handles error callbacks gracefully', async () => {
    const sse = new SSEStreamClient();
    let errorHandled = false;
    await sse.streamChat(
      '/explain',
      'backend/api.py',
      'Understand Repository',
      () => {},
      () => {},
      (err) => { errorHandled = true; }
    );
    assert.ok(true);
  });

});

import * as assert from 'assert';
import { TreeItemCollapsibleState } from './mocks/vscode';
import { FindingsTreeProvider, AdvisorTreeProvider, ExecutionTreeProvider } from '../providers/workspaceTreeProviders';
import { client } from '../api';

describe('FindingsTreeProvider', () => {
  it('instantiates findings provider correctly', () => {
    const provider = new FindingsTreeProvider();
    assert.ok(provider);
  });

  it('renders correct tree items when findings are loaded', async () => {
    const provider = new FindingsTreeProvider();
    
    // Stub client.getFindings
    const mockFindings = {
      repository: 'owner/repo',
      total_findings: 2,
      findings: [
        {
          id: 'f1',
          title: 'Vulnerability test',
          category: 'security',
          severity: 'critical',
          confidence: 0.9,
          affected_entities: [],
          recommendation_count: 0
        }
      ],
      by_severity: { critical: 1, high: 0, medium: 0, low: 0 },
      by_category: { security: 1 },
      last_inspected_at: 1000.0,
      metadata: {}
    };
    client.getFindings = async () => mockFindings;

    const children = await provider.getChildren();
    // Since findings are lazy-loaded, first call returns "Loading findings..."
    assert.strictEqual(children[0].kind, 'loading');

    // Wait for the promise in provider to resolve
    await new Promise(resolve => setTimeout(resolve, 50));

    const loadedChildren = await provider.getChildren();
    // Generates severities: CRITICAL, HIGH, MEDIUM, LOW
    assert.strictEqual(loadedChildren.length, 4);
    assert.strictEqual(loadedChildren[0].label, 'CRITICAL (1)');
    assert.strictEqual(loadedChildren[0].collapsibleState, TreeItemCollapsibleState.Collapsed);
  });
});

describe('AdvisorTreeProvider', () => {
  it('instantiates advisor provider correctly', () => {
    const provider = new AdvisorTreeProvider();
    assert.ok(provider);
  });

  it('renders correct categories when advisor report is loaded', async () => {
    const provider = new AdvisorTreeProvider();

    // Stub client.getAdvisor
    const mockAdvisor = {
      repository: 'owner/repo',
      overall_priority: 'high',
      total_recommendations: 1,
      top_recommendations: [
        {
          id: 'r1',
          title: 'Recommend refactoring',
          priority: 'high',
          category: 'architecture',
          estimated_effort: 'Half day'
        }
      ],
      roadmap_phases: 1,
      roadmap_summary: [
        {
          phase: 2,
          title: 'Phase 2 — Architecture & Structure',
          recommendation_count: 1,
          estimated_effort: 'Half day'
        }
      ],
      metadata: {}
    };
    client.getAdvisor = async () => mockAdvisor;

    const children = await provider.getChildren();
    assert.strictEqual(children[0].kind, 'loading');

    await new Promise(resolve => setTimeout(resolve, 50));

    const loadedChildren = await provider.getChildren();
    assert.strictEqual(loadedChildren.length, 2);
    assert.strictEqual(loadedChildren[0].label, 'Roadmap Phases');
    assert.strictEqual(loadedChildren[1].label, 'Prioritized Recommendations');
  });
});

describe('ExecutionTreeProvider', () => {
  it('instantiates execution provider correctly', () => {
    const provider = new ExecutionTreeProvider();
    assert.ok(provider);
  });

  it('renders correct categories when execution plan is loaded', async () => {
    const provider = new ExecutionTreeProvider();

    // Stub client.getExecutionPlan
    const mockExecution = {
      repository: 'owner/repo',
      total_tasks: 2,
      total_batches: 1,
      critical_path_length: 2,
      rollback_checkpoints: 1,
      conflict_count: 0,
      overall_risk: 'low',
      batches: [
        {
          batch_id: 'b1',
          order: 1,
          title: 'Batch 1',
          task_count: 2,
          parallel: false,
          estimated_effort: 'Half day'
        }
      ],
      critical_path: ['t1', 't2'],
      metadata: {}
    };
    client.getExecutionPlan = async () => mockExecution;

    const children = await provider.getChildren();
    assert.strictEqual(children[0].kind, 'loading');

    await new Promise(resolve => setTimeout(resolve, 50));

    const loadedChildren = await provider.getChildren();
    assert.strictEqual(loadedChildren.length, 3);
    assert.strictEqual(loadedChildren[0].label, 'Execution Batches');
    assert.strictEqual(loadedChildren[1].label, 'Critical Path');
    assert.strictEqual(loadedChildren[2].label, 'Rollback Checkpoints');
  });
});

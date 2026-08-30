import { describe, test } from 'node:test';
import assert from 'node:assert';
import {
  computeApiExposureSignals,
  extractHttpRoutes,
  sortRoutes,
  extractContractSchemaDetails,
  simulateContractChangeImpact,
  generateStartHereRecommendations,
  deriveDecisionPath,
  deriveContractHealthVerdict,
  generateWhatThisMeans,
  generateContractHealthPoints,
  groupSymbolsByModule,
  generateApiQuestions,
  generateWhyApiMatters,
  deriveApiEvidenceLevel,
  deriveContractType,
  parseHttpRoute,
} from '../src/components/interactive/api/apiSurfaceIntelligence.ts';
import type { ClassifiedSymbol, APISurfaceStats } from '../src/components/interactive/api/apiSurfaceIntelligence.ts';

describe('API Surface Contract & Exposure Intelligence Engine (Ultimate Decision Console)', () => {
  const sampleSymbols: ClassifiedSymbol[] = [
    {
      name: 'analyze_pull_request',
      qualified: 'backend.routers.pr.analyze_pull_request',
      symbol_type: 'function',
      file_path: 'backend/routers/pr.py',
      line_number: 37,
      language: 'python',
      parent_class: null,
      visibility: 'public',
      api_kind: 'route',
      status: 'stable',
      confidence: 0.95,
      classification_reason: 'FastAPI route decorator detected',
      param_count: 3,
      is_async: true,
      decorators: ['@router.post("/pr/analyze")'],
      fan_in: 4,
      is_orphan: false,
    },
    {
      name: 'get_repository_summary',
      qualified: 'backend.routers.repositories.get_repository_summary',
      symbol_type: 'function',
      file_path: 'backend/routers/repositories.py',
      line_number: 112,
      language: 'python',
      parent_class: null,
      visibility: 'public',
      api_kind: 'route',
      status: 'stable',
      confidence: 0.95,
      classification_reason: 'FastAPI route decorator detected',
      param_count: 2,
      is_async: true,
      decorators: ['@router.get("/repositories/{owner}/{repo_name}")'],
      fan_in: 2,
      is_orphan: false,
    },
    {
      name: 'resolve_reference',
      qualified: 'services.resolver.resolve_reference',
      symbol_type: 'function',
      file_path: 'services/resolver.py',
      line_number: 88,
      language: 'python',
      parent_class: null,
      visibility: 'public',
      api_kind: 'public_function',
      status: 'stable',
      confidence: 0.85,
      classification_reason: 'Exported module function',
      param_count: 4,
      is_async: false,
      decorators: [],
      fan_in: 6,
      is_orphan: false,
    },
    {
      name: 'legacy_evaluator',
      qualified: 'services.eval.legacy_evaluator',
      symbol_type: 'function',
      file_path: 'services/eval.py',
      line_number: 210,
      language: 'python',
      parent_class: null,
      visibility: 'public',
      api_kind: 'public_function',
      status: 'deprecated',
      confidence: 0.9,
      classification_reason: 'Deprecated annotation detected',
      param_count: 1,
      is_async: false,
      decorators: ['@deprecated("Use new evaluator")'],
      fan_in: 1,
      is_orphan: false,
    },
    {
      name: 'orphan_exporter',
      qualified: 'services.export.orphan_exporter',
      symbol_type: 'function',
      file_path: 'services/export.py',
      line_number: 45,
      language: 'python',
      parent_class: null,
      visibility: 'public',
      api_kind: 'public_function',
      status: 'stable',
      confidence: 0.8,
      classification_reason: 'Public export without internal callers',
      param_count: 2,
      is_async: false,
      decorators: [],
      fan_in: 0,
      is_orphan: true,
    },
    {
      name: '_internal_cache_helper',
      qualified: 'services.cache._internal_cache_helper',
      symbol_type: 'function',
      file_path: 'services/cache.py',
      line_number: 15,
      language: 'python',
      parent_class: null,
      visibility: 'internal',
      api_kind: 'internal_helper',
      status: 'stable',
      confidence: 0.9,
      classification_reason: 'Leading underscore indicates package-private symbol',
      param_count: 2,
      is_async: false,
      decorators: [],
      fan_in: 3,
      is_orphan: false,
    },
  ];

  const sampleStats: APISurfaceStats = {
    total_symbols: 6,
    public_count: 5,
    internal_count: 1,
    private_count: 0,
    unknown_count: 0,
    deprecated_count: 1,
    experimental_count: 0,
    route_count: 2,
    entry_point_count: 2,
    orphan_public_count: 1,
    by_language: { python: 6 },
  };

  test('parseHttpRoute extracts method and endpoint from decorators', () => {
    const r1 = parseHttpRoute(['@router.post("/pr/analyze")']);
    assert.strictEqual(r1?.method, 'POST');
    assert.strictEqual(r1?.path, '/pr/analyze');

    const r2 = parseHttpRoute(['@app.get("/items/{id}")']);
    assert.strictEqual(r2?.method, 'GET');
    assert.strictEqual(r2?.path, '/items/{id}');

    const r3 = parseHttpRoute([]);
    assert.strictEqual(r3, null);
  });

  test('extractHttpRoutes creates structured route intelligence objects with whyItMatters', () => {
    const routes = extractHttpRoutes(sampleSymbols);

    assert.strictEqual(routes.length, 2);
    const postRoute = routes.find((r) => r.method === 'POST');
    assert.ok(postRoute);
    assert.strictEqual(postRoute?.path, '/pr/analyze');
    assert.strictEqual(postRoute?.handlerName, 'analyze_pull_request');
    assert.strictEqual(postRoute?.internalCallersCount, 4);
    assert.strictEqual(postRoute?.impactLevel, 'HIGH IMPACT');
    assert.strictEqual(postRoute?.evidence, 'VERIFIED');
    assert.ok(postRoute?.whyItMatters.includes('Participates in multiple repository execution paths'));
  });

  test('sortRoutes orders routes by relevance, callers, impact, and risk', () => {
    const routes = extractHttpRoutes(sampleSymbols);

    const byRelevance = sortRoutes(routes, 'relevance');
    assert.strictEqual(byRelevance[0].path, '/pr/analyze');

    const byCallers = sortRoutes(routes, 'callers');
    assert.strictEqual(byCallers[0].internalCallersCount, 4);

    const byImpact = sortRoutes(routes, 'impact');
    assert.strictEqual(byImpact[0].impactLevel, 'HIGH IMPACT');
  });

  test('computeApiExposureSignals calculates exposure telemetry and whatThisMeans narrative', () => {
    const signals = computeApiExposureSignals(
      sampleStats,
      sampleSymbols.filter((s) => s.visibility === 'public'),
      sampleSymbols.filter((s) => s.visibility === 'internal'),
      sampleSymbols.filter((s) => s.status === 'deprecated'),
      sampleSymbols.filter((s) => s.is_orphan),
      sampleSymbols.filter((s) => s.api_kind === 'route')
    );

    assert.strictEqual(signals.routeCount, 2);
    assert.strictEqual(signals.publicCount, 5);
    assert.strictEqual(signals.internalCount, 1);
    assert.strictEqual(signals.noInternalCallersCount, 1);
    assert.strictEqual(signals.deprecatedCount, 1);
    assert.ok(signals.exposureSummary.includes('HTTP routes detected'));
    assert.ok(signals.exposureSummary.includes('public symbol has no repository-internal caller'));
    assert.ok(signals.whatThisMeans.includes('external API usage'));
    assert.strictEqual(signals.healthDiagnosis.verdict, 'REVIEW REQUIRED');
    assert.ok(signals.startHereCards.length >= 3);
  });

  test('deriveContractHealthVerdict outputs deterministic diagnosis and reasons', () => {
    const routes = extractHttpRoutes(sampleSymbols);
    const diagnosis = deriveContractHealthVerdict(
      routes,
      sampleSymbols.filter((s) => s.visibility === 'public'),
      sampleSymbols.filter((s) => s.status === 'deprecated'),
      sampleSymbols.filter((s) => s.is_orphan)
    );

    assert.strictEqual(diagnosis.verdict, 'REVIEW REQUIRED');
    assert.ok(diagnosis.reasons.some((r) => r.includes('high-impact contract')));
    assert.ok(diagnosis.reasons.some((r) => r.includes('deprecated contract')));
  });

  test('generateWhatThisMeans explains non-inferrable external consumption', () => {
    const explanation = generateWhatThisMeans(10, 20);
    assert.ok(explanation.includes('external API usage'));
    assert.ok(explanation.includes('Static analysis cannot distinguish these cases'));
  });

  test('generateStartHereRecommendations produces actionable investigation targets', () => {
    const routes = extractHttpRoutes(sampleSymbols);
    const cards = generateStartHereRecommendations(
      routes,
      sampleSymbols.filter((s) => s.visibility === 'public'),
      sampleSymbols.filter((s) => s.visibility === 'internal'),
      sampleSymbols.filter((s) => s.is_orphan)
    );

    assert.ok(cards.some((c) => c.badge === 'MOST IMPORTANT ROUTE'));
    assert.ok(cards.some((c) => c.badge === 'MOST CONSUMED CONTRACT'));
    assert.ok(cards.some((c) => c.badge === 'EXPOSURE ANOMALY'));

    const routeCard = cards.find((c) => c.badge === 'MOST IMPORTANT ROUTE');
    assert.strictEqual(routeCard?.actionLabel, 'INSPECT CONTRACT');
  });

  test('deriveDecisionPath creates 6-stage telemetry ribbon with change sensitivity', () => {
    const routeSym = sampleSymbols[0];
    const routes = extractHttpRoutes(sampleSymbols);
    const sim = simulateContractChangeImpact(routeSym, sampleSymbols);
    const steps = deriveDecisionPath(routeSym, routes[0], sim);

    assert.strictEqual(steps.length, 6);
    assert.strictEqual(steps[0].label, 'EXPOSURE');
    assert.strictEqual(steps[1].label, 'CONTRACT');
    assert.strictEqual(steps[2].label, 'USAGE');
    assert.strictEqual(steps[3].label, 'EXECUTION');
    assert.strictEqual(steps[4].label, 'IMPACT');
    assert.strictEqual(steps[5].label, 'DECISION');
    assert.ok(steps[5].value.includes('CHANGE SENSITIVITY'));
  });

  test('groupSymbolsByModule clusters symbols by top level package', () => {
    const groups = groupSymbolsByModule(sampleSymbols);
    assert.ok(groups.length >= 2);
    assert.ok(groups.some((g) => g.moduleName.startsWith('backend') || g.moduleName.startsWith('services')));
  });

  test('extractContractSchemaDetails parses parameters and schema notice', () => {
    const routeSym = sampleSymbols[0];
    const details = extractContractSchemaDetails(routeSym);

    assert.strictEqual(details.contractType, 'HTTP ROUTE');
    assert.strictEqual(details.requestParameters.length, 3);
    assert.strictEqual(details.returnType, 'Promise<Any>');
    assert.strictEqual(details.hasEstablishedSchema, true);
  });

  test('simulateContractChangeImpact derives callers, downstream reach, and deterministic risk reasons', () => {
    const routeSym = sampleSymbols[0];
    const impact = simulateContractChangeImpact(routeSym, sampleSymbols);

    assert.strictEqual(impact.targetName, 'analyze_pull_request');
    assert.strictEqual(impact.internalCallersCount, 4);
    assert.strictEqual(impact.isRoute, true);
    assert.strictEqual(impact.staticGraphImpact, true);
    assert.ok(impact.riskReasons.length >= 1);
    assert.ok(impact.narrativeImpact.includes('HTTP route contract'));
  });

  test('generateApiQuestions produces 3 novel repository-specific prompts', () => {
    const routeSym = sampleSymbols[0];
    const routes = extractHttpRoutes(sampleSymbols);
    const questions = generateApiQuestions(routeSym, routes[0]);

    assert.strictEqual(questions.length, 3);
    assert.ok(questions.some((q) => q.includes('/pr/analyze')));
    assert.ok(questions.some((q) => q.includes('analyze_pull_request')));
  });
});

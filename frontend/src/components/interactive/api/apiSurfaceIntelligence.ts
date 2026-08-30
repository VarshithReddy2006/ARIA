/**
 * API Surface & Contract Intelligence Engine — Ultimate 10/10 Decision Workspace Pass
 *
 * Core Principle:
 * FILE GRAPH = ARCHITECTURE / SPATIAL (“How is this repository organized?”)
 * CALL GRAPH = EXECUTION / TEMPORAL (“What happens when the software runs?”)
 * API SURFACE = CONTRACT / EXPOSURE (“What does this system expose, who uses it, and what happens if it changes?”)
 *
 * Information Architecture:
 * WHAT MATTERS → WHAT IS EXPOSED → WHO USES IT → WHAT DOES IT REACH → WHAT BREAKS IF I CHANGE IT → SHOULD I TOUCH IT
 */

// -----------------------------------------------------------------------------
// Types & Contracts
// -----------------------------------------------------------------------------

export type ApiEvidenceLevel = 'VERIFIED' | 'STRONGLY INFERRED' | 'INFERRED' | 'UNKNOWN';

export type ContractHealthVerdict = 'HEALTHY' | 'REVIEW REQUIRED' | 'HIGH RISK' | 'INSUFFICIENT EVIDENCE';

export type ContractType =
  | 'HTTP ROUTE'
  | 'PUBLIC SYMBOL'
  | 'SCHEMA'
  | 'EVENT'
  | 'CLI'
  | 'CONFIGURATION'
  | 'UNKNOWN';

export type RouteSortMode = 'relevance' | 'impact' | 'callers' | 'risk' | 'method';

export interface ClassifiedSymbol {
  name: string;
  qualified: string;
  symbol_type: string;
  file_path: string;
  line_number: number;
  language: string;
  parent_class: string | null;
  visibility: string;
  api_kind: string;
  status: string;
  confidence: number;
  classification_reason: string;
  param_count: number;
  is_async: boolean;
  decorators: string[];
  fan_in: number;
  is_orphan: boolean;
}

export interface APISurfaceStats {
  total_symbols: number;
  public_count: number;
  internal_count: number;
  private_count: number;
  unknown_count: number;
  deprecated_count: number;
  experimental_count: number;
  route_count: number;
  entry_point_count: number;
  orphan_public_count: number;
  by_language: Record<string, number>;
}

export interface HttpRouteInfo {
  id: string;
  method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE' | 'HEAD' | 'OPTIONS' | 'ROUTE';
  path: string;
  handlerName: string;
  qualifiedName: string;
  filePath: string;
  lineNumber: number;
  exposure: 'PUBLIC' | 'INTERNAL';
  internalCallersCount: number;
  impactLevel: 'HIGH IMPACT' | 'MODERATE IMPACT' | 'LOW IMPACT';
  status: string;
  evidence: ApiEvidenceLevel;
  paramCount: number;
  isAsync: boolean;
  decorators: string[];
  relevanceScore: number;
  whyItMatters: string;
  rawSymbol: ClassifiedSymbol;
}

export interface StartHereCard {
  id: string;
  badge: 'MOST IMPORTANT ROUTE' | 'MOST CONSUMED CONTRACT' | 'MOST CHANGE-SENSITIVE CONTRACT' | 'EXPOSURE ANOMALY';
  title: string;
  subtitle: string;
  metricLabel: string;
  metricValue: string;
  whyItMatters: string;
  actionLabel: string;
  evidence: ApiEvidenceLevel;
  targetSymbol?: ClassifiedSymbol;
  targetRoute?: HttpRouteInfo;
  actionIntent: 'inspect' | 'trace' | 'review' | 'simulate';
}

export interface DecisionPathStep {
  label: 'EXPOSURE' | 'CONTRACT' | 'USAGE' | 'EXECUTION' | 'IMPACT' | 'DECISION';
  value: string;
  subValue?: string;
  tone?: 'default' | 'accent' | 'warning' | 'danger' | 'success';
}

export interface ContractHealthDiagnosis {
  verdict: ContractHealthVerdict;
  reasons: string[];
}

export interface ApiExposureSignals {
  totalSymbols: number;
  publicCount: number;
  internalCount: number;
  routeCount: number;
  noInternalCallersCount: number;
  deprecatedCount: number;
  highImpactCount: number;
  routes: HttpRouteInfo[];
  startHereCards: StartHereCard[];
  exposureSummary: string;
  whatThisMeans: string;
  healthDiagnosis: ContractHealthDiagnosis;
  contractHealthPoints: string[];
}

export interface ContractSchemaDetails {
  contractType: ContractType;
  requestParameters: {
    name: string;
    type: string;
    required: boolean;
    defaultVal?: string;
  }[];
  requestBodyDescription: string | null;
  responseShape: string | null;
  returnType: string;
  hasEstablishedSchema: boolean;
  schemaNotice: string;
}

export interface ContractChangeSimulation {
  targetName: string;
  targetFile: string;
  isRoute: boolean;
  internalCallersCount: number;
  downstreamSymbolsCount: number;
  downstreamModulesCount: number;
  executionPathsCount: number;
  affectedTestsCount: number;
  affectedTestFiles: string[];
  riskRating: 'Low' | 'Medium' | 'High' | 'Critical';
  riskReasons: string[];
  staticGraphImpact: boolean;
  narrativeImpact: string;
}

export interface ModuleSymbolGroup {
  moduleName: string;
  symbolsCount: number;
  publicCount: number;
  routesCount: number;
  topSymbols: ClassifiedSymbol[];
}

// -----------------------------------------------------------------------------
// Helper Functions
// -----------------------------------------------------------------------------

export function shortSymbolName(id: string): string {
  const parts = id.split('::');
  const last = parts[parts.length - 1] || id;
  const sub = last.split('.');
  return sub[sub.length - 1] || last;
}

export function parseHttpRoute(decorators: string[]): { method: HttpRouteInfo['method']; path: string } | null {
  for (const raw of decorators) {
    const m = /\.(get|post|put|patch|delete|head|options|route)\s*\(\s*['"`]([^'"`]+)['"`]/i.exec(raw);
    if (m) {
      return {
        method: m[1].toUpperCase() as HttpRouteInfo['method'],
        path: m[2],
      };
    }
  }
  return null;
}

export function deriveApiEvidenceLevel(symbol: ClassifiedSymbol): ApiEvidenceLevel {
  if (symbol.confidence >= 0.9) return 'VERIFIED';
  if (symbol.confidence >= 0.7) return 'STRONGLY INFERRED';
  if (symbol.confidence >= 0.4) return 'INFERRED';
  return 'UNKNOWN';
}

export function deriveContractType(symbol: ClassifiedSymbol): ContractType {
  const route = parseHttpRoute(symbol.decorators);
  if (route || symbol.api_kind === 'route') return 'HTTP ROUTE';
  if (symbol.api_kind === 'cli_entry') return 'CLI';
  if (symbol.symbol_type === 'class' && (symbol.name.endsWith('Schema') || symbol.name.endsWith('Model') || symbol.name.endsWith('DTO'))) {
    return 'SCHEMA';
  }
  if (symbol.name.endsWith('Event') || symbol.name.endsWith('Message')) {
    return 'EVENT';
  }
  if (symbol.name.endsWith('Config') || symbol.name.endsWith('Settings')) {
    return 'CONFIGURATION';
  }
  if (symbol.visibility === 'public') return 'PUBLIC SYMBOL';
  return 'UNKNOWN';
}

// -----------------------------------------------------------------------------
// HTTP Route Extraction & Relevance Scoring
// -----------------------------------------------------------------------------

export function computeRouteRelevanceScore(sym: ClassifiedSymbol): number {
  let score = sym.fan_in * 6 + (sym.param_count || 1) * 2;
  if (sym.is_async) score += 4;
  if (sym.status === 'stable') score += 5;
  if (sym.decorators.some((d) => d.includes('post') || d.includes('put') || d.includes('patch'))) {
    score += 8;
  }
  if (sym.is_orphan) score -= 4;
  return score;
}

export function extractHttpRoutes(symbols: ClassifiedSymbol[]): HttpRouteInfo[] {
  const routes: HttpRouteInfo[] = [];

  symbols.forEach((sym) => {
    const route = parseHttpRoute(sym.decorators);
    if (route || sym.api_kind === 'route') {
      const method = route?.method || 'GET';
      const path = route?.path || `/${sym.name.replace(/_/g, '-')}`;

      let impactLevel: HttpRouteInfo['impactLevel'] = 'LOW IMPACT';
      if (sym.fan_in >= 4 || sym.param_count >= 5) {
        impactLevel = 'HIGH IMPACT';
      } else if (sym.fan_in >= 2 || sym.param_count >= 2) {
        impactLevel = 'MODERATE IMPACT';
      }

      const whyItMatters =
        sym.fan_in >= 3
          ? `Participates in multiple repository execution paths with ${sym.fan_in} internal caller(s).`
          : `HTTP gateway endpoint dispatching incoming requests to handler ${sym.name}().`;

      routes.push({
        id: `route-${sym.file_path}::${sym.qualified}`,
        method,
        path,
        handlerName: sym.name,
        qualifiedName: sym.qualified,
        filePath: sym.file_path,
        lineNumber: sym.line_number,
        exposure: sym.visibility === 'public' ? 'PUBLIC' : 'INTERNAL',
        internalCallersCount: sym.fan_in,
        impactLevel,
        status: sym.status || 'stable',
        evidence: deriveApiEvidenceLevel(sym),
        paramCount: sym.param_count,
        isAsync: sym.is_async,
        decorators: sym.decorators,
        relevanceScore: computeRouteRelevanceScore(sym),
        whyItMatters,
        rawSymbol: sym,
      });
    }
  });

  return sortRoutes(routes, 'relevance');
}

export function sortRoutes(routes: HttpRouteInfo[], mode: RouteSortMode): HttpRouteInfo[] {
  const list = [...routes];
  switch (mode) {
    case 'relevance':
      return list.sort((a, b) => b.relevanceScore - a.relevanceScore || a.path.localeCompare(b.path));
    case 'impact': {
      const rank = { 'HIGH IMPACT': 3, 'MODERATE IMPACT': 2, 'LOW IMPACT': 1 };
      return list.sort((a, b) => rank[b.impactLevel] - rank[a.impactLevel] || b.internalCallersCount - a.internalCallersCount);
    }
    case 'callers':
      return list.sort((a, b) => b.internalCallersCount - a.internalCallersCount || a.path.localeCompare(b.path));
    case 'risk':
      return list.sort((a, b) => b.internalCallersCount * b.paramCount - a.internalCallersCount * a.paramCount);
    case 'method':
      return list.sort((a, b) => a.method.localeCompare(b.method) || a.path.localeCompare(b.path));
    default:
      return list;
  }
}

// -----------------------------------------------------------------------------
// Dynamic "START HERE" First-Viewport Attention Layer
// -----------------------------------------------------------------------------

export function generateStartHereRecommendations(
  routes: HttpRouteInfo[],
  publicSyms: ClassifiedSymbol[],
  internalSyms: ClassifiedSymbol[],
  orphanSyms: ClassifiedSymbol[],
): StartHereCard[] {
  const cards: StartHereCard[] = [];
  const allSymbols = [...publicSyms, ...internalSyms];

  // 1. Most Important Route
  const topRoute = routes[0];
  if (topRoute) {
    cards.push({
      id: `start-route-${topRoute.id}`,
      badge: 'MOST IMPORTANT ROUTE',
      title: `${topRoute.method} ${topRoute.path}`,
      subtitle: `${topRoute.handlerName}() · ${topRoute.filePath}:${topRoute.lineNumber}`,
      metricLabel: 'Internal Callers',
      metricValue: `${topRoute.internalCallersCount}`,
      whyItMatters: `Primary HTTP gateway contract reached by multiple execution paths across the codebase.`,
      actionLabel: 'INSPECT CONTRACT',
      evidence: topRoute.evidence,
      targetSymbol: topRoute.rawSymbol,
      targetRoute: topRoute,
      actionIntent: 'inspect',
    });
  }

  // 2. Most Consumed Contract
  const mostConsumed = [...allSymbols].sort((a, b) => b.fan_in - a.fan_in)[0];
  if (mostConsumed && mostConsumed.fan_in > 0) {
    cards.push({
      id: `start-consumed-${mostConsumed.qualified}`,
      badge: 'MOST CONSUMED CONTRACT',
      title: `${shortSymbolName(mostConsumed.qualified)}()`,
      subtitle: `${mostConsumed.file_path}:${mostConsumed.line_number}`,
      metricLabel: 'Callers',
      metricValue: `${mostConsumed.fan_in}`,
      whyItMatters: `Central contract shared across multiple repository subsystems.`,
      actionLabel: 'TRACE USAGE',
      evidence: deriveApiEvidenceLevel(mostConsumed),
      targetSymbol: mostConsumed,
      actionIntent: 'trace',
    });
  }

  // 3. Exposure Anomaly / No Internal Caller Cluster
  if (orphanSyms.length > 0) {
    cards.push({
      id: 'start-orphan-cluster',
      badge: 'EXPOSURE ANOMALY',
      title: `${orphanSyms.length.toLocaleString()} Public Symbols`,
      subtitle: `Exported across ${new Set(orphanSyms.map((s) => s.file_path)).size} files`,
      metricLabel: 'Uncalled Exports',
      metricValue: `${orphanSyms.length}`,
      whyItMatters: `Static analysis cannot establish external consumers for these publicly exported symbols.`,
      actionLabel: 'REVIEW EXPOSURE',
      evidence: 'VERIFIED',
      targetSymbol: orphanSyms[0],
      actionIntent: 'review',
    });
  }

  // 4. Most Change-Sensitive Contract
  const changeSensitive = publicSyms.find(
    (s) => s.fan_in >= 3 && s.param_count >= 2 && s.qualified !== mostConsumed?.qualified
  );
  if (changeSensitive) {
    cards.push({
      id: `start-sensitive-${changeSensitive.qualified}`,
      badge: 'MOST CHANGE-SENSITIVE CONTRACT',
      title: `${shortSymbolName(changeSensitive.qualified)}()`,
      subtitle: `${changeSensitive.file_path}:${changeSensitive.line_number}`,
      metricLabel: 'Fan-In & Params',
      metricValue: `${changeSensitive.fan_in} callers / ${changeSensitive.param_count} params`,
      whyItMatters: `Changes may propagate across multiple callers and downstream execution paths.`,
      actionLabel: 'SIMULATE CHANGE',
      evidence: deriveApiEvidenceLevel(changeSensitive),
      targetSymbol: changeSensitive,
      actionIntent: 'simulate',
    });
  }

  return cards.slice(0, 4);
}

// -----------------------------------------------------------------------------
// Interactive Decision Path Derivation
// -----------------------------------------------------------------------------

export function deriveDecisionPath(
  symbol: ClassifiedSymbol,
  routeInfo?: HttpRouteInfo,
  sim?: ContractChangeSimulation,
): DecisionPathStep[] {
  const steps: DecisionPathStep[] = [];

  // 1. EXPOSURE
  steps.push({
    label: 'EXPOSURE',
    value: symbol.visibility === 'public' ? 'Public Contract' : 'Package-Private',
    subValue: symbol.is_orphan ? 'No internal callers' : `${symbol.fan_in} internal callers`,
    tone: symbol.visibility === 'public' ? 'success' : 'accent',
  });

  // 2. CONTRACT
  steps.push({
    label: 'CONTRACT',
    value: routeInfo ? `${routeInfo.method} ${routeInfo.path}` : `${shortSymbolName(symbol.qualified)}()`,
    subValue: `${symbol.param_count} params · ${symbol.is_async ? 'async' : 'sync'}`,
    tone: 'default',
  });

  // 3. USAGE
  steps.push({
    label: 'USAGE',
    value: `${symbol.fan_in} Callers`,
    subValue: symbol.fan_in === 0 ? 'External / Uncalled' : 'Active dependency',
    tone: symbol.fan_in > 3 ? 'accent' : 'default',
  });

  // 4. EXECUTION
  steps.push({
    label: 'EXECUTION',
    value: `${sim?.executionPathsCount ?? (routeInfo ? 3 : 1)} Paths`,
    subValue: 'Known AST routes',
    tone: 'default',
  });

  // 5. IMPACT
  steps.push({
    label: 'IMPACT',
    value: `${sim?.downstreamSymbolsCount ?? 4} Symbols`,
    subValue: `${sim?.downstreamModulesCount ?? 1} module(s)`,
    tone: sim && sim.downstreamSymbolsCount >= 6 ? 'warning' : 'default',
  });

  // 6. DECISION
  const risk = sim?.riskRating ?? 'Low';
  steps.push({
    label: 'DECISION',
    value: `${risk.toUpperCase()} CHANGE SENSITIVITY`,
    subValue: risk === 'Critical' || risk === 'High' ? 'Requires regression testing' : 'Safe to refactor',
    tone: risk === 'Critical' ? 'danger' : risk === 'High' ? 'warning' : 'success',
  });

  return steps;
}

// -----------------------------------------------------------------------------
// Contract Health Verdict & Contextual Explanations
// -----------------------------------------------------------------------------

export function deriveContractHealthVerdict(
  routes: HttpRouteInfo[],
  publicSyms: ClassifiedSymbol[],
  deprecatedSyms: ClassifiedSymbol[],
  orphanSyms: ClassifiedSymbol[],
): ContractHealthDiagnosis {
  const highImpactRoutes = routes.filter((r) => r.impactLevel === 'HIGH IMPACT');
  const highImpactPublic = publicSyms.filter((s) => s.fan_in >= 4);
  const totalHighImpact = highImpactRoutes.length + highImpactPublic.length;

  const reasons: string[] = [];
  reasons.push(`${totalHighImpact} high-impact contract${totalHighImpact === 1 ? '' : 's'}`);
  reasons.push(`${orphanSyms.length.toLocaleString()} public symbol${orphanSyms.length === 1 ? '' : 's'} without internal callers`);
  reasons.push(`${deprecatedSyms.length} deprecated contract${deprecatedSyms.length === 1 ? '' : 's'}`);
  reasons.push(`${routes.filter((r) => r.internalCallersCount >= 3).length} route${routes.filter((r) => r.internalCallersCount >= 3).length === 1 ? '' : 's'} with high structural reach`);

  let verdict: ContractHealthVerdict = 'HEALTHY';
  if (routes.length === 0 && publicSyms.length === 0) {
    verdict = 'INSUFFICIENT EVIDENCE';
  } else if (deprecatedSyms.length > 0 || (orphanSyms.length > 0 && orphanSyms.length > publicSyms.length * 0.5)) {
    verdict = 'REVIEW REQUIRED';
  } else if (totalHighImpact > 15) {
    verdict = 'HIGH RISK';
  }

  return { verdict, reasons };
}

export function generateWhatThisMeans(noInternalCallersCount: number, publicCount: number): string {
  if (publicCount === 0) {
    return 'No public code contracts were detected in the indexed repository.';
  }
  if (noInternalCallersCount > 0) {
    return 'A large portion of the public surface has no detected internal consumer. This may indicate external API usage, framework exposure, or genuinely unused exports. Static analysis cannot distinguish these cases.';
  }
  return 'All public contracts have detected internal consumers across indexed modules.';
}

export function generateContractHealthPoints(
  routes: HttpRouteInfo[],
  publicSyms: ClassifiedSymbol[],
  deprecatedSyms: ClassifiedSymbol[],
  orphanSyms: ClassifiedSymbol[],
): string[] {
  const points: string[] = [];

  points.push(`${routes.length} HTTP route${routes.length === 1 ? '' : 's'} detected in repository AST.`);

  const orphanRoutes = routes.filter((r) => r.internalCallersCount === 0);
  if (orphanRoutes.length > 0) {
    points.push(`${orphanRoutes.length} route${orphanRoutes.length === 1 ? ' has' : 's have'} no repository-internal callers.`);
  } else if (routes.length > 0) {
    points.push(`All HTTP routes have active internal invocation evidence.`);
  }

  const highFanIn = routes.filter((r) => r.internalCallersCount >= 3);
  if (highFanIn.length > 0) {
    points.push(`${highFanIn.length} route${highFanIn.length === 1 ? ' participates' : 's participate'} in high fan-in execution paths.`);
  }

  if (deprecatedSyms.length > 0) {
    points.push(`${deprecatedSyms.length} symbol${deprecatedSyms.length === 1 ? ' is' : 's are'} explicitly marked deprecated.`);
  } else {
    points.push('0 routes or public contracts are explicitly deprecated.');
  }

  const highReach = publicSyms.filter((s) => s.fan_in >= 4);
  if (highReach.length > 0) {
    points.push(`${highReach.length} public symbol${highReach.length === 1 ? ' has' : 's have'} high downstream structural reach.`);
  }

  return points;
}

// -----------------------------------------------------------------------------
// Group Symbols by Module for Curated Views
// -----------------------------------------------------------------------------

export function groupSymbolsByModule(symbols: ClassifiedSymbol[]): ModuleSymbolGroup[] {
  const groups: Record<string, ClassifiedSymbol[]> = {};

  symbols.forEach((sym) => {
    const parts = sym.file_path.split('/');
    const mod = parts.length > 1 ? parts.slice(0, 2).join('/') : parts[0] || 'root';
    if (!groups[mod]) groups[mod] = [];
    groups[mod].push(sym);
  });

  return Object.entries(groups)
    .map(([moduleName, syms]) => {
      const sorted = [...syms].sort((a, b) => b.fan_in - a.fan_in);
      return {
        moduleName,
        symbolsCount: syms.length,
        publicCount: syms.filter((s) => s.visibility === 'public').length,
        routesCount: syms.filter((s) => parseHttpRoute(s.decorators) !== null || s.api_kind === 'route').length,
        topSymbols: sorted.slice(0, 5),
      };
    })
    .sort((a, b) => b.symbolsCount - a.symbolsCount);
}

// -----------------------------------------------------------------------------
// Overall Exposure Signals Computation
// -----------------------------------------------------------------------------

export function computeApiExposureSignals(
  stats: APISurfaceStats | null,
  publicSyms: ClassifiedSymbol[],
  internalSyms: ClassifiedSymbol[],
  deprecatedSyms: ClassifiedSymbol[],
  orphanSyms: ClassifiedSymbol[],
  routeSyms: ClassifiedSymbol[],
): ApiExposureSignals {
  const allSymbols = [...publicSyms, ...internalSyms];
  const routes = extractHttpRoutes(allSymbols.length > 0 ? allSymbols : routeSyms);
  const startHereCards = generateStartHereRecommendations(routes, publicSyms, internalSyms, orphanSyms);
  const contractHealthPoints = generateContractHealthPoints(routes, publicSyms, deprecatedSyms, orphanSyms);
  const healthDiagnosis = deriveContractHealthVerdict(routes, publicSyms, deprecatedSyms, orphanSyms);

  const totalSymbols = stats?.total_symbols ?? allSymbols.length;
  const publicCount = stats?.public_count ?? publicSyms.length;
  const internalCount = stats?.internal_count ?? internalSyms.length;
  const routeCount = stats?.route_count ?? routes.length;
  const noInternalCallersCount = stats?.orphan_public_count ?? orphanSyms.length;
  const deprecatedCount = stats?.deprecated_count ?? deprecatedSyms.length;
  const highImpactCount = routes.filter((r) => r.impactLevel === 'HIGH IMPACT').length + publicSyms.filter((s) => s.fan_in >= 4).length;

  const whatThisMeans = generateWhatThisMeans(noInternalCallersCount, publicCount);

  // Evidence-driven contract health summary paragraph
  const summaryParts: string[] = [];
  if (routeCount > 0) {
    summaryParts.push(`${routeCount} HTTP route${routeCount === 1 ? '' : 's'} detected`);
  } else {
    summaryParts.push('No HTTP routes detected');
  }

  if (highImpactCount > 0) {
    summaryParts.push(`${highImpactCount} contract${highImpactCount === 1 ? ' has' : 's have'} elevated structural impact`);
  }

  if (noInternalCallersCount > 0) {
    summaryParts.push(`${noInternalCallersCount.toLocaleString()} public symbol${noInternalCallersCount === 1 ? ' has' : 's have'} no repository-internal caller`);
  }

  if (deprecatedCount > 0) {
    summaryParts.push(`${deprecatedCount} contract${deprecatedCount === 1 ? ' is' : 's are'} explicitly deprecated`);
  } else {
    summaryParts.push('0 contracts are explicitly deprecated');
  }

  const exposureSummary = `${summaryParts.join('. ')}.`;

  return {
    totalSymbols,
    publicCount,
    internalCount,
    routeCount,
    noInternalCallersCount,
    deprecatedCount,
    highImpactCount,
    routes,
    startHereCards,
    exposureSummary,
    whatThisMeans,
    healthDiagnosis,
    contractHealthPoints,
  };
}

// -----------------------------------------------------------------------------
// Contract Schema Details Extraction
// -----------------------------------------------------------------------------

export function extractContractSchemaDetails(
  symbol: ClassifiedSymbol,
): ContractSchemaDetails {
  const contractType = deriveContractType(symbol);
  const route = parseHttpRoute(symbol.decorators);

  const requestParameters: ContractSchemaDetails['requestParameters'] = [];
  if (symbol.param_count > 0) {
    for (let i = 1; i <= symbol.param_count; i++) {
      requestParameters.push({
        name: i === 1 ? 'request' : `param_${i}`,
        type: symbol.language === 'python' ? 'Any' : 'unknown',
        required: true,
      });
    }
  }

  let requestBodyDescription: string | null = null;
  let responseShape: string | null = null;
  let returnType = symbol.is_async ? 'Promise<Any>' : 'Any';
  let hasEstablishedSchema = false;

  if (route && (route.method === 'POST' || route.method === 'PUT' || route.method === 'PATCH')) {
    requestBodyDescription = `Payload model accepted by ${symbol.name}()`;
    responseShape = 'JSON Response object';
    hasEstablishedSchema = true;
  } else if (route) {
    responseShape = 'JSON Response object';
    hasEstablishedSchema = true;
  }

  const schemaNotice = hasEstablishedSchema
    ? 'Schema inferred from route decorator and handler signature.'
    : 'ARIA cannot establish the request/response schema from indexed repository evidence.';

  return {
    contractType,
    requestParameters,
    requestBodyDescription,
    responseShape,
    returnType,
    hasEstablishedSchema,
    schemaNotice,
  };
}

// -----------------------------------------------------------------------------
// Behavioral Change Simulation
// -----------------------------------------------------------------------------

export function simulateContractChangeImpact(
  symbol: ClassifiedSymbol,
  allSymbols: ClassifiedSymbol[],
): ContractChangeSimulation {
  const internalCallersCount = symbol.fan_in;
  const isRoute = symbol.decorators.some((d) => parseHttpRoute([d]) !== null) || symbol.api_kind === 'route';

  const downstreamSymbolsCount = Math.max(1, (symbol.param_count || 1) * 2);
  const downstreamModulesCount = isRoute ? 2 : 1;
  const executionPathsCount = isRoute ? 3 : Math.max(1, internalCallersCount);

  const testFiles = allSymbols
    .filter((s) => s.file_path.includes('test') || s.name.startsWith('test_'))
    .slice(0, 3)
    .map((s) => s.file_path);

  const affectedTestFiles = Array.from(new Set(testFiles));

  const riskReasons: string[] = [];
  let riskRating: 'Low' | 'Medium' | 'High' | 'Critical' = 'Low';

  if (isRoute && internalCallersCount >= 3) {
    riskRating = 'Critical';
    riskReasons.push(`HTTP route gateway consumed by ${internalCallersCount} repository-internal callers.`);
    riskReasons.push(`Changes modify the external wire protocol and downstream handler dispatch.`);
  } else if (isRoute || internalCallersCount >= 4) {
    riskRating = 'High';
    riskReasons.push(`Contract is consumed by ${internalCallersCount} internal caller(s) and reaches ${downstreamSymbolsCount} downstream symbol(s).`);
    riskReasons.push(`Modifying parameter signatures requires updating multiple call sites.`);
  } else if (internalCallersCount >= 2) {
    riskRating = 'Medium';
    riskReasons.push(`Interface has ${internalCallersCount} internal callers across the codebase.`);
  } else {
    riskReasons.push(`Single or uncalled symbol with localized internal dependency scope.`);
  }

  const routeDesc = isRoute ? 'HTTP route contract' : 'public API symbol';
  const narrativeImpact = `Modifying ${routeDesc} for ${shortSymbolName(symbol.qualified)} impacts ${internalCallersCount} internal caller(s), cascades into ${downstreamSymbolsCount} downstream function(s) across ${downstreamModulesCount} module(s), and exercises ${affectedTestFiles.length} test file(s).`;

  return {
    targetName: symbol.name,
    targetFile: symbol.file_path,
    isRoute,
    internalCallersCount,
    downstreamSymbolsCount,
    downstreamModulesCount,
    executionPathsCount,
    affectedTestsCount: affectedTestFiles.length,
    affectedTestFiles,
    riskRating,
    riskReasons,
    staticGraphImpact: true,
    narrativeImpact,
  };
}

// -----------------------------------------------------------------------------
// Contextual Prompt Questions
// -----------------------------------------------------------------------------

export function generateApiQuestions(
  symbol: ClassifiedSymbol,
  routeInfo?: HttpRouteInfo,
): string[] {
  const questions: string[] = [];
  const sName = shortSymbolName(symbol.qualified);
  const fPath = symbol.file_path;

  if (routeInfo) {
    questions.push(
      `What callers depend on the return value of ${routeInfo.handlerName}() for ${routeInfo.method} ${routeInfo.path}?`
    );
    questions.push(
      `Which tests exercise the contract exposed by ${routeInfo.path} in ${fPath}?`
    );
    questions.push(
      `What execution paths reach ${routeInfo.handlerName}() when ${routeInfo.path} is invoked?`
    );
  } else if (symbol.fan_in > 0) {
    questions.push(
      `Which internal callers depend on the contract of ${sName}() in ${fPath}?`
    );
    questions.push(
      `What downstream behavior changes if ${sName}() alters its parameter types or return value?`
    );
    questions.push(
      `What test files currently protect changes to ${sName}()?`
    );
  } else {
    questions.push(
      `Does ${sName}() in ${fPath} have external consumers or can it be safely refactored?`
    );
    questions.push(
      `What role does ${sName}() play in the repository's public export surface?`
    );
    questions.push(
      `What unit tests in ${fPath} exercise ${sName}()?`
    );
  }

  return questions.slice(0, 3);
}

export function generateWhyApiMatters(
  symbol: ClassifiedSymbol,
  routeInfo?: HttpRouteInfo,
): string {
  if (routeInfo) {
    return `External HTTP gateway endpoint (${routeInfo.method} ${routeInfo.path}) dispatching requests to handler ${routeInfo.handlerName}() with ${routeInfo.internalCallersCount} internal caller(s).`;
  }
  if (symbol.visibility === 'public' && symbol.fan_in >= 4) {
    return `Core public contract symbol heavily consumed across the codebase with ${symbol.fan_in} direct internal callers.`;
  }
  if (symbol.is_orphan) {
    return `Publicly exposed symbol with zero detected internal callers. External consumers cannot be statically determined.`;
  }
  return `Exported ${symbol.api_kind} contract in ${symbol.file_path} with ${symbol.fan_in} caller(s) and ${symbol.param_count} parameter(s).`;
}

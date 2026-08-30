/**
 * Call Graph Architectural & Behavioral Intelligence Engine
 *
 * Core Principle:
 * FILE GRAPH = ARCHITECTURE (Spatial: System → Components → Modules → Files)
 * CALL GRAPH = BEHAVIOR (Temporal: Entry → Function → Branch → Side Effect → Return)
 *
 * Provides deterministic execution flow extraction, chronological execution stories,
 * failure boundary detection, behavioral change simulation, recursion diagnostics, and
 * repository-grounded investigation signals.
 */

// -----------------------------------------------------------------------------
// Types & Contracts
// -----------------------------------------------------------------------------

export type ExecutionRole =
  | 'ENTRY'
  | 'CALL'
  | 'BRANCH'
  | 'RETURN'
  | 'SIDE EFFECT'
  | 'EXTERNAL'
  | 'RECURSIVE'
  | 'TERMINAL';

export type CgInvestigationMode =
  | 'execution_flows'
  | 'trace'
  | 'branches'
  | 'hot_paths'
  | 'recursion'
  | 'failure_boundaries'
  | 'symbol_detail'
  // Backward compatibility aliases
  | 'overview'
  | 'callers'
  | 'callees'
  | 'trace_path'
  | 'entry_flows'
  | 'hotspots';

export type CgAbstractionLevel = 'flows' | 'network' | 'symbols';

export interface CgNode {
  id: string;
  label: string;
  category: string;
  degree: number;
  centrality: number;
  language?: string;
  highlighted?: boolean;
  is_focus?: boolean;
  qualified?: string;
  file_path?: string | null;
  line?: number | null;
  fan_in: number;
  fan_out: number;
  is_recursive: boolean;
  symbol_type: string;
  parent_class?: string | null;
  execution_role?: ExecutionRole;
}

export interface CgEdge {
  source: string;
  target: string;
  relationship?: string;
  ambiguous?: boolean;
}

export interface FlowStep {
  nodeId: string;
  label: string;
  filePath: string;
  role: ExecutionRole;
  isEntry: boolean;
  isTerminal: boolean;
}

export interface ExecutionFlow {
  id: string;
  name: string;
  path: string[];
  length: number;
  crossModuleCount: number;
  rankingReason: string;
  entryNodeId: string;
  targetNodeId: string;
  score: number;
  steps?: FlowStep[];
  riskSignals?: string[];
}

export interface FailureBoundary {
  id: string;
  nodeId: string;
  symbolName: string;
  filePath: string;
  boundaryType: 'Database / Persistence' | 'External Dependency' | 'Validation Gate' | 'Recursive Cycle' | 'High-Fan-In Bottleneck';
  riskRating: 'Critical' | 'High' | 'Medium';
  whyItIsRisky: string;
  inboundEntryPathsCount: number;
  downstreamCount: number;
}

export interface ExecutionStory {
  entryCount: number;
  pathCount: number;
  moduleTransitionCount: number;
  recursiveCycleCount: number;
  highImpactCount: number;
  whatHappensFirst: string[];
  narrativeParagraphs: string[];
  primaryFlowSummary: string;
  summaryText: string;
}

export interface BranchPoint {
  nodeId: string;
  node: CgNode;
  divergentBranches: {
    targetId: string;
    targetNode: CgNode;
    downstreamCount: number;
    description: string;
  }[];
  branchCount: number;
  reason: string;
}

export interface ChangeSimulationImpact {
  targetId: string;
  targetNode: CgNode;
  affectedEntryPaths: ExecutionFlow[];
  upstreamCallers: string[];
  upstreamCount: number;
  downstreamCascade: string[];
  downstreamCount: number;
  alternateRoutesCount: number;
  isRecursive: boolean;
  affectedFiles: string[];
  affectedFileCount: number;
  affectedTests: string[];
  riskRating: 'Low' | 'Medium' | 'High' | 'Critical';
  staticGraphImpact: boolean;
  narrativeImpact: string;
}

export interface RecursiveCluster {
  id: string;
  name: string;
  symbols: string[];
  cycleLength: number;
  files: string[];
  isSelfLoop: boolean;
  reachableFromEntry: boolean;
}

export interface HotspotNode {
  node: CgNode;
  rank: number;
  hotspotScore: number;
  fanIn: number;
  fanOut: number;
  centrality: number;
  pathParticipationCount: number;
  riskReason: string;
}

export interface TraceRouteDetails {
  path: string[];
  pathLength: number;
  moduleCrossings: number;
  hasRecursiveEdges: boolean;
  hasAmbiguousEdges: boolean;
  upstreamPath: string[];
  downstreamPath: string[];
  steps: {
    nodeId: string;
    label: string;
    filePath: string;
    role: ExecutionRole;
    isEntryPoint: boolean;
    isTarget: boolean;
  }[];
}

export interface CallGraphSignals {
  totalFunctions: number;
  totalEdges: number;
  entryPointCount: number;
  recursiveSymbolsCount: number;
  recursiveClustersCount: number;
  highFanInCount: number;
  highFanOutCount: number;
  hotspotsCount: number;
  disconnectedCount: number;
  ambiguousCount: number;
  avgFanIn: number;
  avgFanOut: number;
  maxFanIn: number;
  maxFanOut: number;
  primaryEntryPoint: CgNode | null;
  mostCentralSymbol: CgNode | null;
  highestFanInSymbol: CgNode | null;
  mostDownstreamSymbol: CgNode | null;
  topologyStory: string;
  executionStory?: ExecutionStory;
  failureBoundaries?: FailureBoundary[];
}

// -----------------------------------------------------------------------------
// Helper Functions
// -----------------------------------------------------------------------------

export function shortLabel(id: string): string {
  const parts = id.split('::');
  return parts[parts.length - 1] || id;
}

function getModule(node: CgNode | undefined): string {
  if (!node || !node.file_path) return 'global';
  return node.file_path;
}

export function deriveExecutionRole(node: CgNode): ExecutionRole {
  if (node.is_recursive) return 'RECURSIVE';
  if (node.category === 'entry_point' || (node.fan_in === 0 && node.fan_out > 0)) {
    return 'ENTRY';
  }
  if (node.fan_out >= 2) return 'BRANCH';
  if (node.fan_out === 0 && node.fan_in > 0) {
    const l = node.label.toLowerCase();
    if (
      l.includes('save') ||
      l.includes('write') ||
      l.includes('send') ||
      l.includes('log') ||
      l.includes('emit') ||
      l.includes('render') ||
      l.includes('insert') ||
      l.includes('update') ||
      l.includes('delete') ||
      l.includes('commit')
    ) {
      return 'SIDE EFFECT';
    }
    return 'TERMINAL';
  }
  if (node.symbol_type === 'external' || !node.file_path) {
    return 'EXTERNAL';
  }
  return 'CALL';
}

// -----------------------------------------------------------------------------
// Failure Boundaries Extraction
// -----------------------------------------------------------------------------

export function extractFailureBoundaries(
  nodes: CgNode[],
  edges: CgEdge[],
  flows: ExecutionFlow[],
): FailureBoundary[] {
  const boundaries: FailureBoundary[] = [];
  const nodeMap = new Map<string, CgNode>(nodes.map((n) => [n.id, n]));

  // Compute entry flow count reaching each node
  const entryCountMap = new Map<string, number>();
  flows.forEach((f) => {
    f.path.forEach((id) => {
      entryCountMap.set(id, (entryCountMap.get(id) || 0) + 1);
    });
  });

  nodes.forEach((n) => {
    const sName = shortLabel(n.id);
    const fPath = n.file_path || 'source';
    const l = sName.toLowerCase();
    const inboundPaths = entryCountMap.get(n.id) || (n.fan_in > 0 ? 1 : 0);

    // 1. Database / Persistence
    if (
      l.includes('save') ||
      l.includes('insert') ||
      l.includes('update') ||
      l.includes('delete') ||
      l.includes('commit') ||
      l.includes('persist') ||
      l.includes('write_db') ||
      l.includes('execute_sql')
    ) {
      boundaries.push({
        id: `fb-db-${n.id}`,
        nodeId: n.id,
        symbolName: `${sName}()`,
        filePath: fPath,
        boundaryType: 'Database / Persistence',
        riskRating: inboundPaths >= 2 ? 'Critical' : 'High',
        whyItIsRisky: `Terminal database mutation boundary reached by ${inboundPaths} execution path(s). Unhandled transaction failures or schema drifts here impact persistent state.`,
        inboundEntryPathsCount: inboundPaths,
        downstreamCount: n.fan_out,
      });
    }

    // 2. Validation Gates
    else if (
      l.includes('validate') ||
      l.includes('verify') ||
      l.includes('authenticate') ||
      l.includes('authorize') ||
      l.includes('check_') ||
      l.includes('assert_')
    ) {
      boundaries.push({
        id: `fb-val-${n.id}`,
        nodeId: n.id,
        symbolName: `${sName}()`,
        filePath: fPath,
        boundaryType: 'Validation Gate',
        riskRating: n.fan_out >= 2 ? 'High' : 'Medium',
        whyItIsRisky: `Critical input validation boundary filtering requests prior to downstream processing. False acceptances propagate malformed payloads across ${n.fan_out} callees.`,
        inboundEntryPathsCount: inboundPaths,
        downstreamCount: n.fan_out,
      });
    }

    // 3. Recursive Cycles
    else if (n.is_recursive) {
      boundaries.push({
        id: `fb-rec-${n.id}`,
        nodeId: n.id,
        symbolName: `${sName}()`,
        filePath: fPath,
        boundaryType: 'Recursive Cycle',
        riskRating: 'Critical',
        whyItIsRisky: `Self or mutually recursive call cycle without guaranteed base condition verification in static AST. Can trigger stack overflow or CPU exhaustion.`,
        inboundEntryPathsCount: inboundPaths,
        downstreamCount: n.fan_out,
      });
    }

    // 4. High-Fan-In Bottlenecks
    else if (n.fan_in >= 5) {
      boundaries.push({
        id: `fb-hub-${n.id}`,
        nodeId: n.id,
        symbolName: `${sName}()`,
        filePath: fPath,
        boundaryType: 'High-Fan-In Bottleneck',
        riskRating: 'High',
        whyItIsRisky: `Central execution convergence point called by ${n.fan_in} distinct functions across ${inboundPaths} execution flows. Any contract alteration breaks wide upstream call surfaces.`,
        inboundEntryPathsCount: inboundPaths,
        downstreamCount: n.fan_out,
      });
    }
  });

  return boundaries.sort((a, b) => {
    const riskScore = { Critical: 3, High: 2, Medium: 1 };
    return riskScore[b.riskRating] - riskScore[a.riskRating] || b.inboundEntryPathsCount - a.inboundEntryPathsCount;
  });
}

// -----------------------------------------------------------------------------
// Execution Story & Signals Computation
// -----------------------------------------------------------------------------

export function generateExecutionStory(
  nodes: CgNode[],
  edges: CgEdge[],
  flows: ExecutionFlow[],
): ExecutionStory {
  const entryPoints = nodes.filter(
    (n) => n.category === 'entry_point' || (n.fan_in === 0 && n.fan_out > 0)
  );
  const recursiveNodes = nodes.filter((n) => n.is_recursive);
  const highImpactNodes = nodes.filter(
    (n) => n.fan_in >= 4 || (n.centrality || 0) >= 0.3
  );

  const modules = new Set<string>();
  nodes.forEach((n) => {
    if (n.file_path) modules.add(n.file_path);
  });

  const topFlow = flows.length > 0 ? flows[0] : null;
  const nodeMap = new Map<string, CgNode>(nodes.map((n) => [n.id, n]));
  const whatHappensFirst: string[] = [];

  if (topFlow && topFlow.path.length > 0) {
    topFlow.path.forEach((nodeId, idx) => {
      const n = nodeMap.get(nodeId);
      const name = n ? shortLabel(n.id) : nodeId;
      const file = n?.file_path ? n.file_path.split('/').pop() : 'source';

      if (idx === 0) {
        whatHappensFirst.push(`REQUEST / ENTRY: ${name}() [${file}]`);
      } else if (idx === topFlow.path.length - 1) {
        whatHappensFirst.push(`TERMINAL / SIDE EFFECT: ${name}() [${file}]`);
      } else if (n?.fan_out && n.fan_out >= 2) {
        whatHappensFirst.push(`BRANCH: ${name}() evaluates routes`);
      } else {
        whatHappensFirst.push(`ACTION: ${name}() in ${file}`);
      }
    });
  }

  if (whatHappensFirst.length === 0 && entryPoints.length > 0) {
    const ep = entryPoints[0];
    whatHappensFirst.push(
      `REQUEST / ENTRY: ${shortLabel(ep.id)}() in ${ep.file_path || 'source'}`
    );
  }

  // Developer-First Natural Language Synthesis
  const narrativeParagraphs: string[] = [];

  if (topFlow && topFlow.steps && topFlow.steps.length >= 2) {
    const entryStep = topFlow.steps[0];
    const intermediateSteps = topFlow.steps.slice(1, -1);
    const terminalStep = topFlow.steps[topFlow.steps.length - 1];

    if (intermediateSteps.length > 0) {
      const midNames = intermediateSteps.map((s) => `${s.label}()`).join(' and ');
      narrativeParagraphs.push(
        `Requests entering through ${entryStep.label}() typically flow through ${midNames} before reaching ${terminalStep.label}().`
      );
    } else {
      narrativeParagraphs.push(
        `Requests entering through ${entryStep.label}() execute directly into ${terminalStep.label}().`
      );
    }
  }

  if (highImpactNodes.length > 0) {
    const topHub = [...highImpactNodes].sort((a, b) => b.fan_in - a.fan_in)[0];
    narrativeParagraphs.push(
      `${shortLabel(topHub.id)}() is a high-impact execution symbol reached by ${topHub.fan_in} callers across ${flows.length} execution path(s).`
    );
  }

  if (recursiveNodes.length > 0) {
    narrativeParagraphs.push(
      `${recursiveNodes.length} recursive symbol(s) participate in cyclical call loops requiring termination guard verification.`
    );
  }

  const primaryFlowSummary = topFlow
    ? topFlow.steps?.map((s) => s.label).join(' → ') || topFlow.name
    : 'No active execution flows detected.';

  const summaryText = `${entryPoints.length} primary entry point${entryPoints.length === 1 ? '' : 's'} · ${flows.length} execution path${flows.length === 1 ? '' : 's'} · ${modules.size} module transition${modules.size === 1 ? '' : 's'} · ${recursiveNodes.length} recursive symbol${recursiveNodes.length === 1 ? '' : 's'}`;

  return {
    entryCount: entryPoints.length,
    pathCount: flows.length,
    moduleTransitionCount: modules.size,
    recursiveCycleCount: recursiveNodes.length > 0 ? Math.ceil(recursiveNodes.length / 2) : 0,
    highImpactCount: highImpactNodes.length,
    whatHappensFirst,
    narrativeParagraphs,
    primaryFlowSummary,
    summaryText,
  };
}

export function computeCallGraphSignals(
  nodes: CgNode[],
  edges: CgEdge[],
): CallGraphSignals {
  if (!nodes || nodes.length === 0) {
    return {
      totalFunctions: 0,
      totalEdges: 0,
      entryPointCount: 0,
      recursiveSymbolsCount: 0,
      recursiveClustersCount: 0,
      highFanInCount: 0,
      highFanOutCount: 0,
      hotspotsCount: 0,
      disconnectedCount: 0,
      ambiguousCount: 0,
      avgFanIn: 0,
      avgFanOut: 0,
      maxFanIn: 0,
      maxFanOut: 0,
      primaryEntryPoint: null,
      mostCentralSymbol: null,
      highestFanInSymbol: null,
      mostDownstreamSymbol: null,
      topologyStory: 'No functions analyzed.',
    };
  }

  const inDegreeMap = new Map<string, number>();
  const outDegreeMap = new Map<string, number>();

  nodes.forEach((n) => {
    inDegreeMap.set(n.id, 0);
    outDegreeMap.set(n.id, 0);
    n.execution_role = deriveExecutionRole(n);
  });

  let ambiguousEdges = 0;
  edges.forEach((e) => {
    if (e.ambiguous) ambiguousEdges++;
    if (inDegreeMap.has(e.target)) {
      inDegreeMap.set(e.target, (inDegreeMap.get(e.target) || 0) + 1);
    }
    if (outDegreeMap.has(e.source)) {
      outDegreeMap.set(e.source, (outDegreeMap.get(e.source) || 0) + 1);
    }
  });

  const entryPoints = nodes.filter(
    (n) => n.category === 'entry_point' || (n.fan_in === 0 && n.fan_out > 0)
  );

  const recursiveNodes = nodes.filter((n) => n.is_recursive);
  const recursiveClusters = findRecursiveClusters(nodes, edges);

  const highFanInNodes = nodes.filter((n) => n.fan_in >= 3);
  const highFanOutNodes = nodes.filter((n) => n.fan_out >= 3);
  const disconnectedNodes = nodes.filter((n) => {
    const inDeg = inDegreeMap.get(n.id) ?? n.fan_in;
    const outDeg = outDegreeMap.get(n.id) ?? n.fan_out;
    return inDeg === 0 && outDeg === 0;
  });

  let mostCentral: CgNode | null = null;
  let maxCentrality = -1;
  nodes.forEach((n) => {
    if (n.centrality > maxCentrality) {
      maxCentrality = n.centrality;
      mostCentral = n;
    }
  });

  let highestFanIn: CgNode | null = null;
  let maxFanInVal = -1;
  nodes.forEach((n) => {
    if (n.fan_in > maxFanInVal) {
      maxFanInVal = n.fan_in;
      highestFanIn = n;
    }
  });

  let mostDownstream: CgNode | null = null;
  let maxFanOutVal = -1;
  nodes.forEach((n) => {
    if (n.fan_out > maxFanOutVal) {
      maxFanOutVal = n.fan_out;
      mostDownstream = n;
    }
  });

  let primaryEntry: CgNode | null = null;
  if (entryPoints.length > 0) {
    primaryEntry = [...entryPoints].sort((a, b) => {
      const scoreA = a.fan_out * 2 + a.centrality * 10;
      const scoreB = b.fan_out * 2 + b.centrality * 10;
      return scoreB - scoreA;
    })[0];
  }

  const sumFanIn = nodes.reduce((acc, n) => acc + n.fan_in, 0);
  const sumFanOut = nodes.reduce((acc, n) => acc + n.fan_out, 0);
  const avgFanIn = nodes.length > 0 ? Number((sumFanIn / nodes.length).toFixed(1)) : 0;
  const avgFanOut = nodes.length > 0 ? Number((sumFanOut / nodes.length).toFixed(1)) : 0;

  const flows = extractExecutionFlows(nodes, edges, 5);
  const executionStory = generateExecutionStory(nodes, edges, flows);
  const failureBoundaries = extractFailureBoundaries(nodes, edges, flows);

  const storyParts: string[] = [
    `Call graph contains ${nodes.length} functions across ${edges.length} call edges.`,
  ];
  if (entryPoints.length > 0) {
    storyParts.push(
      `${entryPoints.length} root entry points initiate execution flow.`
    );
  }
  if (highestFanIn) {
    storyParts.push(
      `Primary architectural hub is ${shortLabel((highestFanIn as CgNode).id)} (${(highestFanIn as CgNode).fan_in} callers).`
    );
  }
  if (recursiveClusters.length > 0) {
    storyParts.push(
      `${recursiveNodes.length} symbols participate in ${recursiveClusters.length} recursive cycle(s).`
    );
  }

  return {
    totalFunctions: nodes.length,
    totalEdges: edges.length,
    entryPointCount: entryPoints.length,
    recursiveSymbolsCount: recursiveNodes.length,
    recursiveClustersCount: recursiveClusters.length,
    highFanInCount: highFanInNodes.length,
    highFanOutCount: highFanOutNodes.length,
    hotspotsCount: highFanInNodes.length + (mostCentral ? 1 : 0),
    disconnectedCount: disconnectedNodes.length,
    ambiguousCount: ambiguousEdges,
    avgFanIn,
    avgFanOut,
    maxFanIn: maxFanInVal >= 0 ? maxFanInVal : 0,
    maxFanOut: maxFanOutVal >= 0 ? maxFanOutVal : 0,
    primaryEntryPoint: primaryEntry,
    mostCentralSymbol: mostCentral,
    highestFanInSymbol: highestFanIn,
    mostDownstreamSymbol: mostDownstream,
    topologyStory: storyParts.join(' '),
    executionStory,
    failureBoundaries,
  };
}

// -----------------------------------------------------------------------------
// Execution Flow Extraction
// -----------------------------------------------------------------------------

export function extractExecutionFlows(
  nodes: CgNode[],
  edges: CgEdge[],
  maxFlows: number = 5,
): ExecutionFlow[] {
  if (!nodes || nodes.length === 0 || !edges || edges.length === 0) return [];

  const nodeMap = new Map<string, CgNode>(nodes.map((n) => [n.id, n]));
  const adj = new Map<string, string[]>();

  edges.forEach((e) => {
    const list = adj.get(e.source) || [];
    list.push(e.target);
    adj.set(e.source, list);
  });

  const entryPoints = nodes.filter(
    (n) => n.category === 'entry_point' || (n.fan_in === 0 && n.fan_out > 0)
  );

  const startNodes = entryPoints.length > 0 ? entryPoints : nodes.slice(0, 5);
  const discoveredPaths: { path: string[]; score: number; reason: string }[] = [];

  startNodes.forEach((startNode) => {
    const queue: { current: string; path: string[]; depth: number }[] = [
      { current: startNode.id, path: [startNode.id], depth: 0 },
    ];

    while (queue.length > 0 && queue.length < 200) {
      const { current, path, depth } = queue.shift()!;
      const neighbors = adj.get(current) || [];

      if (neighbors.length === 0 || depth >= 7) {
        if (path.length >= 2) {
          let score = 10;
          const modules = new Set<string>();
          let hasHighCentrality = false;
          let hasHighFanIn = false;

          path.forEach((id) => {
            const n = nodeMap.get(id);
            if (n) {
              score += (n.centrality || 0) * 20 + (n.fan_in || 0) * 2 + (n.fan_out || 0);
              if (n.centrality >= 0.3) hasHighCentrality = true;
              if (n.fan_in >= 3) hasHighFanIn = true;
              modules.add(getModule(n));
            }
          });

          score += modules.size * 5;
          score += path.length * 2;

          const reasonParts: string[] = [];
          if (startNode.category === 'entry_point' || startNode.fan_in === 0) {
            reasonParts.push('begins at an entry point');
          }
          if (hasHighCentrality) {
            reasonParts.push('traverses high-centrality symbols');
          }
          if (hasHighFanIn) {
            reasonParts.push('crosses high fan-in hubs');
          }
          if (modules.size > 1) {
            reasonParts.push(`spans ${modules.size} architectural modules`);
          }

          const rankingReason =
            reasonParts.length > 0
              ? `Starts from an entry point and reaches a terminal state across ${reasonParts.join(' and ')}.`
              : 'Direct execution trace from entry root.';

          discoveredPaths.push({ path, score, reason: rankingReason });
        }
        continue;
      }

      const sortedNeighbors = [...neighbors].sort((a, b) => {
        const na = nodeMap.get(a);
        const nb = nodeMap.get(b);
        const sa = (na?.centrality || 0) * 10 + (na?.fan_out || 0);
        const sb = (nb?.centrality || 0) * 10 + (nb?.fan_out || 0);
        return sb - sa;
      });

      for (const next of sortedNeighbors.slice(0, 3)) {
        if (!path.includes(next)) {
          queue.push({
            current: next,
            path: [...path, next],
            depth: depth + 1,
          });
        }
      }
    }
  });

  discoveredPaths.sort((a, b) => b.score - a.score);

  const uniqueFlows: ExecutionFlow[] = [];
  const seenSignatures = new Set<string>();

  for (const item of discoveredPaths) {
    const signature = `${item.path[0]}->${item.path[item.path.length - 1]}`;
    if (seenSignatures.has(signature) && uniqueFlows.length >= maxFlows) continue;
    seenSignatures.add(signature);

    const startId = item.path[0];
    const endId = item.path[item.path.length - 1];

    const modules = new Set<string>();
    const steps: FlowStep[] = item.path.map((id, idx) => {
      const n = nodeMap.get(id);
      modules.add(getModule(n));
      const role = n ? deriveExecutionRole(n) : 'CALL';
      return {
        nodeId: id,
        label: n ? shortLabel(n.id) : id,
        filePath: n?.file_path || 'source',
        role,
        isEntry: idx === 0,
        isTerminal: idx === item.path.length - 1,
      };
    });

    const riskSignals: string[] = [];
    item.path.forEach((id) => {
      const n = nodeMap.get(id);
      if (n?.is_recursive) riskSignals.push(`Recursive symbol: ${shortLabel(n.id)}()`);
      if (n && n.fan_in >= 5) riskSignals.push(`High fan-in hub: ${shortLabel(n.id)}()`);
    });

    const name = steps.map((s) => s.label).join(' → ');

    uniqueFlows.push({
      id: `flow-${uniqueFlows.length + 1}`,
      name,
      path: item.path,
      length: item.path.length,
      crossModuleCount: modules.size,
      rankingReason: item.reason,
      entryNodeId: startId,
      targetNodeId: endId,
      score: item.score,
      steps,
      riskSignals: Array.from(new Set(riskSignals)),
    });

    if (uniqueFlows.length >= maxFlows) break;
  }

  if (uniqueFlows.length === 0 && nodes.length > 0) {
    const root = startNodes[0] || nodes[0];
    uniqueFlows.push({
      id: 'flow-1',
      name: `${shortLabel(root.id)} execution flow`,
      path: [root.id],
      length: 1,
      crossModuleCount: 1,
      rankingReason: 'Primary detected executable root.',
      entryNodeId: root.id,
      targetNodeId: root.id,
      score: 1,
      steps: [
        {
          nodeId: root.id,
          label: shortLabel(root.id),
          filePath: root.file_path || 'source',
          role: 'ENTRY',
          isEntry: true,
          isTerminal: true,
        },
      ],
      riskSignals: [],
    });
  }

  return uniqueFlows;
}

// -----------------------------------------------------------------------------
// Branch Points Extraction
// -----------------------------------------------------------------------------

export function extractBranchPoints(
  nodes: CgNode[],
  edges: CgEdge[],
): BranchPoint[] {
  const branchNodes = nodes.filter((n) => n.fan_out >= 2);
  const nodeMap = new Map<string, CgNode>(nodes.map((n) => [n.id, n]));
  const branchMap = new Map<string, CgEdge[]>();

  edges.forEach((e) => {
    const list = branchMap.get(e.source) || [];
    list.push(e);
    branchMap.set(e.source, list);
  });

  const branchPoints: BranchPoint[] = [];

  branchNodes.forEach((node) => {
    const outEdges = branchMap.get(node.id) || [];
    if (outEdges.length >= 2) {
      const divergentBranches = outEdges.map((e) => {
        const target = nodeMap.get(e.target) || {
          id: e.target,
          label: shortLabel(e.target),
          category: 'regular',
          degree: 0,
          centrality: 0,
          fan_in: 0,
          fan_out: 0,
          is_recursive: false,
          symbol_type: 'function',
        };

        const targetShort = shortLabel(e.target);
        return {
          targetId: e.target,
          targetNode: target,
          downstreamCount: target.fan_out || 0,
          description: `Dispatches execution to ${targetShort}() in ${target.file_path || 'source'}`,
        };
      });

      branchPoints.push({
        nodeId: node.id,
        node,
        divergentBranches,
        branchCount: divergentBranches.length,
        reason: `Evaluates conditional execution branching into ${divergentBranches.length} distinct targets.`,
      });
    }
  });

  return branchPoints.sort((a, b) => b.branchCount - a.branchCount);
}

// -----------------------------------------------------------------------------
// Behavioral Change Simulation
// -----------------------------------------------------------------------------

export function simulateChangeImpact(
  targetId: string,
  nodes: CgNode[],
  edges: CgEdge[],
): ChangeSimulationImpact {
  const nodeMap = new Map<string, CgNode>(nodes.map((n) => [n.id, n]));
  const targetNode = nodeMap.get(targetId) || {
    id: targetId,
    label: shortLabel(targetId),
    category: 'regular',
    degree: 0,
    centrality: 0,
    fan_in: 0,
    fan_out: 0,
    is_recursive: false,
    symbol_type: 'function',
  };

  const flows = extractExecutionFlows(nodes, edges, 10);
  const affectedEntryPaths = flows.filter((f) => f.path.includes(targetId));

  // Upstream callers
  const parentMap = new Map<string, string[]>();
  const childMap = new Map<string, string[]>();
  edges.forEach((e) => {
    const pList = parentMap.get(e.target) || [];
    pList.push(e.source);
    parentMap.set(e.target, pList);

    const cList = childMap.get(e.source) || [];
    cList.push(e.target);
    childMap.set(e.source, cList);
  });

  const upstreamCallers = parentMap.get(targetId) || [];

  // Downstream cascade BFS
  const visited = new Set<string>();
  const queue: string[] = [targetId];
  const affectedFiles = new Set<string>();
  const affectedTests: string[] = [];

  if (targetNode.file_path) affectedFiles.add(targetNode.file_path);

  while (queue.length > 0) {
    const current = queue.shift()!;
    const children = childMap.get(current) || [];

    for (const childId of children) {
      if (!visited.has(childId)) {
        visited.add(childId);
        const childNode = nodeMap.get(childId);
        if (childNode?.file_path) {
          affectedFiles.add(childNode.file_path);
          if (
            childNode.file_path.includes('test') ||
            childNode.label.startsWith('test_')
          ) {
            affectedTests.push(childNode.label);
          }
        }
        queue.push(childId);
      }
    }
  }

  const cascadeList = Array.from(visited);
  const downstreamCount = cascadeList.length;

  let riskRating: 'Low' | 'Medium' | 'High' | 'Critical' = 'Low';
  if (targetNode.is_recursive || affectedEntryPaths.length >= 3 || downstreamCount >= 8) {
    riskRating = 'Critical';
  } else if (affectedEntryPaths.length >= 2 || downstreamCount >= 4 || targetNode.fan_in >= 4) {
    riskRating = 'High';
  } else if (downstreamCount >= 2 || targetNode.fan_in >= 2) {
    riskRating = 'Medium';
  }

  const narrativeImpact = `Modifying ${shortLabel(targetId)}() impacts ${affectedEntryPaths.length} entry flow(s), cascades into ${downstreamCount} downstream function(s) across ${affectedFiles.size} file(s), and exercises ${affectedTests.length} test suite(s).`;

  return {
    targetId,
    targetNode,
    affectedEntryPaths,
    upstreamCallers,
    upstreamCount: upstreamCallers.length,
    downstreamCascade: cascadeList,
    downstreamCount,
    alternateRoutesCount: Math.max(0, targetNode.fan_out - 1),
    isRecursive: Boolean(targetNode.is_recursive),
    affectedFiles: Array.from(affectedFiles),
    affectedFileCount: affectedFiles.size,
    affectedTests: Array.from(new Set(affectedTests)),
    riskRating,
    staticGraphImpact: true,
    narrativeImpact,
  };
}

// -----------------------------------------------------------------------------
// Progressive Graph Abstraction & Execution Graph Builder
// -----------------------------------------------------------------------------

export function buildAbstractedCallGraph(
  nodes: CgNode[],
  edges: CgEdge[],
  level: CgAbstractionLevel | CgInvestigationMode,
  selectedNodeId: string | null = null,
  activeFlow: ExecutionFlow | null = null,
): { nodes: CgNode[]; edges: CgEdge[]; flows: ExecutionFlow[]; clusters: RecursiveCluster[] } {
  const flows = extractExecutionFlows(nodes, edges, 8);
  const clusters = findRecursiveClusters(nodes, edges);

  if (level === 'symbols' || level === 'symbol_detail') {
    return { nodes, edges, flows, clusters };
  }

  if (level === 'flows' || level === 'execution_flows') {
    const flowNodeIds = new Set<string>();

    if (activeFlow) {
      activeFlow.path.forEach((id) => flowNodeIds.add(id));
    } else {
      flows.slice(0, 4).forEach((f) => f.path.forEach((id) => flowNodeIds.add(id)));
    }

    nodes.forEach((n) => {
      if (n.category === 'entry_point' || n.fan_in >= 4 || n.centrality >= 0.25 || n.is_recursive) {
        flowNodeIds.add(n.id);
      }
      if (selectedNodeId && n.id === selectedNodeId) {
        flowNodeIds.add(n.id);
      }
    });

    const filteredNodes = nodes.filter((n) => flowNodeIds.has(n.id));
    const allowedIds = new Set(filteredNodes.map((n) => n.id));
    const filteredEdges = edges.filter((e) => allowedIds.has(e.source) && allowedIds.has(e.target));

    return {
      nodes: filteredNodes.length > 0 ? filteredNodes : nodes,
      edges: filteredEdges.length > 0 ? filteredEdges : edges,
      flows,
      clusters,
    };
  }

  // Network mode
  const connectedIds = new Set<string>();
  edges.forEach((e) => {
    connectedIds.add(e.source);
    connectedIds.add(e.target);
  });

  const networkNodes = nodes.filter(
    (n) => connectedIds.has(n.id) || n.id === selectedNodeId || n.category === 'entry_point'
  );
  const allowedNetworkIds = new Set(networkNodes.map((n) => n.id));
  const networkEdges = edges.filter(
    (e) => allowedNetworkIds.has(e.source) && allowedNetworkIds.has(e.target)
  );

  return {
    nodes: networkNodes.length > 0 ? networkNodes : nodes,
    edges: networkEdges.length > 0 ? networkEdges : edges,
    flows,
    clusters,
  };
}

// -----------------------------------------------------------------------------
// Trace Path Reconstruction
// -----------------------------------------------------------------------------

export function tracePathToNode(
  targetId: string,
  nodes: CgNode[],
  edges: CgEdge[],
  direction: 'upstream' | 'downstream' | 'both' = 'upstream',
): string[] {
  if (!targetId || !nodes || nodes.length === 0) return [];

  const nodeMap = new Map<string, CgNode>(nodes.map((n) => [n.id, n]));
  const targetNode = nodeMap.get(targetId);
  if (!targetNode) return [targetId];

  if (direction === 'upstream') {
    const parentMap = new Map<string, string[]>();
    edges.forEach((e) => {
      const list = parentMap.get(e.target) || [];
      list.push(e.source);
      parentMap.set(e.target, list);
    });

    const queue: { current: string; path: string[] }[] = [
      { current: targetId, path: [targetId] },
    ];
    const visited = new Set<string>([targetId]);
    let bestPath: string[] = [targetId];

    while (queue.length > 0) {
      const { current, path } = queue.shift()!;
      const parents = parentMap.get(current) || [];

      if (parents.length === 0) {
        if (path.length > bestPath.length) {
          bestPath = path;
        }
        continue;
      }

      for (const p of parents) {
        if (!visited.has(p)) {
          visited.add(p);
          const newPath = [p, ...path];
          const parentNode = nodeMap.get(p);
          if (parentNode?.category === 'entry_point' || parentNode?.fan_in === 0) {
            return newPath;
          }
          queue.push({ current: p, path: newPath });
          if (newPath.length > bestPath.length) {
            bestPath = newPath;
          }
        }
      }
    }

    return bestPath;
  }

  const childMap = new Map<string, string[]>();
  edges.forEach((e) => {
    const list = childMap.get(e.source) || [];
    list.push(e.target);
    childMap.set(e.source, list);
  });

  const queue: { current: string; path: string[] }[] = [
    { current: targetId, path: [targetId] },
  ];
  const visited = new Set<string>([targetId]);
  let longestPath: string[] = [targetId];

  while (queue.length > 0) {
    const { current, path } = queue.shift()!;
    const children = childMap.get(current) || [];

    if (children.length === 0) {
      if (path.length > longestPath.length) {
        longestPath = path;
      }
      continue;
    }

    for (const c of children) {
      if (!visited.has(c)) {
        visited.add(c);
        const newPath = [...path, c];
        queue.push({ current: c, path: newPath });
        if (newPath.length > longestPath.length) {
          longestPath = newPath;
        }
      }
    }
  }

  return longestPath;
}

export function traceDetailedRoute(
  path: string[],
  nodes: CgNode[],
  edges: CgEdge[],
  targetId: string,
): TraceRouteDetails {
  const nodeMap = new Map<string, CgNode>(nodes.map((n) => [n.id, n]));
  const ambiguousSet = new Set(
    edges.filter((e) => e.ambiguous).map((e) => `${e.source}->${e.target}`)
  );

  const modules = new Set<string>();
  let hasRecursive = false;
  let hasAmbiguous = false;

  const targetIdx = path.indexOf(targetId);
  const upstreamPath = targetIdx >= 0 ? path.slice(0, targetIdx + 1) : [targetId];
  const downstreamPath = targetIdx >= 0 ? path.slice(targetIdx) : [targetId];

  const steps = path.map((id) => {
    const n = nodeMap.get(id);
    if (n) {
      modules.add(getModule(n));
      if (n.is_recursive) hasRecursive = true;
    }
    return {
      nodeId: id,
      label: n ? shortLabel(n.id) : id,
      filePath: n?.file_path || 'unknown',
      role: n ? deriveExecutionRole(n) : 'CALL',
      isEntryPoint: n?.category === 'entry_point' || (n?.fan_in === 0 && (n?.fan_out || 0) > 0),
      isTarget: id === targetId,
    };
  });

  for (let i = 0; i < path.length - 1; i++) {
    const key = `${path[i]}->${path[i + 1]}`;
    if (ambiguousSet.has(key)) hasAmbiguous = true;
  }

  return {
    path,
    pathLength: path.length,
    moduleCrossings: Math.max(0, modules.size - 1),
    hasRecursiveEdges: hasRecursive,
    hasAmbiguousEdges: hasAmbiguous,
    upstreamPath,
    downstreamPath,
    steps,
  };
}

// -----------------------------------------------------------------------------
// Recursion Cycle Diagnostics
// -----------------------------------------------------------------------------

export function findRecursiveClusters(
  nodes: CgNode[],
  edges: CgEdge[],
): RecursiveCluster[] {
  const clusters: RecursiveCluster[] = [];
  const nodeMap = new Map<string, CgNode>(nodes.map((n) => [n.id, n]));

  // 1. Self-recursive loops: foo() ↺ foo()
  edges.forEach((e) => {
    if (e.source === e.target) {
      const n = nodeMap.get(e.source);
      clusters.push({
        id: `rec-self-${e.source}`,
        name: `Self-Recursion: ${shortLabel(e.source)}() ↺`,
        symbols: [e.source],
        cycleLength: 1,
        files: n?.file_path ? [n.file_path] : [],
        isSelfLoop: true,
        reachableFromEntry: (n?.fan_in || 0) > 0,
      });
    }
  });

  // 2. Mutual cycles: foo() ↕ bar()
  const edgePairSet = new Set(edges.map((e) => `${e.source}#${e.target}`));
  const processedPairs = new Set<string>();

  edges.forEach((e) => {
    if (e.source !== e.target && edgePairSet.has(`${e.target}#${e.source}`)) {
      const pairKey = [e.source, e.target].sort().join('::');
      if (!processedPairs.has(pairKey)) {
        processedPairs.add(pairKey);
        const nodeA = nodeMap.get(e.source);
        const nodeB = nodeMap.get(e.target);
        const files = Array.from(
          new Set([nodeA?.file_path, nodeB?.file_path].filter(Boolean) as string[])
        );

        clusters.push({
          id: `rec-mutual-${pairKey}`,
          name: `Mutual Recursion: ${shortLabel(e.source)}() ↕ ${shortLabel(e.target)}()`,
          symbols: [e.source, e.target],
          cycleLength: 2,
          files,
          isSelfLoop: false,
          reachableFromEntry: true,
        });
      }
    }
  });

  return clusters;
}

// -----------------------------------------------------------------------------
// Hot Paths Ranking
// -----------------------------------------------------------------------------

export function rankHotspots(
  nodes: CgNode[],
  edges: CgEdge[],
  scope: 'top5' | 'top10' | 'all' = 'top10',
): HotspotNode[] {
  const flows = extractExecutionFlows(nodes, edges, 10);
  const participationCount = new Map<string, number>();

  flows.forEach((f) => {
    f.path.forEach((id) => {
      participationCount.set(id, (participationCount.get(id) || 0) + 1);
    });
  });

  const scored = nodes.map((n) => {
    const paths = participationCount.get(n.id) || 0;
    const score =
      paths * 10 +
      n.fan_in * 3.5 +
      n.fan_out * 1.5 +
      (n.centrality || 0) * 30 +
      (n.is_recursive ? 15 : 0) +
      (n.category === 'entry_point' ? 5 : 0);

    const reasons: string[] = [];
    if (paths > 0) reasons.push(`Reached by ${paths} entry execution flow(s)`);
    if (n.fan_in >= 4) reasons.push(`${n.fan_in} inbound callers`);
    if (n.fan_out >= 4) reasons.push(`${n.fan_out} downstream routes`);
    if ((n.centrality || 0) >= 0.25) {
      reasons.push(`${((n.centrality || 0) * 100).toFixed(0)}% route centrality`);
    }

    return {
      node: n,
      rank: 0,
      hotspotScore: score,
      fanIn: n.fan_in,
      fanOut: n.fan_out,
      centrality: n.centrality || 0,
      pathParticipationCount: paths,
      riskReason: reasons.length > 0 ? reasons.join(' · ') : 'Moderate route connectivity',
    };
  });

  scored.sort((a, b) => b.hotspotScore - a.hotspotScore);

  const ranked = scored.map((item, idx) => ({ ...item, rank: idx + 1 }));

  if (scope === 'top5') return ranked.slice(0, 5);
  if (scope === 'top10') return ranked.slice(0, 10);
  return ranked;
}

// -----------------------------------------------------------------------------
// Dynamic Repository-Grounded Prompt Generation
// -----------------------------------------------------------------------------

export function generateCallGraphQuestions(
  node: CgNode,
  signals: CallGraphSignals,
): string[] {
  const questions: string[] = [];
  const sName = shortLabel(node.id);
  const fPath = node.file_path || 'source';

  if (node.category === 'entry_point' || node.fan_in === 0) {
    questions.push(
      `Which downstream execution paths are initiated by root entry function ${sName}() in ${fPath}?`
    );
  } else if (node.fan_in > 0) {
    questions.push(
      `Which entry points eventually invoke ${sName}() in ${fPath}?`
    );
  }

  if (node.is_recursive) {
    questions.push(
      `How does ${sName}() terminate its recursive cycle without stack overflow?`
    );
  } else if (node.fan_in >= 4) {
    questions.push(
      `What execution paths change if ${sName}() fails or alters its return contract?`
    );
  } else if (node.fan_out >= 3) {
    questions.push(
      `How does ${sName}() reach the persistence or side-effect layer across its ${node.fan_out} callees?`
    );
  } else {
    questions.push(
      `What tests in the repository exercise ${sName}() in ${fPath}?`
    );
  }

  if (signals.primaryEntryPoint && signals.primaryEntryPoint.id !== node.id) {
    questions.push(
      `How does execution flow from primary entry ${shortLabel(signals.primaryEntryPoint.id)} down to ${sName}()?`
    );
  } else {
    questions.push(
      `How is error handling and propagation structured around ${sName}()?`
    );
  }

  const unique = Array.from(new Set(questions));
  while (unique.length < 3) {
    unique.push(`How does ${sName}() interact with other execution modules in ${fPath}?`);
  }
  return unique.slice(0, 3);
}

// -----------------------------------------------------------------------------
// Confidence & Narrative Derivations
// -----------------------------------------------------------------------------

export function deriveConfidenceLevel(
  node: CgNode,
): 'VERIFIED' | 'STRONGLY INFERRED' | 'INFERRED' | 'UNKNOWN' {
  if (node.symbol_type === 'function' || node.symbol_type === 'method') {
    return 'VERIFIED';
  }
  if (node.file_path) {
    return 'STRONGLY INFERRED';
  }
  return 'INFERRED';
}

export function generateWhyItMatters(
  node: CgNode,
  signals: CallGraphSignals,
): string {
  const parts: string[] = [];

  if (node.category === 'entry_point' || (node.fan_in === 0 && node.fan_out > 0)) {
    parts.push(
      `Root execution gateway initiating ${node.fan_out} downstream execution chain(s).`
    );
  } else if (node.fan_in >= 5) {
    parts.push(
      `High-participation execution symbol sitting on multiple execution routes with ${node.fan_in} direct callers.`
    );
  }

  if (node.is_recursive) {
    parts.push(
      `Participates in recursive call cycles requiring termination guarantee verification.`
    );
  }

  if (node.centrality >= 0.25) {
    parts.push(
      `Key inter-module bridge (${(node.centrality * 100).toFixed(1)}% route centrality) determining downstream execution targets.`
    );
  }

  if (parts.length === 0) {
    parts.push(
      `Executes within ${node.file_path || 'local'} execution flow with ${node.fan_in} caller(s) and ${node.fan_out} callee(s).`
    );
  }

  return parts.join(' ');
}

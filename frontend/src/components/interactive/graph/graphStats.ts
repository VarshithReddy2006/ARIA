/**
 * Pure client-side graph statistics over the API response.
 * Derives accurate counts, centralities, cycle clusters, and blast radii from nodes & edges.
 */

import type { GraphEdge, GraphNode, GraphSignals, BlastRadiusResult } from './types';

interface Stats {
  components: number;
  /** Number of strongly-connected components with size > 1 — i.e. cycle clusters */
  cycleClusters: number;
}

export function computeGraphStats(nodes: GraphNode[], edges: GraphEdge[]): Stats {
  if (nodes.length === 0) return { components: 0, cycleClusters: 0 };

  // Undirected adjacency for weakly-connected components
  const undirected = new Map<string, Set<string>>();
  nodes.forEach((n) => undirected.set(n.id, new Set()));
  edges.forEach((e) => {
    undirected.get(e.source)?.add(e.target);
    undirected.get(e.target)?.add(e.source);
  });

  // BFS-count connected components
  const seen = new Set<string>();
  let components = 0;
  for (const n of nodes) {
    if (seen.has(n.id)) continue;
    components++;
    const queue: string[] = [n.id];
    seen.add(n.id);
    while (queue.length) {
      const cur = queue.shift()!;
      const neighbours = undirected.get(cur);
      if (!neighbours) continue;
      neighbours.forEach((next) => {
        if (!seen.has(next)) {
          seen.add(next);
          queue.push(next);
        }
      });
    }
  }

  // Tarjan's SCC over the DIRECTED graph
  const directed = new Map<string, string[]>();
  nodes.forEach((n) => directed.set(n.id, []));
  edges.forEach((e) => directed.get(e.source)?.push(e.target));

  const index = new Map<string, number>();
  const lowlink = new Map<string, number>();
  const onStack = new Set<string>();
  const stack: string[] = [];
  let counter = 0;
  let cycleClusters = 0;

  // Iterative Tarjan to avoid stack overflow on big graphs
  function strongConnect(start: string) {
    type Frame = { node: string; i: number };
    const frames: Frame[] = [{ node: start, i: 0 }];
    index.set(start, counter);
    lowlink.set(start, counter);
    counter++;
    stack.push(start);
    onStack.add(start);

    while (frames.length) {
      const frame = frames[frames.length - 1];
      const targets = directed.get(frame.node) ?? [];
      if (frame.i < targets.length) {
        const w = targets[frame.i++];
        if (!index.has(w)) {
          index.set(w, counter);
          lowlink.set(w, counter);
          counter++;
          stack.push(w);
          onStack.add(w);
          frames.push({ node: w, i: 0 });
        } else if (onStack.has(w)) {
          lowlink.set(frame.node, Math.min(lowlink.get(frame.node)!, index.get(w)!));
        }
      } else {
        if (lowlink.get(frame.node) === index.get(frame.node)) {
          let size = 0;
          let w: string;
          do {
            w = stack.pop()!;
            onStack.delete(w);
            size++;
          } while (w !== frame.node);
          if (size > 1) cycleClusters++;
        }
        frames.pop();
        if (frames.length) {
          const parent = frames[frames.length - 1];
          lowlink.set(parent.node, Math.min(lowlink.get(parent.node)!, lowlink.get(frame.node)!));
        }
      }
    }
  }

  for (const n of nodes) {
    if (!index.has(n.id)) strongConnect(n.id);
  }

  return { components, cycleClusters };
}

/**
 * Computes architectural signals across the loaded graph.
 */
export function computeGraphSignals(nodes: GraphNode[], edges: GraphEdge[]): GraphSignals {
  if (nodes.length === 0) {
    return {
      mostCentralNode: null,
      highestCouplingNode: null,
      entryPointCount: 0,
      hotspotCount: 0,
      cycleClusterCount: 0,
      components: 0,
      architecturalStory: 'No indexed graph evidence available.',
    };
  }

  const { components, cycleClusters } = computeGraphStats(nodes, edges);

  // In-degree & Out-degree maps
  const inDegreeMap = new Map<string, number>();
  const outDegreeMap = new Map<string, number>();
  nodes.forEach((n) => {
    inDegreeMap.set(n.id, 0);
    outDegreeMap.set(n.id, 0);
  });
  edges.forEach((e) => {
    outDegreeMap.set(e.source, (outDegreeMap.get(e.source) ?? 0) + 1);
    inDegreeMap.set(e.target, (inDegreeMap.get(e.target) ?? 0) + 1);
  });

  // Most central node (by centrality or degree)
  let mostCentral: GraphNode | null = null;
  let maxCentrality = -1;
  nodes.forEach((n) => {
    const c = n.centrality > 0 ? n.centrality : (n.degree / Math.max(nodes.length, 1));
    if (c > maxCentrality) {
      maxCentrality = c;
      mostCentral = n;
    }
  });

  // Highest coupling node (in + out degree)
  let highestCoupling: GraphNode | null = null;
  let maxDegree = -1;
  nodes.forEach((n) => {
    const totalDeg = (inDegreeMap.get(n.id) ?? 0) + (outDegreeMap.get(n.id) ?? 0);
    if (totalDeg > maxDegree) {
      maxDegree = totalDeg;
      highestCoupling = n;
    }
  });

  // Entry points: explicit entry_point category or in_degree == 0 with out_degree > 0
  const entryPointNodes = nodes.filter((n) => {
    if (n.category === 'entry_point') return true;
    const inDeg = inDegreeMap.get(n.id) ?? 0;
    const outDeg = outDegreeMap.get(n.id) ?? 0;
    return inDeg === 0 && outDeg > 0;
  });

  // Hotspots: high_coupling or degree >= 8 or centrality >= 0.15
  const hotspotNodes = nodes.filter((n) => {
    if (n.category === 'high_coupling') return true;
    const totalDeg = (inDegreeMap.get(n.id) ?? 0) + (outDegreeMap.get(n.id) ?? 0);
    return totalDeg >= 8 || n.centrality >= 0.15;
  });

  // Construct truthful architectural storytelling
  const centralLabel = mostCentral ? ((mostCentral as GraphNode).label || (mostCentral as GraphNode).id.split('/').pop()) : 'central module';
  const centralPct = maxCentrality >= 0 ? `${(maxCentrality * 100).toFixed(1)}%` : 'N/A';
  const story = `ARIA identified ${components} architectural ${components === 1 ? 'component' : 'components'} across ${nodes.length} files. ${entryPointNodes.length} primary ${entryPointNodes.length === 1 ? 'entry point' : 'entry points'} route through central orchestrator ${centralLabel} (centrality ${centralPct}), with ${hotspotNodes.length} high-coupling ${hotspotNodes.length === 1 ? 'module' : 'modules'} and ${cycleClusters} cycle ${cycleClusters === 1 ? 'cluster' : 'clusters'} detected.`;

  return {
    mostCentralNode: mostCentral
      ? { id: (mostCentral as GraphNode).id, label: (mostCentral as GraphNode).label || (mostCentral as GraphNode).id.split('/').pop() || '', centrality: maxCentrality }
      : null,
    highestCouplingNode: highestCoupling
      ? { id: (highestCoupling as GraphNode).id, label: (highestCoupling as GraphNode).label || (highestCoupling as GraphNode).id.split('/').pop() || '', degree: maxDegree }
      : null,
    entryPointCount: entryPointNodes.length,
    hotspotCount: hotspotNodes.length,
    cycleClusterCount: cycleClusters,
    components,
    architecturalStory: story,
  };
}

/**
 * Computes downstream blast radius for a given node via reverse BFS.
 * When node X changes, all nodes that directly or transitively IMPORT / DEPEND on X are affected.
 */
export function computeBlastRadius(
  nodeId: string,
  edges: GraphEdge[],
  nodes: GraphNode[],
): BlastRadiusResult {
  // Reverse adjacency: target -> list of sources (who imports target)
  const incoming = new Map<string, string[]>();
  nodes.forEach((n) => incoming.set(n.id, []));
  edges.forEach((e) => incoming.get(e.target)?.push(e.source));

  const direct = incoming.get(nodeId) ?? [];
  const directSet = new Set(direct);

  const transitive: string[] = [];
  const visited = new Set<string>([nodeId]);
  const queue: string[] = [...direct];
  direct.forEach((d) => visited.add(d));

  while (queue.length > 0) {
    const cur = queue.shift()!;
    const callers = incoming.get(cur) ?? [];
    for (const caller of callers) {
      if (!visited.has(caller)) {
        visited.add(caller);
        transitive.push(caller);
        queue.push(caller);
      }
    }
  }

  const totalAffected = direct.length + transitive.length;
  const blastRadiusPct = nodes.length > 0 ? (totalAffected / nodes.length) * 100 : 0;

  // Determine affected entry points
  const entryPoints = nodes
    .filter((n) => n.category === 'entry_point' && visited.has(n.id) && n.id !== nodeId)
    .map((n) => n.id);

  // Determine affected components (unique directories)
  const affectedDirs = new Set<string>();
  visited.forEach((id) => {
    if (id.includes('/')) {
      affectedDirs.add(id.substring(0, id.lastIndexOf('/')));
    }
  });

  let riskLevel: 'Low' | 'Medium' | 'High' | 'Critical' = 'Low';
  if (blastRadiusPct > 40 || totalAffected >= 20) riskLevel = 'Critical';
  else if (blastRadiusPct > 20 || totalAffected >= 10) riskLevel = 'High';
  else if (blastRadiusPct > 5 || totalAffected >= 3) riskLevel = 'Medium';

  return {
    nodeId,
    directDependents: direct,
    transitiveDependents: transitive,
    directCount: direct.length,
    transitiveCount: transitive.length,
    totalAffectedCount: totalAffected,
    blastRadiusPct: Math.round(blastRadiusPct * 10) / 10,
    affectedComponentsCount: affectedDirs.size,
    affectedEntryPoints: entryPoints,
    riskLevel,
  };
}

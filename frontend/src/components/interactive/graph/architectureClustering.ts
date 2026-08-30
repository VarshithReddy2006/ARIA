/**
 * Architecture Clustering & Progressive Detail Engine
 * 
 * Provides evidence-based visual clustering and progressive abstraction levels:
 * - Level 1: SYSTEM (High-level architecture clusters & inter-cluster relationships)
 * - Level 2: COMPONENTS (Expanded active clusters + key internal files)
 * - Level 3: FILES (Full file-level dependency topology)
 */

import type { GraphNode, GraphEdge, ArchitectureCluster, AbstractionLevel } from './types.ts';

/**
 * Derives a clean architectural cluster ID and category for any file path.
 */
export function getClusterId(node: GraphNode): string {
  const path = node.id.replace(/\\/g, '/');
  const parts = path.split('/').filter(Boolean);

  if (parts.length <= 1) {
    if (node.category === 'entry_point') return 'Entry Points';
    return 'Root Modules';
  }

  if (parts.length >= 3) {
    return `${parts[0]}/${parts[1]}`;
  }

  return parts[0];
}

/**
 * Derives an evidence-based primary architectural role for a cluster.
 */
export function deriveClusterRole(clusterId: string, nodes: GraphNode[]): string {
  const norm = clusterId.toLowerCase();

  if (norm.includes('api') || norm.includes('routes') || norm.includes('controllers') || norm.includes('server')) {
    return 'API Gateways & Request Routing';
  }
  if (norm.includes('domain') || norm.includes('models') || norm.includes('entities') || norm.includes('core')) {
    return 'Domain Logic & Entity Transformations';
  }
  if (norm.includes('services') || norm.includes('features') || norm.includes('engine')) {
    return 'Business Services & Processing Pipelines';
  }
  if (norm.includes('infra') || norm.includes('db') || norm.includes('storage') || norm.includes('clients')) {
    return 'Infrastructure & External Integrations';
  }
  if (norm.includes('util') || norm.includes('helpers') || norm.includes('common') || norm.includes('shared')) {
    return 'Shared Utilities & Cross-Cutting Libs';
  }
  if (norm.includes('test') || norm.includes('spec') || norm.includes('e2e')) {
    return 'Test Suites & Verification Fixtures';
  }
  if (norm.includes('config') || norm.includes('settings')) {
    return 'Configuration & Environment Definitions';
  }
  if (norm.includes('worker') || norm.includes('jobs') || norm.includes('tasks')) {
    return 'Background Workers & Async Processing';
  }

  // Count majority category if directory is non-standard
  const catCounts = new Map<string, number>();
  nodes.forEach((n) => catCounts.set(n.category, (catCounts.get(n.category) ?? 0) + 1));
  let topCat = 'regular';
  let maxCount = 0;
  catCounts.forEach((count, cat) => {
    if (count > maxCount) {
      maxCount = count;
      topCat = cat;
    }
  });

  if (topCat === 'entry_point') return 'Application Roots & Entry Points';
  if (topCat === 'core_module') return 'Core Orchestration Components';
  if (topCat === 'service') return 'Service Layer Operations';
  if (topCat === 'high_coupling') return 'High-Connectivity Integration Hubs';

  return 'Component Subsystem & Internal Modules';
}

/**
 * Builds architecture clusters from raw repository nodes and edges.
 */
export function buildArchitectureClusters(
  nodes: GraphNode[],
  edges: GraphEdge[],
  expandedClusterIds: Set<string> = new Set(),
): ArchitectureCluster[] {
  if (!nodes || nodes.length === 0) return [];

  const clusterMap = new Map<string, GraphNode[]>();

  nodes.forEach((n) => {
    const cId = getClusterId(n);
    if (!clusterMap.has(cId)) clusterMap.set(cId, []);
    clusterMap.get(cId)!.push(n);
  });

  // Build node to cluster map for edge counting
  const nodeToCluster = new Map<string, string>();
  clusterMap.forEach((cNodes, cId) => {
    cNodes.forEach((n) => nodeToCluster.set(n.id, cId));
  });

  const clusters: ArchitectureCluster[] = [];

  clusterMap.forEach((cNodes, cId) => {
    const nodeIds = new Set(cNodes.map((n) => n.id));
    let internalEdges = 0;
    let externalEdges = 0;

    edges.forEach((e) => {
      const srcIn = nodeIds.has(e.source);
      const tgtIn = nodeIds.has(e.target);
      if (srcIn && tgtIn) {
        internalEdges++;
      } else if (srcIn || tgtIn) {
        externalEdges++;
      }
    });

    // Find most central module in this cluster
    let topModule: GraphNode | null = null;
    let maxMetric = -1;
    for (const n of cNodes) {
      const m = n.centrality > 0 ? n.centrality : n.degree;
      if (m > maxMetric) {
        maxMetric = m;
        topModule = n;
      }
    }

    // Assign cluster category
    let clusterCategory = 'regular';
    if (cNodes.some((n) => n.category === 'entry_point')) clusterCategory = 'entry_point';
    else if (cNodes.some((n) => n.category === 'core_module')) clusterCategory = 'core_module';
    else if (cNodes.some((n) => n.category === 'domain')) clusterCategory = 'domain';
    else if (cNodes.some((n) => n.category === 'service')) clusterCategory = 'service';
    else if (cNodes.some((n) => n.category === 'high_coupling')) clusterCategory = 'high_coupling';

    const central = topModule as GraphNode | null;

    clusters.push({
      id: cId,
      name: cId,
      category: clusterCategory,
      fileCount: cNodes.length,
      nodeIds: cNodes.map((n) => n.id),
      internalEdgeCount: internalEdges,
      externalEdgeCount: externalEdges,
      primaryRole: deriveClusterRole(cId, cNodes),
      mostCentralModule: central
        ? { id: central.id, label: central.label || central.id.split('/').pop() || '', centrality: central.centrality || 0 }
        : null,
      isExpanded: expandedClusterIds.has(cId),
    });
  });

  return clusters.sort((a, b) => b.fileCount - a.fileCount);
}

/**
 * Transforms nodes and edges based on the active abstraction level.
 */
export function buildAbstractedGraph(
  nodes: GraphNode[],
  edges: GraphEdge[],
  level: AbstractionLevel,
  expandedClusterIds: Set<string>,
  activeNodeId: string | null = null,
): { nodes: GraphNode[]; edges: GraphEdge[]; clusters: ArchitectureCluster[] } {
  const clusters = buildArchitectureClusters(nodes, edges, expandedClusterIds);

  if (level === 'files') {
    return { nodes, edges, clusters };
  }

  // System Level: Aggregated Cluster Nodes + Cross-cluster edges
  if (level === 'system') {
    const clusterNodes: GraphNode[] = clusters.map((c) => ({
      id: `cluster:${c.id}`,
      label: `${c.name.toUpperCase()} (${c.fileCount} files)`,
      category: c.category,
      degree: c.externalEdgeCount,
      centrality: c.mostCentralModule?.centrality ?? 0.1,
      language: 'cluster',
      highlighted: c.fileCount > 5,
      is_focus: false,
    }));

    // Aggregate inter-cluster edges
    const nodeToCluster = new Map<string, string>();
    clusters.forEach((c) => {
      c.nodeIds.forEach((id) => nodeToCluster.set(id, `cluster:${c.id}`));
    });

    const interClusterEdges = new Map<string, { source: string; target: string; count: number }>();
    edges.forEach((e) => {
      const srcC = nodeToCluster.get(e.source);
      const tgtC = nodeToCluster.get(e.target);
      if (srcC && tgtC && srcC !== tgtC) {
        const key = `${srcC}→${tgtC}`;
        if (!interClusterEdges.has(key)) {
          interClusterEdges.set(key, { source: srcC, target: tgtC, count: 0 });
        }
        interClusterEdges.get(key)!.count++;
      }
    });

    const aggregatedEdges: GraphEdge[] = Array.from(interClusterEdges.values()).map((ie) => ({
      source: ie.source,
      target: ie.target,
      relationship: `${ie.count} deps`,
    }));

    return { nodes: clusterNodes, edges: aggregatedEdges, clusters };
  }

  // Components Level: Clusters + Core nodes from expanded/active clusters
  const displayedNodes: GraphNode[] = [];
  const nodeToCluster = new Map<string, string>();
  clusters.forEach((c) => {
    c.nodeIds.forEach((id) => nodeToCluster.set(id, `cluster:${c.id}`));
  });

  clusters.forEach((c) => {
    const isExpanded = expandedClusterIds.has(c.id) || (activeNodeId && c.nodeIds.includes(activeNodeId));

    if (isExpanded) {
      // Include top important files from this cluster
      const contained = nodes.filter((n) => c.nodeIds.includes(n.id));
      displayedNodes.push(...contained);
    } else {
      // Represent as compact cluster node
      displayedNodes.push({
        id: `cluster:${c.id}`,
        label: `${c.name} (${c.fileCount})`,
        category: c.category,
        degree: c.externalEdgeCount,
        centrality: c.mostCentralModule?.centrality ?? 0.1,
        language: 'cluster',
        highlighted: false,
        is_focus: false,
      });
    }
  });

  const displayedIds = new Set(displayedNodes.map((n) => n.id));
  const validEdges = edges.filter((e) => {
    // Check direct edge
    if (displayedIds.has(e.source) && displayedIds.has(e.target)) return true;
    return false;
  });

  return { nodes: displayedNodes, edges: validEdges, clusters };
}

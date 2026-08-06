/**
 * Shared TypeScript types for Interactive Dependency Graph & Architecture Intelligence v2.
 * All components in the graph/ folder import from here.
 */

export interface GraphNode {
  id: string;
  label: string;
  category: string;
  degree: number;
  centrality: number;
  language: string;
  highlighted: boolean;
  is_focus: boolean;
}

export interface GraphEdge {
  source: string;
  target: string;
  relationship: string;
}

export interface GraphResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
  node_count: number;
  edge_count: number;
  error?: string;
  matched_count?: number;
  query?: string;
}

export type GraphMode =
  | 'full'
  | 'neighbors'
  | 'trace_fwd'
  | 'trace_bwd'
  | 'search';

export type HeatmapMode =
  | 'none'
  | 'coupling'
  | 'complexity'
  | 'churn'
  | 'fan_out'
  | 'file_size'
  | 'violations';

export type ArchitectureLayer =
  | 'Presentation'
  | 'Application'
  | 'Domain'
  | 'Infrastructure'
  | 'Data'
  | 'Integration'
  | 'Shared'
  | 'Test'
  | 'Configuration';

export type DetectedPattern =
  | 'MVC'
  | 'Clean Architecture'
  | 'Hexagonal'
  | 'Repository Pattern'
  | 'Factory'
  | 'Adapter'
  | 'Strategy'
  | 'Facade'
  | 'Decorator'
  | 'Observer'
  | 'CQRS'
  | 'Dependency Injection'
  | 'Singleton'
  | 'Builder'
  | 'Command'
  | 'Pipeline'
  | 'Middleware'
  | 'Event Driven';

export interface SystemPosition {
  distance_from_entry_point: number;
  distance_from_infrastructure: number;
  layer_number: number;
  dependency_depth: number;
  max_dependency_chain: number;
}

export interface AdvancedMetrics {
  fan_in: number;
  fan_out: number;
  afferent_coupling: number;
  efferent_coupling: number;
  instability: number;
  abstractness: number;
  distance_main_sequence: number;
  cyclomatic_complexity: number;
  maintainability_index: number;
  dependency_depth: number;
  import_count: number;
  export_count: number;
  public_symbols_count: number;
  classes_count: number;
  functions_count: number;
  avg_function_length: number;
  lines_of_code: number;
  comment_density: number;
}

export interface RiskIndicator {
  type: string;
  label: string;
  severity: 'info' | 'warn' | 'danger';
  description: string;
}

export interface GitMetrics {
  created: string | null;
  last_modified: string | null;
  commit_count: number | null;
  contributors_count: number | null;
  latest_author: string | null;
  latest_commit_message: string | null;
}

export interface DeveloperGuidance {
  common_modification_reasons: string[] | null;
  changed_together_files: string[] | null;
  related_tests: string[] | null;
  potential_side_effects: string[] | null;
}

export interface ImpactDetails {
  node_id: string;
  direct_consumers: string[];
  indirect_consumers: string[];
  total_affected_files: number;
  affected_entry_points: string[];
  affected_apis: string[];
  affected_services: string[];
  affected_tests: string[];
  risk_level: 'Low' | 'Medium' | 'High' | 'Critical';
  estimated_blast_radius_pct: number;
}

export interface Recommendation {
  title: string;
  reason: string;
  impact: string;
  priority: 'P0' | 'P1' | 'P2';
  estimated_improvement: string;
  suggestion: string;
}

export interface ArchitectureNodeDetails {
  node_id: string;
  label: string;
  business_responsibility: string;
  layer: ArchitectureLayer;
  patterns: DetectedPattern[];
  system_position: SystemPosition;
  metrics: AdvancedMetrics;
  impact?: ImpactDetails;
  recommendations?: Recommendation[];
  risk_indicators: RiskIndicator[];
  git_metrics: GitMetrics;
  developer_guidance: DeveloperGuidance;
  suggested_reading_order: string[] | null;
}

export interface ArchitectureQuality {
  overall_score: number;
  badge: 'EXCELLENT' | 'GOOD' | 'NEEDS_ATTENTION' | 'CRITICAL';
  subscores: {
    layering: number;
    coupling: number;
    cohesion: number;
    complexity: number;
    maintainability: number;
    dependency_health: number;
    testability: number;
  };
}

export interface DependencyPath {
  source: string;
  target: string;
  distance: number;
  path_nodes: string[];
  cross_layer_transitions: number;
  has_cycle: boolean;
}

export const CATEGORY_COLORS: Record<string, string> = {
  entry_point:   '#10b981', // emerald-500
  core_module:   '#3b82f6', // blue-500
  high_coupling: '#f97316', // orange-500
  directory:     '#a855f7', // purple-500
  focus:         '#ffffff', // white
  regular:       '#71717a', // zinc-500
  service:       '#6366f1', // indigo-500
  controller:    '#ec4899', // pink-500
  utility:       '#64748b', // slate-500
  test:          '#06b6d4', // cyan-500
};

export const CATEGORY_LABELS: Record<string, string> = {
  entry_point:   'Entry Point',
  core_module:   'Core Module',
  high_coupling: 'High Coupling',
  directory:     'Directory',
  focus:         'Focus',
  regular:       'Regular',
  service:       'Service',
  controller:    'Controller',
  utility:       'Utility',
  test:          'Test Suite',
};

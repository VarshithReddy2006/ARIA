/**
 * Canonical TypeScript mirror of the backend impact-analysis contract.
 *
 * SOURCE OF TRUTH: `models/phase2.py` (Pydantic models serialised by
 * `POST /api/v1/impact-analysis`). Field optionality here intentionally matches
 * the Python models field-for-field:
 *
 *   - Python `Optional[X] = None`        -> `x?: X`
 *   - Python `X = Field(default_factory)`-> `x: X` (always present in JSON)
 *
 * These types previously existed as two drifting copies inside
 * `ImpactAnalysisGraph.tsx` and `ImpactAnalysisWorkspace.tsx`. The copies
 * disagreed on `CallerInfo.line_number` (required vs optional), which broke
 * `tsc --noEmit` and misrepresented a genuinely nullable backend field as
 * always present. Keep this file as the only declaration site.
 */

/** `models.phase2.EvidenceKind` */
export type EvidenceKind =
  | 'FACT'
  | 'INFERENCE'
  | 'PREDICTION'
  | 'RECOMMENDATION';

/** `models.phase2.ConfidenceTier` */
export type ConfidenceTier = 'HIGH' | 'MEDIUM' | 'LOW';

/** `models.phase2.ImpactAnalysis.operating_mode` */
export type OperatingMode = 'SAFE' | 'BALANCED' | 'EXPLORATORY';

/** `models.phase2.TestImpactItem.impact_type` */
export type TestImpactType =
  | 'DIRECT TEST IMPACT'
  | 'LIKELY TEST IMPACT'
  | 'HEURISTIC TEST CANDIDATE';

/** `models.phase2.DependencyPath` */
export interface DependencyPath {
  path: string[];
}

/** `models.phase2.EvidenceItem` */
export interface EvidenceItem {
  // Widened with `string` because the backend serialises the enum by value and
  // may add kinds before the frontend is redeployed.
  kind: EvidenceKind | string;
  statement: string;
  source_reference?: string;
  /** 0-100 (not 0.0-1.0). */
  confidence: number;
}

/** `models.phase2.CallerInfo` */
export interface CallerInfo {
  caller_id: string;
  caller_name: string;
  file_path: string;
  /** Optional: `Optional[int] = None` upstream. Absent means UNKNOWN, not 0. */
  line_number?: number;
  is_direct: boolean;
  depth: number;
  propagation_path?: string[];
  /** `models.call_graph.CallRelationshipType` value, e.g. `DIRECT_CALL`. */
  relationship?: string;
  receiver_expr?: string;
  receiver_type?: string;
  confidence_tier?: ConfidenceTier | string;
}

/** `models.phase2.ApiExposureInfo` */
export interface ApiExposureInfo {
  public_routes: string[];
  internal_routes: string[];
  exported_symbols: string[];
  deprecated_interfaces: string[];
}

/** `models.phase2.TestImpactItem` */
export interface TestImpactItem {
  test_file: string;
  impact_type: TestImpactType | string;
  reason: string;
  confidence_tier?: ConfidenceTier;
  evidence_strength?: string;
  propagation_path?: string[];
  source_reference?: string;
  evidence_paths?: Array<Record<string, unknown>>;
}

/** `models.phase2.ImpactedFileDetail` */
export interface ImpactedFileDetail {
  file_path: string;
  confidence_tier: ConfidenceTier;
  /** 0.0-1.0 (not 0-100). */
  confidence_score: number;
  evidence_strength: string;
  reason: string;
  propagation_path: string[];
  target_symbols: string[];
  verifications?: Record<string, unknown>;
}

/** `models.phase2.ImpactAnalysis` — the `POST /api/v1/impact-analysis` body. */
export interface ImpactAnalysisData {
  repo: string;
  issue_text: string;
  directly_affected_files: string[];
  indirectly_affected_files: string[];
  affected_components: string[];
  /** 'low' | 'medium' | 'high' | 'extreme' */
  risk_level: string;
  estimated_file_count: number;
  dependency_paths: DependencyPath[];
  /** 0-100. */
  confidence: number;
  /** 'XS' | 'S' | 'M' | 'L' | 'XL' */
  blast_radius_category?: string;
  affected_symbols?: string[];
  direct_callers?: CallerInfo[];
  transitive_callers?: CallerInfo[];
  api_exposure?: ApiExposureInfo;
  affected_tests?: TestImpactItem[];
  architecture_boundaries?: string[];
  evidence_items?: EvidenceItem[];
  implementation_order?: string[];
  high_confidence_files?: string[];
  medium_confidence_files?: string[];
  low_confidence_files?: string[];
  tiered_files?: {
    high: string[];
    medium: string[];
    low: string[];
  };
  impacted_file_details?: ImpactedFileDetail[];
  verified_impact_count?: number;
  likely_impact_count?: number;
  candidate_count?: number;
  operating_mode?: OperatingMode | string;
}

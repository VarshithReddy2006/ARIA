/* eslint-disable @typescript-eslint/ban-types */
/**
 * API client for the Repo Intelligence Agent backend.
 *
 * All backend communication goes through this module. It reads the base URL
 * and optional token from VS Code settings so there is one place to change
 * the target. No analysis logic lives here — this is a pure HTTP client.
 */

import * as vscode from 'vscode';
import * as https from 'https';
import * as http from 'http';

// ---------------------------------------------------------------------------
// Types that mirror backend Pydantic models
// ---------------------------------------------------------------------------

export interface HealthResponse {
  backend: string;
  llm_provider: string;
  llm_model: string;
  embedding_provider: string;
  vector_db: string;
  status: string;
}

export interface RecentRepo {
  name: string;
  url: string;
  tech_stack: string[];
  analyzed_at: string;
}

export interface RepositoryAnalysis {
  structure: Record<string, string[]>;
  dependencies: string[];
  tech_stack: string[];
  metadata: Record<string, string>;
}

export interface ArchitectureSummary {
  summary: string;
  reading_order: string[];
  relationships: ComponentRelationship[];
}

export interface ComponentRelationship {
  source: string;
  target: string;
  relationship_type: string;
  description: string;
}

export interface AnalysisDetails {
  analysis: RepositoryAnalysis;
  architecture: ArchitectureSummary;
}

export interface Symbol {
  name: string;
  qualified: string;
  symbol_type: string;
  file_path: string;
  line_number: number;
  language: string;
  parent_class: string | null;
  fan_in?: number;
  fan_out?: number;
}

export interface FileSymbolsResponse {
  file: string;
  repo: string;
  symbol_count: number;
  symbols: Symbol[];
}

export interface SymbolDefinitionResponse {
  symbol: string;
  repo: string;
  definition: Symbol;
}

export interface SymbolReferencesResponse {
  symbol: string;
  repo: string;
  references: Symbol[];
  reference_count: number;
}

export interface GraphNode {
  id: string;
  data: {
    label: string;
    [key: string]: unknown;
  };
  position: { x: number; y: number };
  type?: string;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  /** Alias of `source`, retained for edge consumers that traverse from/to. */
  from?: string;
  /** Alias of `target`, retained for edge consumers that traverse from/to. */
  to?: string;
  type?: string;
  [key: string]: unknown;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface CallGraphStats {
  node_count: number;
  edge_count: number;
  /** Mapped from the backend `entry_functions` field. */
  entry_count: number;
  [key: string]: unknown;
}

export interface CallNode {
  node_id: string;
  name: string;
  qualified: string;
  file_path: string;
  line_number: number;
  language: string;
  symbol_type: string;
  parent_class: string | null;
  is_entry: boolean;
  is_recursive: boolean;
  fan_in: number;
  fan_out: number;
}

export interface CallersResponse {
  function_id: string;
  callers: CallNode[];
}

export interface CalleesResponse {
  function_id: string;
  callees: CallNode[];
}

export interface BlastRadiusResult {
  function_id: string;
  affected_functions: string[];
  affected_files: string[];
  depth: number;
  risk_level: string;
  recursive_cycles: string[][];
}

export interface ClassifiedSymbol {
  name: string;
  qualified: string;
  symbol_type: string;
  file_path: string;
  line_number: number;
  language: string;
  visibility: string;
  api_kind: string;
  status: string;
  confidence: number;
  classification_reason: string;
  fan_in: number;
  is_orphan: boolean;
}

export interface APISurfaceStats {
  total_symbols: number;
  public_count: number;
  internal_count: number;
  private_count: number;
  deprecated_count: number;
  experimental_count: number;
  route_count: number;
  orphan_public_count: number;
  by_language: Record<string, number>;
}

export interface APISurface {
  repo: string;
  generated_at: string;
  symbols: ClassifiedSymbol[];
  stats: APISurfaceStats;
  warning?: string;
}

export interface ChurnHotspot {
  file_path: string;
  commit_count: number;
  churn_score: number;
  [key: string]: unknown;
}

export interface HotspotsResponse {
  hotspots: ChurnHotspot[];
}

export interface ReadingOrderEntry {
  file: string;
  score: number;
  reason: string;
  [key: string]: unknown;
}

export interface ReadingOrder {
  repo: string;
  entries: ReadingOrderEntry[];
  [key: string]: unknown;
}

export interface ImpactAnalysis {
  repo: string;
  issue: string;
  affected_files: string[];
  risk_level: string;
  risk_score: number;
  [key: string]: unknown;
}

export interface IssueMapResponse {
  issue_summary: string;
  issue_type: string;
  relevant_files: string[];
  affected_components: string[];
  implementation_plan: Array<Record<string, unknown>>;
  complexity: string;
  confidence: number;
  verified: boolean;
  sources: string[];
}

export interface ArchitectureBuildResponse {
  status: string;
  repo: string;
  files_parsed: number;
  dependencies_found: number;
  entry_points: string[];
}

// ── Workspace Panel Types ──────────────────────────────────────────────────

export interface WorkspaceState {
  repository: string;
  selected_file: string | null;
  selected_symbol: string | null;
  active_panel: string;
  filters: Record<string, any>;
  ui_preferences: Record<string, any>;
}

export interface HealthSummary {
  overall_score: number | null;
  overall_priority: string | null;
  critical_count: number;
  high_count: number;
  medium_count: number;
  low_count: number;
  trend_direction: string | null;
}

export interface OverviewPanel {
  repository: string;
  description: string | null;
  primary_language: string | null;
  languages: string[];
  total_files: number;
  total_symbols: number;
  architecture_style: string | null;
  dependency_count: number;
  health: HealthSummary;
  last_indexed_at: number | null;
  metadata: Record<string, any>;
}

export interface ExplorerNode {
  id: string;
  label: string;
  kind: string;
  children: ExplorerNode[];
  metadata: Record<string, any>;
}

export interface ExplorerPanel {
  repository: string;
  total_nodes: number;
  total_edges: number;
  root_nodes: ExplorerNode[];
  entry_points: string[];
  dependency_summary: Record<string, number>;
  metadata: Record<string, any>;
}

export interface ChatSessionMeta {
  repository: string;
  grounding_available: boolean;
  context_nodes: number;
  suggested_questions: string[];
  metadata: Record<string, any>;
}

export interface FindingsSummary {
  id: string;
  title: string;
  category: string;
  severity: string;
  confidence: number;
  affected_entities: string[];
  recommendation_count: number;
}

export interface FindingsPanel {
  repository: string;
  total_findings: number;
  findings: FindingsSummary[];
  by_severity: Record<string, number>;
  by_category: Record<string, number>;
  last_inspected_at: number | null;
  metadata: Record<string, any>;
}

export interface TimelineEntry {
  snapshot_id: string;
  timestamp: number;
  commit_hash: string | null;
  summary: string;
  metrics: Record<string, any>;
}

export interface TimelinePanel {
  repository: string;
  snapshot_count: number;
  timeline: TimelineEntry[];
  trends: Record<string, any>;
  metadata: Record<string, any>;
}

export interface MonitorPanel {
  repository: string;
  status: string;
  last_run_at: number | null;
  last_trigger: string | null;
  run_count: number;
  health_trend: string | null;
  overall_health_score: number | null;
  recent_runs: Array<Record<string, any>>;
  alerts: Array<Record<string, any>>;
  metadata: Record<string, any>;
}

export interface AdvisorPanel {
  repository: string;
  overall_priority: string;
  total_recommendations: number;
  top_recommendations: Array<Record<string, any>>;
  roadmap_phases: number;
  roadmap_summary: Array<Record<string, any>>;
  metadata: Record<string, any>;
}

export interface BatchSummary {
  batch_id: string;
  order: number;
  title: string;
  task_count: number;
  parallel: boolean;
  estimated_effort: string;
}

export interface ExecutionPanel {
  repository: string;
  total_tasks: number;
  total_batches: number;
  critical_path_length: number;
  rollback_checkpoints: number;
  conflict_count: number;
  overall_risk: string;
  batches: BatchSummary[];
  critical_path: string[];
  metadata: Record<string, any>;
}

export interface WorkspaceSnapshot {
  state: WorkspaceState;
  overview: OverviewPanel | null;
  explorer: ExplorerPanel | null;
  chat: ChatSessionMeta | null;
  findings: FindingsPanel | null;
  timeline: TimelinePanel | null;
  monitor: MonitorPanel | null;
  advisor: AdvisorPanel | null;
  execution: ExecutionPanel | null;
  available_panels: string[];
  metadata: Record<string, any>;
}


// ---------------------------------------------------------------------------
// SSE helpers
// ---------------------------------------------------------------------------

export type SseEventHandler = (event: Record<string, unknown>) => void;

// ---------------------------------------------------------------------------
// Client class
// ---------------------------------------------------------------------------

export class RepoIntelligenceClient {
  private _token = '';
  public onUnauthorized?: () => Promise<string | undefined>;

  public setToken(token: string): void {
    this._token = token;
  }

  private get baseUrl(): string {
    const cfg = vscode.workspace.getConfiguration('repoIntelligence');
    return (cfg.get<string>('backendUrl') ?? 'http://127.0.0.1:8001').replace(/\/$/, '');
  }

  private get timeoutMs(): number {
    const cfg = vscode.workspace.getConfiguration('repoIntelligence');
    return cfg.get<number>('requestTimeoutMs') ?? 15000;
  }

  private get authHeaders(): Record<string, string> {
    return this._token ? { Authorization: `Bearer ${this._token}` } : {};
  }

  // ── Core fetch ──────────────────────────────────────────────────────────

  async fetchJson<T>(
    path: string,
    options: { method?: string; body?: unknown } = {}
  ): Promise<T> {
    if (path.startsWith('/api/') && !path.startsWith('/api/v1/')) {
      path = '/api/v1' + path.substring(4);
    }
    const url = `${this.baseUrl}${path}`;
    const method = options.method ?? 'GET';
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      ...this.authHeaders,
    };

    return new Promise<T>((resolve, reject) => {
      const parsedUrl = new URL(url);
      const isHttps = parsedUrl.protocol === 'https:';
      const transport = isHttps ? https : http;

      const reqOptions: http.RequestOptions = {
        hostname: parsedUrl.hostname,
        port: parsedUrl.port || (isHttps ? 443 : 80),
        path: parsedUrl.pathname + parsedUrl.search,
        method,
        headers,
        timeout: this.timeoutMs,
      };

      const req = transport.request(reqOptions, (res) => {
        let data = '';
        res.on('data', (chunk) => (data += chunk));
        res.on('end', () => {
          try {
            if (res.statusCode === 401 && this.onUnauthorized) {
              this.onUnauthorized().then((newToken) => {
                if (newToken !== undefined) {
                  this.setToken(newToken);
                  this.fetchJson<T>(path, options).then(resolve, reject);
                } else {
                  reject(new Error('HTTP 401 Unauthorized'));
                }
              }).catch(reject);
              return;
            }

            if (res.statusCode && res.statusCode >= 400) {
              let detail = `HTTP ${res.statusCode}`;
              try {
                const parsed = JSON.parse(data);
                detail = parsed.detail ?? detail;
              } catch {
                // use status text
              }
              reject(new Error(detail));
              return;
            }
            resolve(JSON.parse(data) as T);
          } catch (e) {
            reject(new Error(`Failed to parse response: ${String(e)}`));
          }
        });
      });

      req.on('timeout', () => {
        req.destroy();
        reject(new Error(`Request to ${url} timed out after ${this.timeoutMs}ms`));
      });

      req.on('error', (e) => reject(new Error(`Request failed: ${e.message}`)));

      if (options.body !== undefined) {
        req.write(JSON.stringify(options.body));
      }
      req.end();
    });
  }

  // ── SSE streaming (uses Node http/https directly) ───────────────────────

  streamSse(
    path: string,
    body: Record<string, unknown>,
    onEvent: SseEventHandler,
    onDone: () => void,
    onError: (err: Error) => void
  ): () => void {
    if (path.startsWith('/api/') && !path.startsWith('/api/v1/')) {
      path = '/api/v1' + path.substring(4);
    }
    const url = `${this.baseUrl}${path}`;
    const parsedUrl = new URL(url);
    const isHttps = parsedUrl.protocol === 'https:';
    const transport = isHttps ? https : http;

    const payload = JSON.stringify(body);
    const reqOptions: http.RequestOptions = {
      hostname: parsedUrl.hostname,
      port: parsedUrl.port || (isHttps ? 443 : 80),
      path: parsedUrl.pathname + parsedUrl.search,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
        'Cache-Control': 'no-cache',
        ...this.authHeaders,
      },
    };

    const req = transport.request(reqOptions, (res) => {
      if (res.statusCode === 401 && this.onUnauthorized) {
        this.onUnauthorized().then((newToken) => {
          if (newToken !== undefined) {
            this.setToken(newToken);
          }
        }).catch(() => {});
        onError(new Error('HTTP 401 Unauthorized'));
        return;
      }

      let buffer = '';
      res.on('data', (chunk: Buffer) => {
        buffer += chunk.toString();
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const jsonStr = line.slice(6).trim();
            if (!jsonStr) {
              continue;
            }
            try {
              const event = JSON.parse(jsonStr) as Record<string, unknown>;
              onEvent(event);
              if (event.status === 'done') {
                onDone();
              }
            } catch {
              // skip malformed SSE lines
            }
          }
        }
      });
      res.on('end', () => onDone());
      res.on('error', onError);
    });

    req.on('error', onError);
    req.write(payload);
    req.end();

    return () => req.destroy();
  }

  // ── Health ──────────────────────────────────────────────────────────────

  async health(): Promise<HealthResponse> {
    return this.fetchJson<HealthResponse>('/health');
  }

  // ── Repositories ────────────────────────────────────────────────────────

  async getRecentRepos(): Promise<RecentRepo[]> {
    return this.fetchJson<RecentRepo[]>('/api/repos/recent');
  }

  async getAnalysis(owner: string, repo: string): Promise<AnalysisDetails> {
    return this.fetchJson<AnalysisDetails>(`/api/analysis/${owner}/${repo}`);
  }

  async runInspection(owner: string, repo: string, policy = 'default'): Promise<any> {
    return this.fetchJson(`/api/repositories/${owner}/${repo}/inspect?policy=${policy}`, {
      method: 'POST',
    });
  }

  async runMonitoring(owner: string, repo: string, policy = 'immediate'): Promise<any> {
    return this.fetchJson(`/api/repositories/${owner}/${repo}/monitor?policy=${policy}`, {
      method: 'POST',
    });
  }

  async generateRoadmap(owner: string, repo: string): Promise<any> {
    return this.fetchJson(`/api/repositories/${owner}/${repo}/advisor`, {
      method: 'POST',
    });
  }

  async generateExecutionPlan(owner: string, repo: string): Promise<any> {
    return this.fetchJson(`/api/repositories/${owner}/${repo}/execution-plan`, {
      method: 'POST',
    });
  }

  // ── Symbols ─────────────────────────────────────────────────────────────

  async getFileSymbols(owner: string, repo: string, filePath: string): Promise<FileSymbolsResponse> {
    return this.fetchJson<FileSymbolsResponse>(
      `/api/symbols/${owner}/${repo}/file/${filePath}`
    );
  }

  async getSymbolDefinition(owner: string, repo: string, symbolName: string): Promise<SymbolDefinitionResponse> {
    return this.fetchJson<SymbolDefinitionResponse>(
      `/api/symbols/${owner}/${repo}/definition/${encodeURIComponent(symbolName)}`
    );
  }

  async getSymbolReferences(owner: string, repo: string, symbolName: string): Promise<SymbolReferencesResponse> {
    return this.fetchJson<SymbolReferencesResponse>(
      `/api/symbols/${owner}/${repo}/references/${encodeURIComponent(symbolName)}`
    );
  }

  // ── Architecture ────────────────────────────────────────────────────────

  async buildArchitecture(repo: string): Promise<ArchitectureBuildResponse> {
    return this.fetchJson<ArchitectureBuildResponse>('/api/architecture/build', {
      method: 'POST',
      body: { repo },
    });
  }

  async getArchitectureSummary(owner: string, repo: string): Promise<ArchitectureSummary> {
    return this.fetchJson<ArchitectureSummary>(`/api/architecture/${owner}/${repo}`);
  }

  async getReadingOrder(repo: string): Promise<ReadingOrder> {
    return mapReadingOrder(
      await this.fetchJson<unknown>('/api/reading-order', {
        method: 'POST',
        body: { repo },
      })
    );
  }

  async getImpactAnalysis(repo: string, issue: string): Promise<ImpactAnalysis> {
    return mapImpactAnalysis(
      await this.fetchJson<unknown>('/api/impact-analysis', {
        method: 'POST',
        body: { repo, issue },
      })
    );
  }

  // ── Graph ────────────────────────────────────────────────────────────────

  async getDependencyGraph(owner: string, repo: string, query?: string): Promise<GraphData> {
    const q = query ? `?q=${encodeURIComponent(query)}` : '';
    return mapGraphData(await this.fetchJson<unknown>(`/api/graph/${owner}/${repo}/full${q}`));
  }

  async getGraphNeighbors(owner: string, repo: string, nodePath: string): Promise<GraphData> {
    return mapGraphData(
      await this.fetchJson<unknown>(`/api/graph/${owner}/${repo}/neighbors/${nodePath}`)
    );
  }

  async getGraphTrace(
    owner: string,
    repo: string,
    nodePath: string,
    direction = 'both',
    depth = 6
  ): Promise<GraphData> {
    return mapGraphData(
      await this.fetchJson<unknown>(
        `/api/graph/${owner}/${repo}/trace/${nodePath}?direction=${direction}&depth=${depth}`
      )
    );
  }

  // ── Call Graph ──────────────────────────────────────────────────────────

  async getCallGraph(owner: string, repo: string, query?: string): Promise<GraphData> {
    const q = query ? `?q=${encodeURIComponent(query)}` : '';
    return mapGraphData(await this.fetchJson<unknown>(`/api/call-graph/${owner}/${repo}${q}`));
  }

  async getCallGraphStats(owner: string, repo: string): Promise<CallGraphStats> {
    return mapCallGraphStats(
      await this.fetchJson<unknown>(`/api/call-graph/${owner}/${repo}/stats`)
    );
  }

  async getCallers(owner: string, repo: string, functionId: string): Promise<CallersResponse> {
    return this.fetchJson<CallersResponse>(
      `/api/call-graph/${owner}/${repo}/callers/${functionId}`
    );
  }

  async getCallees(owner: string, repo: string, functionId: string): Promise<CalleesResponse> {
    return this.fetchJson<CalleesResponse>(
      `/api/call-graph/${owner}/${repo}/callees/${functionId}`
    );
  }

  async getBlastRadius(owner: string, repo: string, functionId: string): Promise<BlastRadiusResult> {
    return this.fetchJson<BlastRadiusResult>(
      `/api/call-graph/${owner}/${repo}/blast-radius/${functionId}`
    );
  }

  // ── API Surface ──────────────────────────────────────────────────────────

  async getAPISurface(owner: string, repo: string): Promise<APISurface> {
    return this.fetchJson<APISurface>(`/api/api-surface/${owner}/${repo}`);
  }

  async getAPISurfaceStats(owner: string, repo: string): Promise<APISurfaceStats> {
    return this.fetchJson<APISurfaceStats>(`/api/api-surface/${owner}/${repo}/stats`);
  }

  async getPublicAPI(owner: string, repo: string, query?: string): Promise<{ symbols: ClassifiedSymbol[]; count: number }> {
    const q = query ? `?q=${encodeURIComponent(query)}` : '';
    return this.fetchJson(`/api/api-surface/${owner}/${repo}/public${q}`);
  }

  // ── Git Churn ───────────────────────────────────────────────────────────

  async getChurnHotspots(
    owner: string,
    repo: string,
    topN = 25,
    sinceDays = 365
  ): Promise<HotspotsResponse> {
    return this.fetchJson<HotspotsResponse>(
      `/api/churn/${owner}/${repo}/hotspots?top_n=${topN}&since_days=${sinceDays}`
    );
  }

  // ── Chat ────────────────────────────────────────────────────────────────

  // ── Workspace ────────────────────────────────────────────────────────────

  async getWorkspace(
    owner: string,
    repo: string,
    file?: string,
    symbol?: string,
    panel?: string
  ): Promise<WorkspaceSnapshot> {
    const params: string[] = [];
    if (file) { params.push(`file=${encodeURIComponent(file)}`); }
    if (symbol) { params.push(`symbol=${encodeURIComponent(symbol)}`); }
    if (panel) { params.push(`panel=${encodeURIComponent(panel)}`); }
    const query = params.length > 0 ? `?${params.join('&')}` : '';
    return this.fetchJson<WorkspaceSnapshot>(`/api/repositories/${owner}/${repo}/workspace${query}`);
  }

  async getOverview(owner: string, repo: string): Promise<OverviewPanel> {
    return this.fetchJson<OverviewPanel>(`/api/repositories/${owner}/${repo}/workspace/overview`);
  }

  async getExplorer(owner: string, repo: string): Promise<ExplorerPanel> {
    return this.fetchJson<ExplorerPanel>(`/api/repositories/${owner}/${repo}/workspace/explorer`);
  }

  async getChatMeta(owner: string, repo: string): Promise<ChatSessionMeta> {
    return this.fetchJson<ChatSessionMeta>(`/api/repositories/${owner}/${repo}/workspace/chat`);
  }

  async getFindings(owner: string, repo: string): Promise<FindingsPanel> {
    return this.fetchJson<FindingsPanel>(`/api/repositories/${owner}/${repo}/workspace/findings`);
  }

  async getTimeline(owner: string, repo: string): Promise<TimelinePanel> {
    return this.fetchJson<TimelinePanel>(`/api/repositories/${owner}/${repo}/workspace/timeline`);
  }

  async getMonitoring(owner: string, repo: string): Promise<MonitorPanel> {
    return this.fetchJson<MonitorPanel>(`/api/repositories/${owner}/${repo}/workspace/monitor`);
  }

  async getAdvisor(owner: string, repo: string): Promise<AdvisorPanel> {
    return this.fetchJson<AdvisorPanel>(`/api/repositories/${owner}/${repo}/workspace/advisor`);
  }

  async getExecutionPlan(owner: string, repo: string): Promise<ExecutionPanel> {
    return this.fetchJson<ExecutionPanel>(`/api/repositories/${owner}/${repo}/workspace/execution`);
  }

  streamChat(
    repo: string,
    message: string,
    history: Array<{ role: string; content: string }>,
    onToken: (text: string) => void,
    onDone: (sources: string[], confidence: number) => void,
    onError: (err: Error) => void,
    sessionId?: string
  ): () => void {
    const body = sessionId ? { repo, message, history, session_id: sessionId } : { repo, message, history };
    return this.streamSse(
      '/api/chat',
      body,
      (event) => {
        if (typeof event.text === 'string') {
          onToken(event.text);
        }
        if (event.status === 'done') {
          onDone(
            (event.sources as string[]) ?? [],
            (event.confidence as number) ?? 0
          );
        }
      },
      () => { /* handled inside onEvent for status==done */ },
      onError
    );
  }
}

/**
 * Backend → extension response mappers.
 *
 * The backend emits flattened graph nodes, `ordered_files` reading orders,
 * split impact file lists, and `entry_functions` call-graph statistics.
 * These helpers adapt those payloads to the DTOs the extension consumes,
 * without altering any backend contract.
 */

function mapGraphData(raw: unknown): GraphData {
  const payload = (raw ?? {}) as { nodes?: unknown[]; edges?: unknown[] };

  const nodes: GraphNode[] = (payload.nodes ?? []).map((entry) => {
    const node = (entry ?? {}) as Record<string, unknown>;
    const id = String(node.id ?? '');

    if (node.data && typeof node.data === 'object') {
      return {
        ...node,
        id,
        data: node.data as GraphNode['data'],
        position: (node.position as GraphNode['position']) ?? { x: 0, y: 0 },
      } as GraphNode;
    }

    const { id: _id, position, ...rest } = node;
    return {
      id,
      data: {
        ...rest,
        label: String(node.label ?? id.split('/').pop() ?? id),
      },
      position: (position as GraphNode['position']) ?? { x: 0, y: 0 },
    } as GraphNode;
  });

  const edges: GraphEdge[] = (payload.edges ?? []).map((entry, index) => {
    const edge = (entry ?? {}) as Record<string, unknown>;
    const source = String(edge.source ?? edge.from ?? '');
    const target = String(edge.target ?? edge.to ?? '');
    return {
      ...edge,
      id: String(edge.id ?? `${source}->${target}#${index}`),
      source,
      target,
      from: source,
      to: target,
    } as GraphEdge;
  });

  return { nodes, edges };
}

function mapReadingOrder(raw: unknown): ReadingOrder {
  const payload = (raw ?? {}) as Record<string, unknown>;
  const source = (payload.ordered_files ?? payload.entries ?? []) as unknown[];

  const entries: ReadingOrderEntry[] = source.map((item, index) => {
    const entry = (item ?? {}) as Record<string, unknown>;
    return {
      ...entry,
      file: String(entry.file_path ?? entry.file ?? ''),
      score: Number(entry.score ?? entry.rank ?? index + 1),
      reason: String(entry.reason ?? ''),
    } as ReadingOrderEntry;
  });

  return { ...payload, repo: String(payload.repo ?? ''), entries } as ReadingOrder;
}

function mapImpactAnalysis(raw: unknown): ImpactAnalysis {
  const payload = (raw ?? {}) as Record<string, unknown>;
  const direct = (payload.directly_affected_files ?? []) as string[];
  const indirect = (payload.indirectly_affected_files ?? []) as string[];
  const existing = payload.affected_files as string[] | undefined;
  const affected = existing ?? [...direct, ...indirect];

  return {
    ...payload,
    repo: String(payload.repo ?? ''),
    issue: String(payload.issue ?? payload.issue_text ?? ''),
    affected_files: affected,
    risk_level: String(payload.risk_level ?? ''),
    risk_score: Number(payload.risk_score ?? payload.confidence ?? 0),
  } as ImpactAnalysis;
}

function mapCallGraphStats(raw: unknown): CallGraphStats {
  const payload = (raw ?? {}) as Record<string, unknown>;
  return {
    ...payload,
    node_count: Number(payload.node_count ?? 0),
    edge_count: Number(payload.edge_count ?? 0),
    entry_count: Number(payload.entry_count ?? payload.entry_functions ?? 0),
  } as CallGraphStats;
}

/**
 * Shared singleton client — imported by providers, commands, and panels.
 */
export const client = new RepoIntelligenceClient();

/**
 * Extract a user-friendly message from any error value.
 */
export function extractErrorMessage(err: unknown): string {
  if (err instanceof Error) {
    return err.message;
  }
  if (typeof err === 'string') {
    return err;
  }
  return 'An unknown error occurred.';
}

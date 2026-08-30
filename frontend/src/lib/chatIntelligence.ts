/**
 * ARIA Chat Intelligence & Engineering Companion Module
 * 
 * Provides:
 * - Query intent classification across 17 engineering categories
 * - Evidence confidence categorization (VERIFIED, INFERRED, PARTIAL, UNKNOWN)
 * - Secret and sensitive data redaction for repository safety
 * - Dynamic suggested prompts derived from repository architecture
 * - Contextual follow-up question synthesis
 * - Interactive file path and symbol extraction
 * - Pronoun and entity memory resolution
 * - Cross-surface navigation action routing
 */

export type ChatIntent =
  | 'OVERVIEW'
  | 'ARCHITECTURE'
  | 'FILE_EXPLANATION'
  | 'SYMBOL_EXPLANATION'
  | 'DEPENDENCY'
  | 'CIRCULAR_DEPENDENCY'
  | 'CALL_GRAPH'
  | 'IMPACT_ANALYSIS'
  | 'API'
  | 'API_FLOW'
  | 'DEBUGGING'
  | 'TESTING'
  | 'READING_PATH'
  | 'HEALTH'
  | 'SECURITY'
  | 'DEAD_CODE'
  | 'GIT_HISTORY'
  | 'PR_RISK'
  | 'CHANGE_PLANNING'
  | 'GENERAL_REPOSITORY';

export type ResponseIntent = ChatIntent;
export type EvidenceConfidence = 'VERIFIED' | 'STRONGLY INFERRED' | 'INFERRED' | 'UNKNOWN' | 'PARTIAL';

export interface ConversationEntity {
  name: string;
  type: 'file' | 'symbol' | 'endpoint' | 'artifact' | 'dependency';
  turn: number;
}

export interface EngineeringThread {
  threadId: string;
  title: string;
  entities: string[];
  resolvedAspects: string[];
  unresolvedAspects: string[];
  depthLevel: number;
}

export interface FollowUpCandidate {
  prompt: string;
  targetEntity?: string;
  noveltyScore: number;
  depthLevel: number;
}

export interface InvestigationContext {
  activeThreads: EngineeringThread[];
  exploredEntities: ConversationEntity[];
  currentFocus?: string;
  depthLevel: number;
}

export interface ExtractedEntity {
  type: 'file' | 'symbol' | 'api' | 'relationship';
  raw: string;
  normalized: string;
}

export interface IntentAnalysis {
  intent: ChatIntent;
  confidence: number;
  entities: ExtractedEntity[];
  actionTarget?: 'graph' | 'call_graph' | 'reading_path' | 'report' | 'api_surface' | 'dead_code' | 'git_history' | 'pr_intelligence';
  actionLabel?: string;
}

export interface DynamicPromptConfig {
  repoName: string;
  techStack?: string[];
  dependencies?: string[];
  entryPoints?: string[];
  cyclesCount?: number;
  componentCount?: number;
  readingSteps?: number;
  healthScore?: number;
}

// ---------------------------------------------------------------------------
// 1. Intent Detection
// ---------------------------------------------------------------------------

const INTENT_RULES: Array<{
  pattern: RegExp;
  intent: ChatIntent;
  confidence: number;
  actionTarget?: IntentAnalysis['actionTarget'];
  actionLabel?: string;
}> = [
  {
    pattern: /\b(how (?:would|can|to|do) (?:I|we) (?:add|implement|refactor|create|introduce|migrate|replace)|what files (?:would|to|should) (?:I|we) (?:need to |have to )?(?:modify|change|touch|update)|plan (?:for|to)|implementation (?:plan|order|steps)|refactor.*to)\b/i,
    intent: 'CHANGE_PLANNING',
    confidence: 0.95,
    actionTarget: 'graph',
    actionLabel: 'Inspect Impact in File Graph',
  },
  {
    pattern: /\b(what (happens|breaks|changes)|if (I|we) (change|delete|modify|remove)|blast radius|ripple effect|downstream impact|affect(ed)? files|what depends on)\b/i,
    intent: 'IMPACT_ANALYSIS',
    confidence: 0.95,
    actionTarget: 'graph',
    actionLabel: 'Analyze Impact Propagation',
  },
  {
    pattern: /\b(who calls|what calls|callers? of|callees? of|call (chain|graph|hierarchy)|invoked by|called by)\b/i,
    intent: 'CALL_GRAPH',
    confidence: 0.95,
    actionTarget: 'call_graph',
    actionLabel: 'Trace in Call Graph',
  },
  {
    pattern: /\b(dead code|unused (functions?|files?|symbols?|methods?)|unreferenced|uncalled)\b/i,
    intent: 'DEAD_CODE',
    confidence: 0.92,
    actionTarget: 'dead_code',
    actionLabel: 'View Dead Code Analysis',
  },
  {
    pattern: /\b(api(s)?|endpoints?|routes?|rest api|http methods?|post \/|get \/|put \/|delete \/|openapi|swagger|fastapi|flask route)\b/i,
    intent: 'API',
    confidence: 0.92,
    actionTarget: 'api_surface',
    actionLabel: 'Open API Surface',
  },
  {
    pattern: /\b(git|history|commits?|recent(ly)? changed|who wrote|when was.*changed|changelog|blame|churn)\b/i,
    intent: 'GIT_HISTORY',
    confidence: 0.90,
    actionTarget: 'git_history',
    actionLabel: 'Inspect Git History',
  },
  {
    pattern: /\b(pr risk|pull request|review risk|drift|merge risk|architecture drift)\b/i,
    intent: 'PR_RISK',
    confidence: 0.90,
    actionTarget: 'pr_intelligence',
    actionLabel: 'Open PR Intelligence',
  },
  {
    pattern: /\b(health|score|grade|quality|maintainability|bottlenecks?|risky areas?|vulnerabilit(y|ies))\b/i,
    intent: 'HEALTH',
    confidence: 0.90,
    actionTarget: 'report',
    actionLabel: 'Review Health Report',
  },
  {
    pattern: /\b(reading (path|order)|read first|onboard(ing)?|where to start|start reading|what should I read)\b/i,
    intent: 'READING_PATH',
    confidence: 0.92,
    actionTarget: 'reading_path',
    actionLabel: 'Follow Reading Path',
  },
  {
    pattern: /\b(circular|cycle|cyclic|circular.depend|import.loop|dependency.cycle|packages?|external libraries|dependencies)\b/i,
    intent: 'DEPENDENCY',
    confidence: 0.92,
    actionTarget: 'graph',
    actionLabel: 'Explore Dependencies in Graph',
  },
  {
    pattern: /\b(where is .* defined|find definition|what is .* class|what is .* function|definition of)\b/i,
    intent: 'SYMBOL_EXPLANATION',
    confidence: 0.88,
    actionTarget: 'call_graph',
    actionLabel: 'Trace Symbol in Call Graph',
  },
  {
    pattern: /\b(what does (?:file |module )?[\w./\\-]+\.(?:py|ts|tsx|js|jsx|go|rs|java|c|cpp|h|json|md)\b.*|explain (?:file |module )?[\w./\\-]+\.(?:py|ts|tsx|js|jsx|go|rs|java)\b|where is .* implemented|where is .* file|what does .* (file|module))\b/i,
    intent: 'FILE_EXPLANATION',
    confidence: 0.88,
    actionTarget: 'graph',
    actionLabel: 'Inspect File in Graph',
  },
  {
    pattern: /\b(architect(ure)?|structure|components?|layers?|high level|monolith|microservice|data flow|execution flow|pipeline)\b/i,
    intent: 'ARCHITECTURE',
    confidence: 0.90,
    actionTarget: 'graph',
    actionLabel: 'Inspect Architecture Topology',
  },
  {
    pattern: /\b(what does this (repo|repository|codebase|project) do|overview|summary|purpose|what is this)\b/i,
    intent: 'OVERVIEW',
    confidence: 0.90,
    actionTarget: 'reading_path',
    actionLabel: 'Explore Guided Reading Path',
  },
];

// Regex to capture file paths mentioned in queries
const FILE_PATH_REGEX = /\b([\w-]+\/)*[\w-]+\.(py|ts|tsx|js|jsx|go|rs|java|cpp|c|h|cs|php|rb|json|yaml|yml|toml|md)\b/gi;

// Regex to capture symbol/function mentions (e.g., extract_features(), getUserData, calculateScore)
const SYMBOL_REGEX = /\b([a-zA-Z_][a-zA-Z0-9_]+)\(\)|\b([A-Z][a-zA-Z0-9]{2,}(?:[A-Z][a-z0-9]+)*)\b/g;

export function detectChatIntent(query: string): IntentAnalysis {
  const clean = (query || '').trim();
  if (!clean) {
    return { intent: 'GENERAL_REPOSITORY', confidence: 0.5, entities: [] };
  }

  // Extract entities
  const entities: ExtractedEntity[] = [];
  const fileMatches = clean.match(FILE_PATH_REGEX) || [];
  fileMatches.forEach((f) => {
    entities.push({ type: 'file', raw: f, normalized: f.replace(/\\/g, '/') });
  });

  const symbolMatches = clean.match(SYMBOL_REGEX) || [];
  symbolMatches.forEach((s) => {
    const cleanSym = s.replace(/\(\)$/, '');
    if (!entities.some((e) => e.normalized === cleanSym)) {
      entities.push({ type: 'symbol', raw: s, normalized: cleanSym });
    }
  });

  for (const rule of INTENT_RULES) {
    if (rule.pattern.test(clean)) {
      return {
        intent: rule.intent,
        confidence: rule.confidence,
        entities,
        actionTarget: rule.actionTarget,
        actionLabel: rule.actionLabel,
      };
    }
  }

  return {
    intent: 'GENERAL_REPOSITORY',
    confidence: 0.65,
    entities,
    actionTarget: 'graph',
    actionLabel: 'Inspect in File Graph',
  };
}

// ---------------------------------------------------------------------------
// 2. Dynamic Suggested Prompts Generation
// ---------------------------------------------------------------------------

export function generateSuggestedPrompts(config: DynamicPromptConfig): string[] {
  const {
    repoName,
    techStack = [],
    dependencies = [],
    entryPoints = [],
    cyclesCount = 0,
    readingSteps = 0,
    healthScore,
  } = config;

  const depLower = dependencies.map((d) => d.toLowerCase());
  const techLower = techStack.map((t) => t.toLowerCase());
  const hasMl = depLower.some((d) => ['torch', 'tensorflow', 'scikit-learn', 'sklearn', 'transformers', 'keras', 'joblib'].includes(d));
  const hasWebApi = depLower.some((d) => ['fastapi', 'flask', 'express', 'django', 'koa', 'nest'].includes(d)) || techLower.includes('fastapi') || techLower.includes('flask');

  const prompts: string[] = [];

  // 1. Core Purpose / Flow
  if (hasMl && hasWebApi) {
    prompts.push('How does the machine learning inference pipeline and API flow work?');
  } else if (hasWebApi) {
    prompts.push('What API endpoints does this repository expose and how are they structured?');
  } else if (hasMl) {
    prompts.push('How does the data preprocessing and model evaluation pipeline operate?');
  } else {
    prompts.push(`What does ${repoName ? repoName.split('/').pop() : 'this repository'} do and what is its primary use?`);
  }

  // 2. Entry Points & Onboarding
  if (entryPoints.length > 0) {
    prompts.push(`What does the entry point ${entryPoints[0]} do and what does it call?`);
  } else if (readingSteps > 0) {
    prompts.push('What is the recommended reading path and what should I read first?');
  }

  // 3. Architecture & Impact
  if (cyclesCount > 0) {
    prompts.push(`Where are the ${cyclesCount} architectural cycles located and how can they be resolved?`);
  } else {
    prompts.push('What are the key architectural components and high-centrality modules?');
  }

  // 4. Change Planning / Health
  if (typeof healthScore === 'number' && healthScore < 80) {
    prompts.push('What architectural bottlenecks or warnings need attention in this repository?');
  } else {
    prompts.push('What files would I need to modify to add authentication or rate limiting?');
  }

  return prompts.slice(0, 4);
}

// ---------------------------------------------------------------------------
// 3. Contextual Follow-up Synthesis
// ---------------------------------------------------------------------------

export function generateFollowUpPrompts(
  query: string,
  intent: ChatIntent,
  responseText?: string,
  sources: string[] = []
): string[] {
  const followUps: string[] = [];
  const cleanSources = deduplicateSources(sources);
  const text = (responseText || '') + ' ' + (query || '');

  // Extract files from text & sources
  const fileRegex = /\b([\w./\\-]+\.(py|ts|tsx|js|jsx|java|go|rs|rb|php|cs|cpp|c|h|json|md|pkl|onnx))\b/gi;
  const foundFiles = new Set<string>(cleanSources);
  let match: RegExpExecArray | null;
  while ((match = fileRegex.exec(text)) !== null) {
    const f = match[1].replace(/\\/g, '/');
    if (!f.includes('node_modules') && !f.includes('.git')) {
      foundFiles.add(f);
    }
  }
  const fileList = Array.from(foundFiles);
  const primaryFile = fileList[0] || '';
  const secondaryFile = fileList[1] || '';

  // Extract function / symbol names in backticks
  const symbolRegex = /`([a-zA-Z_][a-zA-Z0-9_]{2,})(?:\(\))?`/g;
  const foundSymbols = new Set<string>();
  while ((match = symbolRegex.exec(text)) !== null) {
    const sym = match[1];
    if (!sym.includes('.') && !['file', 'true', 'false', 'null', 'undefined', 'string', 'number'].includes(sym.toLowerCase())) {
      foundSymbols.add(sym);
    }
  }
  const symbolList = Array.from(foundSymbols);
  const primarySymbol = symbolList[0] || '';
  const secondarySymbol = symbolList[1] || '';

  // Extract endpoints
  const endpointRegex = /(?:GET|POST|PUT|DELETE)?\s*(\/\w+(?:\/[\w-]+)*)/gi;
  const foundEndpoints = new Set<string>();
  while ((match = endpointRegex.exec(text)) !== null) {
    const ep = match[1];
    if (!ep.endsWith('.py') && !ep.endsWith('.js') && ep.length > 1) {
      foundEndpoints.add(ep);
    }
  }
  const endpointList = Array.from(foundEndpoints);
  const primaryEndpoint = endpointList[0] || '';

  // ── 1. Concrete Entity-Driven Follow-Up Synthesis ──────────────────────

  // Pattern A: Function drilldown & Call Graph
  if (primarySymbol && primaryFile) {
    if (secondarySymbol) {
      followUps.push(`How does \`${primarySymbol}()\` in \`${primaryFile}\` pass data to \`${secondarySymbol}()\`?`);
    } else {
      followUps.push(`How does \`${primarySymbol}()\` in \`${primaryFile}\` execute its core transformation?`);
    }
    followUps.push(`What callers invoke \`${primarySymbol}()\` across the repository?`);
  } else if (primaryFile) {
    followUps.push(`What upstream callers invoke \`${primaryFile}\`, and what are its direct dependencies?`);
  }

  // Pattern B: Endpoint / API validation
  if (primaryEndpoint) {
    const targetFile = primaryFile || 'the backend';
    followUps.push(`How does the \`${primaryEndpoint}\` endpoint in \`${targetFile}\` validate input payloads and handle errors?`);
  }

  // Pattern C: Cross-file interaction & Change Impact
  if (primaryFile && secondaryFile) {
    followUps.push(`What changes would be required in \`${primaryFile}\` if the schema or interface in \`${secondaryFile}\` changed?`);
  }

  // Pattern D: ML Artifact / Model origin
  if (text.toLowerCase().includes('model') || text.toLowerCase().includes('predict') || text.toLowerCase().includes('randomforest') || text.toLowerCase().includes('.pkl')) {
    const pklFile = fileList.find((f) => f.endsWith('.pkl') || f.endsWith('.onnx') || f.endsWith('.pt')) || 'the model artifact';
    followUps.push(`Where is \`${pklFile}\` produced during training, and how does \`predict_model()\` load it?`);
  }

  // Pattern E: Intent-specific follow-ups with entity grounding
  if (followUps.length < 3) {
    switch (intent) {
      case 'CALL_GRAPH':
        if (primaryFile) {
          followUps.push(`What is the full upstream invocation chain for \`${primaryFile}\`?`);
        } else {
          followUps.push('What is the full upstream invocation chain in the call graph?');
        }
        break;
      case 'API':
      case 'API_FLOW':
        if (primaryFile) {
          followUps.push(`Where are the request validation models and schemas defined for \`${primaryFile}\`?`);
        } else {
          followUps.push('Where are the API route controllers and request validation models defined?');
        }
        break;

      case 'CHANGE_PLANNING':
      case 'IMPACT_ANALYSIS':
        if (primaryFile) {
          followUps.push(`What is the recommended implementation order when modifying \`${primaryFile}\`?`);
        } else {
          followUps.push('What downstream components are in the blast radius of this proposed change?');
        }
        break;

      case 'DEBUGGING':
        if (primaryFile) {
          followUps.push(`What failure points or unhandled exceptions exist along the execution path in \`${primaryFile}\`?`);
        } else {
          followUps.push('What execution paths are most susceptible to runtime exceptions?');
        }
        break;

      case 'DEPENDENCY':
        if (primaryFile) {
          followUps.push(`Which files have high coupling with \`${primaryFile}\` and could form import cycles?`);
        } else {
          followUps.push('Which packages and internal modules have the highest coupling centrality?');
        }
        break;

      default:
        if (primaryFile) {
          followUps.push(`What automated unit or regression tests cover the logic in \`${primaryFile}\`?`);
        }
    }
  }

  // Deduplicate and return top 2–3
  const unique = Array.from(new Set(followUps)).filter((q) => q.trim().length > 10);
  return unique.slice(0, 3);
}

// ---------------------------------------------------------------------------
// 4. Secret & Sensitive Data Redaction
// ---------------------------------------------------------------------------

const SECRET_PATTERNS: Array<{ pattern: RegExp; replacement: string }> = [
  // OpenAI & LLM API Keys
  { pattern: /\b(sk-[a-zA-Z0-9_-]{20,})\b/g, replacement: '[REDACTED_KEY]' },
  // GitHub Personal Access Tokens
  { pattern: /\b(ghp_[a-zA-Z0-9]{30,})\b/g, replacement: '[REDACTED_GH_TOKEN]' },
  // Bearer / Authorization Headers
  { pattern: /\b(Bearer\s+)[a-zA-Z0-9._-]{25,}\b/gi, replacement: '$1[REDACTED_BEARER_TOKEN]' },
  // AWS Access Key IDs
  { pattern: /\b(AKIA[0-9A-Z]{16})\b/g, replacement: '[REDACTED_AWS_CREDENTIAL]' },
  // Google API Keys
  { pattern: /\b(AIza[0-9A-Za-z-_]{35})\b/g, replacement: '[REDACTED_GOOGLE_CREDENTIAL]' },
  // Private Key Blocks
  {
    pattern: /-----BEGIN (?:RSA|OPENSSH|EC|DSA|PGP|PRIVATE) KEY-----[a-zA-Z0-9+/=\s]+-----END (?:RSA|OPENSSH|EC|DSA|PGP|PRIVATE) KEY-----/g,
    replacement: '[REDACTED_PRIVATE_KEY]',
  },
  // Passwords in config/connection strings
  { pattern: /(password\s*[:=]\s*['"])[^'"]{4,}(['"])/gi, replacement: '$1[REDACTED_PASSWORD]$2' },
];

export function redactSecrets(content: string): string {
  if (!content) return '';
  let clean = content;
  for (const { pattern, replacement } of SECRET_PATTERNS) {
    clean = clean.replace(pattern, replacement);
  }
  return clean;
}

// ---------------------------------------------------------------------------
// 5. Memory & Pronoun Context Resolution
// ---------------------------------------------------------------------------

export function resolvePronouns(
  userQuery: string,
  lastReferencedEntity: string | null
): string {
  if (!lastReferencedEntity) return userQuery;

  const pronounRegex = /\b(it|this|that|there|those functions|this file|the module)\b/i;
  if (pronounRegex.test(userQuery) && !userQuery.toLowerCase().includes(lastReferencedEntity.toLowerCase())) {
    return `${userQuery} (referring to ${lastReferencedEntity})`;
  }
  return userQuery;
}

// ---------------------------------------------------------------------------
// 6. Semantic Evidence Levels & Hierarchy Extraction
// ---------------------------------------------------------------------------

export type EvidenceLevel = 'VERIFIED' | 'STRONGLY INFERRED' | 'INFERRED' | 'UNKNOWN';

export interface StructuredEvidenceItem {
  id: string;
  filePath: string;
  lineRange?: string;
  level: EvidenceLevel;
  role: string;
  whyItMatters: string;
  codeSnippet?: string;
  subsystem?: string;
}

export interface KeyFileItem {
  filePath: string;
  role: string;
}

export interface ParsedAnswerHierarchy {
  answerSummary: string;
  keyFindings: string[];
  keyFiles: KeyFileItem[];
  evidenceItems: StructuredEvidenceItem[];
  groundingStatus: 'VERIFIED' | 'STRONGLY INFERRED' | 'PARTIALLY GROUNDED' | 'INSUFFICIENT EVIDENCE';
}

/**
 * Deduplicates and normalizes file source paths.
 */
export function deduplicateSources(sources: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const src of sources || []) {
    const clean = (src || '').trim().replace(/\\/g, '/');
    if (clean && !seen.has(clean.toLowerCase())) {
      seen.add(clean.toLowerCase());
      out.push(clean);
    }
  }
  return out;
}

/**
 * Derives role, subsystem, and engineering significance for a source file.
 */
export function deriveFileRoleAndSignificance(filePath: string): { role: string; subsystem: string; whyItMatters: string; level: EvidenceLevel } {
  const lower = filePath.toLowerCase();
  const fileName = filePath.split('/').pop() || filePath;

  if (['app.py', 'main.py', 'index.ts', 'server.js', 'index.js', 'main.go', 'main.rs'].includes(fileName.toLowerCase())) {
    return {
      role: 'Entry Point / API Orchestration',
      subsystem: 'API Flow',
      whyItMatters: `Defines primary application entry root and initializes routing/inference execution.`,
      level: 'VERIFIED',
    };
  }

  if (lower.includes('feature') || lower.includes('transform') || lower.includes('preprocess') || lower.includes('pipeline')) {
    return {
      role: 'Feature Engineering / Data Pipeline',
      subsystem: 'Feature Engineering',
      whyItMatters: `Transforms raw inputs into structured feature representations for computation.`,
      level: 'VERIFIED',
    };
  }

  if (lower.includes('model') || lower.includes('classifier') || lower.includes('predict') || lower.includes('infer')) {
    return {
      role: 'Model Inference / Computational Core',
      subsystem: 'Model Inference',
      whyItMatters: `Executes algorithmic evaluation and returns domain predictions.`,
      level: 'VERIFIED',
    };
  }

  if (lower.includes('util') || lower.includes('helper') || lower.includes('common')) {
    return {
      role: 'Shared Utility Engine',
      subsystem: 'Utility Layer',
      whyItMatters: `Provides helper routines and shared logic consumed across subsystems.`,
      level: 'STRONGLY INFERRED',
    };
  }

  if (lower.includes('test') || lower.includes('spec') || lower.includes('__tests__')) {
    return {
      role: 'Automated Test Suite',
      subsystem: 'Test Coverage',
      whyItMatters: `Provides regression and unit verification for core application flows.`,
      level: 'VERIFIED',
    };
  }

  if (lower.includes('route') || lower.includes('controller') || lower.includes('api') || lower.includes('endpoint')) {
    return {
      role: 'API Route Controller',
      subsystem: 'API Flow',
      whyItMatters: `Handles HTTP endpoints, request serialization, and response formatting.`,
      level: 'VERIFIED',
    };
  }

  if (lower.includes('config') || lower.includes('setting') || lower.includes('env')) {
    return {
      role: 'Configuration / Environment Settings',
      subsystem: 'Configuration',
      whyItMatters: `Defines runtime parameters, database configurations, and environment secrets.`,
      level: 'STRONGLY INFERRED',
    };
  }

  if (['package.json', 'requirements.txt', 'pyproject.toml', 'cargo.toml', 'go.mod'].includes(fileName.toLowerCase())) {
    return {
      role: 'Package Dependency Manifest',
      subsystem: 'Manifests',
      whyItMatters: `Declares external package requirements and runtime dependencies.`,
      level: 'VERIFIED',
    };
  }

  return {
    role: 'Supporting Module',
    subsystem: 'Core Subsystem',
    whyItMatters: `Contains implementation routines supporting primary repository operations.`,
    level: 'INFERRED',
  };
}

/**
 * Extracts structured answer hierarchy (Answer summary, Key Findings, Key Files, Evidence Items, Grounding Status).
 */
export function parseAnswerHierarchy(
  rawText: string,
  sources: string[] = [],
  confidence?: number
): ParsedAnswerHierarchy {
  const cleanSources = deduplicateSources(sources);
  const cleanText = (rawText || '').trim();

  // Determine grounding status
  let groundingStatus: ParsedAnswerHierarchy['groundingStatus'] = 'VERIFIED';
  if (!cleanText || cleanText.includes('insufficient evidence') || cleanText.includes('could not establish') || cleanText.includes('could not be confidently inferred')) {
    groundingStatus = 'INSUFFICIENT EVIDENCE';
  } else if (cleanSources.length === 0 || (typeof confidence === 'number' && confidence < 60)) {
    groundingStatus = 'PARTIALLY GROUNDED';
  } else if (typeof confidence === 'number' && confidence >= 85) {
    groundingStatus = 'VERIFIED';
  } else {
    groundingStatus = 'STRONGLY INFERRED';
  }

  // Derive evidence items
  const evidenceItems: StructuredEvidenceItem[] = cleanSources.map((src, idx) => {
    const { role, subsystem, whyItMatters, level } = deriveFileRoleAndSignificance(src);
    return {
      id: `ev-${idx}-${src}`,
      filePath: src,
      level,
      role,
      subsystem,
      whyItMatters,
    };
  });

  // Extract Key Files if 2+ sources exist
  const keyFiles: KeyFileItem[] = cleanSources.slice(0, 5).map((src) => {
    const { role } = deriveFileRoleAndSignificance(src);
    return { filePath: src, role };
  });

  // Extract key findings from bullet points if present, or summarize first lines
  const keyFindings: string[] = [];
  const bulletLines = cleanText.split('\n').filter((l) => /^\s*[-*•]\s+/.test(l));
  if (bulletLines.length > 0) {
    bulletLines.slice(0, 4).forEach((line) => {
      const cleanLine = line.replace(/^\s*[-*•]\s+/, '').trim();
      if (cleanLine.length > 5) {
        keyFindings.push(cleanLine);
      }
    });
  }

  return {
    answerSummary: cleanText,
    keyFindings,
    keyFiles,
    evidenceItems,
    groundingStatus,
  };
}

// ---------------------------------------------------------------------------
// 7. Interactive Tokenizer (Clickable Files, Symbols, and Confidence Badges)
// ---------------------------------------------------------------------------

export interface ParsedTextSegment {
  type: 'text' | 'file' | 'symbol' | 'confidence';
  value: string;
  meta?: string;
}

export function parseInteractiveSegments(text: string): ParsedTextSegment[] {
  const segments: ParsedTextSegment[] = [];
  const tokenRegex = /(\[VERIFIED\]|\[STRONGLY INFERRED\]|\[INFERRED\]|\[PARTIAL\]|\[UNKNOWN\]|\[NOT CONFIRMED\]|\b(?:[\w-]+\/)+[\w-]+\.(?:py|ts|tsx|js|jsx|go|rs|java|md)\b|\b[a-zA-Z_][a-zA-Z0-9_]*\(\))/g;

  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = tokenRegex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      segments.push({
        type: 'text',
        value: text.substring(lastIndex, match.index),
      });
    }

    const token = match[0];
    if (token.startsWith('[') && token.endsWith(']')) {
      segments.push({
        type: 'confidence',
        value: token.replace(/[\[\]]/g, ''),
      });
    } else if (token.includes('/') || token.includes('.')) {
      segments.push({
        type: 'file',
        value: token,
      });
    } else if (token.endsWith('()')) {
      segments.push({
        type: 'symbol',
        value: token.slice(0, -2),
        meta: token,
      });
    } else {
      segments.push({
        type: 'text',
        value: token,
      });
    }

    lastIndex = match.index + token.length;
  }

  if (lastIndex < text.length) {
    segments.push({
      type: 'text',
      value: text.substring(lastIndex),
    });
  }

  return segments;
}

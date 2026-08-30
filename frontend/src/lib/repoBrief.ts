/**
 * Repository Purpose & Capability Extraction
 *
 * Grounded extraction of repository briefing, purpose statement, primary use case,
 * and key capabilities using only verified analysis evidence (manifests, structure,
 * entry points, tech stack, architecture relationships, and documentation summaries).
 */

export interface CapabilityItem {
  title: string;
  detail: string;
  evidence: string;
  confidence: 'strong' | 'moderate' | 'inferred';
}

export type BriefConfidence = 'VERIFIED' | 'INFERRED' | 'UNKNOWN';

export interface RepoBrief {
  about: string;
  purpose: string | null;
  primaryUse: string | null;
  isConfidenceHigh: boolean;
  confidenceState: BriefConfidence;
  capabilities: CapabilityItem[];
  pipelineSteps?: string[];
}

export interface DeriveBriefParams {
  repoName: string;
  summary?: string;
  techStack: string[];
  dependencies: string[];
  structure: Record<string, string[]>;
  entryPoints: string[];
  relationships?: { source: string; target: string; relationship_type: string; description?: string }[];
}

/**
 * Clean and summarize text into 2-3 concise sentences.
 */
function cleanSummaryText(raw: string): string {
  if (!raw) return '';
  const trimmed = raw.replace(/\r\n/g, '\n').trim();
  // Remove markdown headers or backticks
  const plain = trimmed.replace(/^#+\s+/gm, '').replace(/```[\s\S]*?```/g, '').trim();
  const sentences = plain.split(/(?<=[.!?])\s+/).filter(s => s.length > 10);
  if (sentences.length <= 3) return plain;
  return sentences.slice(0, 3).join(' ');
}

/**
 * Derives a grounded repository brief based strictly on verified analysis artifacts.
 */
export function deriveRepoBrief(params: DeriveBriefParams): RepoBrief {
  const {
    repoName,
    summary = '',
    techStack = [],
    dependencies = [],
    structure = {},
    entryPoints = [],
    relationships = [],
  } = params;

  const depLower = dependencies.map((d) => d.toLowerCase());
  const techLower = techStack.map((t) => t.toLowerCase());
  const allFiles = Object.values(structure).flat();

  // ── 1. Purpose & About ───────────────────────────────────────────────────
  const hasValidSummary = summary && summary.trim().length > 15 && !summary.startsWith('Architecture summary for');

  let about = '';
  let purpose: string | null = null;
  let primaryUse: string | null = null;
  let isConfidenceHigh = false;

  if (hasValidSummary) {
    about = cleanSummaryText(summary);
    isConfidenceHigh = true;

    // Extract purpose from summary or synthesize concise fact
    const firstSentence = about.split(/(?<=[.!?])\s+/)[0] || '';
    purpose = firstSentence.length > 10 ? firstSentence : null;

    // Grounded primary use from manifest & structural evidence
    const isMlProject = depLower.some(d => ['torch', 'tensorflow', 'scikit-learn', 'sklearn', 'transformers', 'keras'].includes(d));
    const isWebApi = depLower.some(d => ['fastapi', 'flask', 'express', 'django', 'koa', 'nest'].includes(d)) || techLower.includes('fastapi') || techLower.includes('flask');
    const isExtension = allFiles.some(f => f.toLowerCase().includes('manifest.json') || f.toLowerCase().includes('extension') || f.toLowerCase().includes('popup.'));

    if (isExtension && isWebApi) {
      primaryUse = 'Browser-integrated URL analysis and prediction API';
    } else if (isMlProject && isWebApi) {
      primaryUse = 'Automated model inference via REST endpoints';
    } else if (isWebApi) {
      primaryUse = 'REST API service handling client requests';
    } else if (isMlProject) {
      primaryUse = 'Data evaluation and algorithmic prediction';
    } else if (entryPoints.length > 0) {
      primaryUse = `Direct execution via ${entryPoints[0].split('/').pop()}`;
    }
  } else {
    // Grounded fallback from verified file patterns
    const slug = repoName.split('/').pop() || repoName;
    const cleanSlug = slug.replace(/[-_]/g, ' ');

    const isMlProject = depLower.some(d => ['torch', 'tensorflow', 'scikit-learn', 'sklearn', 'transformers', 'keras'].includes(d));
    const isWebApi = depLower.some(d => ['fastapi', 'flask', 'express', 'django', 'koa', 'nest'].includes(d)) || techLower.includes('fastapi') || techLower.includes('flask');
    const isExtension = allFiles.some(f => f.toLowerCase().includes('manifest.json') || f.toLowerCase().includes('extension') || f.toLowerCase().includes('popup.'));

    if (isMlProject && isWebApi) {
      about = `${slug} provides a machine learning inference backend and web service built with ${techStack.slice(0, 3).join(', ')}.`;
      purpose = `Machine learning prediction and classification service`;
      primaryUse = isExtension ? `Browser-integrated URL analysis and prediction API` : `Automated model inference via REST endpoints`;
      isConfidenceHigh = true;
    } else if (isWebApi) {
      about = `${slug} is a web service application providing backend endpoints and data processing routines.`;
      purpose = `Backend API and service orchestration`;
      primaryUse = `REST API service handling client requests`;
      isConfidenceHigh = true;
    } else if (isMlProject) {
      about = `${slug} contains data science and machine learning models for classification and computational analysis.`;
      purpose = `Machine learning model training and inference`;
      primaryUse = `Data evaluation and algorithmic prediction`;
      isConfidenceHigh = true;
    } else if (entryPoints.length > 0 && techStack.length > 0) {
      about = `${slug} is a ${techStack[0]}-based codebase structured around ${entryPoints.length} executable entry ${entryPoints.length === 1 ? 'point' : 'points'}.`;
      purpose = `${cleanSlug} execution and utilities`;
      primaryUse = `Direct application execution via ${entryPoints[0].split('/').pop()}`;
      isConfidenceHigh = false;
    } else {
      about = `Purpose not confidently inferred from repository manifests alone. Explore the file structure or ask ARIA for a grounded explanation.`;
      purpose = null;
      primaryUse = null;
      isConfidenceHigh = false;
    }
  }

  // ── 2. Capabilities ──────────────────────────────────────────────────────
  const capabilities: CapabilityItem[] = [];

  // Capability: Web API
  const webFramework = dependencies.find(d => ['fastapi', 'flask', 'express', 'django', 'koa', 'aiohttp', 'tornado'].includes(d.toLowerCase()))
    || techStack.find(t => ['fastapi', 'flask', 'express', 'django'].includes(t.toLowerCase()));
  if (webFramework) {
    capabilities.push({
      title: 'REST API & Web Service',
      detail: `Provides HTTP service endpoints and routing powered by ${webFramework}.`,
      evidence: `Resolved in dependency manifest (${webFramework})`,
      confidence: 'strong',
    });
  }

  // Capability: ML / Prediction
  const mlDeps = dependencies.filter(d => ['torch', 'pytorch', 'tensorflow', 'scikit-learn', 'sklearn', 'transformers', 'numpy', 'pandas', 'joblib', 'scipy'].includes(d.toLowerCase()));
  if (mlDeps.length > 0) {
    const isPredictive = mlDeps.some(d => ['torch', 'scikit-learn', 'transformers', 'tensorflow', 'sklearn'].includes(d.toLowerCase()));
    capabilities.push({
      title: isPredictive ? 'ML Model Inference & Classification' : 'Data Processing & Numerical Analysis',
      detail: isPredictive
        ? `Appears to support machine learning evaluation and classification (${mlDeps.slice(0, 3).join(', ')}).`
        : `Provides numerical and tabular data processing pipelines.`,
      evidence: `Resolved in dependencies (${mlDeps.slice(0, 3).join(', ')})`,
      confidence: isPredictive ? 'strong' : 'moderate',
    });
  }

  // Capability: Browser / Client Extension
  const hasExtensionFiles = allFiles.some(f => f.toLowerCase().includes('manifest.json') || f.toLowerCase().includes('popup.html') || f.toLowerCase().includes('popup.js') || f.toLowerCase().includes('background.js'));
  if (hasExtensionFiles) {
    capabilities.push({
      title: 'Browser Extension & Client UI',
      detail: 'Provides browser extension manifests and client-side interaction scripts.',
      evidence: 'Resolved in file structure (manifest / popup scripts)',
      confidence: 'strong',
    });
  }

  // Capability: Entry Points
  if (entryPoints.length > 0) {
    const mainFiles = entryPoints.slice(0, 2).map(p => p.split('/').pop()).join(', ');
    capabilities.push({
      title: 'Executable Starting Points',
      detail: `Supports direct application execution via ${mainFiles}.`,
      evidence: `Resolved in root source structure`,
      confidence: 'strong',
    });
  }

  // Capability: Architecture Boundaries
  if (relationships.length > 0) {
    capabilities.push({
      title: 'Modular Component Architecture',
      detail: `Coordinates data flow across ${relationships.length} explicit cross-component boundaries.`,
      evidence: `Derived from repository architecture graph`,
      confidence: 'moderate',
    });
  }

  // Capability: Tests
  const hasTests = allFiles.some(f => f.includes('test') || f.includes('spec'));
  if (hasTests) {
    capabilities.push({
      title: 'Automated Test Suite',
      detail: 'Maintains automated verification test suites for codebase validation.',
      evidence: 'Detected in test directory structure',
      confidence: 'moderate',
    });
  }

  // ── 3. High-Level "How It Works" Flow ─────────────────────────────────────
  let pipelineSteps: string[] | undefined;

  if (webFramework && mlDeps.length > 0 && hasExtensionFiles) {
    pipelineSteps = [
      'Client / Browser Input',
      `${webFramework} API Endpoint`,
      'Feature Extraction',
      'ML Model Inference',
      'Prediction Response',
    ];
  } else if (webFramework && mlDeps.length > 0) {
    pipelineSteps = [
      'HTTP Request',
      `${webFramework} Controller`,
      'Data Preprocessing',
      'ML Inference',
      'JSON Response',
    ];
  } else if (webFramework) {
    pipelineSteps = [
      'Client Request',
      `${webFramework} Routing`,
      'Business Logic',
      'Service Response',
    ];
  } else if (entryPoints.length > 0 && mlDeps.length > 0) {
    pipelineSteps = [
      'Executable Input',
      'Dataset Preprocessing',
      'Model Computation',
      'Output Evaluation',
    ];
  }

  let confidenceState: BriefConfidence = 'UNKNOWN';
  if (hasValidSummary) {
    confidenceState = 'VERIFIED';
  } else if (purpose !== null || primaryUse !== null) {
    confidenceState = 'INFERRED';
  } else {
    confidenceState = 'UNKNOWN';
  }

  return {
    about,
    purpose,
    primaryUse,
    isConfidenceHigh,
    confidenceState,
    capabilities: capabilities.slice(0, 5),
    pipelineSteps,
  };
}

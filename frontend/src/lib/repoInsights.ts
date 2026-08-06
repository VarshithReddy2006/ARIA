/**
 * Executive insight derivation.
 *
 * Turns the already-fetched analysis payload into a ranked set of plain-language
 * findings. Every insight is derived from real indexed data — nothing is
 * hardcoded, and nothing is asserted that the data cannot support.
 *
 * Pure functions only, so the rules are unit-testable without React.
 */

export type InsightSeverity = 'good' | 'warn' | 'risk' | 'neutral';

export interface Insight {
  id: string;
  title: string;
  /** One-sentence explanation, always citing the concrete number behind it. */
  detail: string;
  severity: InsightSeverity;
  /** Longer tooltip text explaining how the finding was derived. */
  tooltip: string;
  /** Named icon, resolved to a component by the presentation layer. */
  icon: InsightIcon;
}

export type InsightIcon =
  | 'architecture'
  | 'dependency'
  | 'entrypoint'
  | 'scale'
  | 'onboarding'
  | 'monorepo'
  | 'language'
  | 'cycle'
  | 'docs'
  | 'tests'
  | 'api';

export interface InsightInputs {
  fileCount: number;
  directoryCount: number;
  dependencyCount: number;
  techStack: string[];
  /** Directory -> file paths, exactly as returned by the analysis endpoint. */
  structure: Record<string, string[]>;
  entryPointCount: number;
  cycleCount: number;
  componentCount: number;
  relationshipCount: number;
  readingSteps: number;
  readingMinutes: number;
}

/** Files-per-directory density above which a repo reads as "dense". */
const DENSE_FILES_PER_DIR = 6;
const DENSE_FILE_COUNT = 400;
/** Dependency count above which the external surface is worth flagging. */
const HIGH_DEPENDENCY_COUNT = 60;
/** Onboarding minutes below which onboarding counts as fast. */
const FAST_ONBOARDING_MINUTES = 45;

const MONOREPO_DIR_HINTS = ['packages/', 'apps/', 'services/', 'libs/', 'modules/'];
const DOC_FILE_HINTS = [
  'readme', 'contributing', 'architecture', 'changelog', 'docs/',
  'deployment', 'installation', 'security', 'faq', 'roadmap',
];
const TEST_PATH_HINTS = ['test', 'spec', '__tests__', '.test.', '.spec.'];

function allFilePaths(structure: Record<string, string[]>): string[] {
  return Object.values(structure ?? {}).flat();
}

/**
 * Detects a monorepo by looking for multiple top-level workspace directories
 * under a conventional container (packages/, apps/, services/, ...).
 */
export function detectMonorepo(structure: Record<string, string[]>): {
  isMonorepo: boolean;
  workspaces: string[];
} {
  const directories = Object.keys(structure ?? {});
  const workspaces = new Set<string>();

  for (const dir of directories) {
    const normalized = dir.replace(/\\/g, '/').replace(/^\.\//, '');
    for (const hint of MONOREPO_DIR_HINTS) {
      const idx = normalized.indexOf(hint);
      if (idx !== 0) continue;
      const remainder = normalized.slice(hint.length);
      const workspace = remainder.split('/')[0];
      if (workspace) workspaces.add(`${hint}${workspace}`);
    }
  }

  return { isMonorepo: workspaces.size >= 2, workspaces: Array.from(workspaces).sort() };
}

/** Counts files that look like project documentation. */
export function countDocumentation(structure: Record<string, string[]>): number {
  return allFilePaths(structure).filter((path) => {
    const lower = path.toLowerCase();
    if (!lower.endsWith('.md') && !lower.endsWith('.mdx') && !lower.includes('docs/')) return false;
    return DOC_FILE_HINTS.some((hint) => lower.includes(hint));
  }).length;
}

/** Counts files that look like automated tests. */
export function countTestFiles(structure: Record<string, string[]>): number {
  return allFilePaths(structure).filter((path) => {
    const lower = path.toLowerCase();
    return TEST_PATH_HINTS.some((hint) => lower.includes(hint));
  }).length;
}

/** Ranking so the most actionable findings lead the strip. */
const SEVERITY_RANK: Record<InsightSeverity, number> = {
  risk: 0,
  warn: 1,
  good: 2,
  neutral: 3,
};

/**
 * Builds the executive insight set. Returns findings ordered by severity
 * (risks first) so the strip leads with what needs attention.
 */
export function deriveInsights(input: InsightInputs): Insight[] {
  const insights: Insight[] = [];

  const {
    fileCount, directoryCount, dependencyCount, techStack, structure,
    entryPointCount, cycleCount, componentCount, relationshipCount,
    readingSteps, readingMinutes,
  } = input;

  // ── Architecture stability ─────────────────────────────────────────────
  if (relationshipCount > 0) {
    if (cycleCount > 0) {
      insights.push({
        id: 'cycles',
        title: 'Circular Dependencies',
        detail: `${cycleCount} dependency ${cycleCount === 1 ? 'cycle' : 'cycles'} detected between components.`,
        severity: 'risk',
        tooltip:
          'Cycles were found by depth-first traversal of the component relationship graph. ' +
          'They make modules hard to test and change in isolation.',
        icon: 'cycle',
      });
    } else {
      insights.push({
        id: 'acyclic',
        title: 'Stable Architecture',
        detail: `No circular dependencies across ${componentCount} components.`,
        severity: 'good',
        tooltip:
          'Depth-first traversal of the component relationship graph found no cycles, ' +
          'so components can be reasoned about in dependency order.',
        icon: 'architecture',
      });
    }
  } else {
    insights.push({
      id: 'independent-modules',
      title: 'Independent Modules',
      detail: 'No cross-component imports detected — modules appear self-contained.',
      severity: 'neutral',
      tooltip:
        'The architecture agent found no imports between top-level packages. This is common ' +
        'in flat layouts and in repositories of independent services.',
      icon: 'architecture',
    });
  }

  // ── Entry points ───────────────────────────────────────────────────────
  if (entryPointCount > 1) {
    insights.push({
      id: 'multi-entry',
      title: 'Multiple Entry Points',
      detail: `${entryPointCount} executable application entry points.`,
      severity: 'good',
      tooltip:
        'Entry points are inferred from conventional filenames (main, app, index, server, manage). ' +
        'Several of them usually indicates multiple deployable surfaces.',
      icon: 'entrypoint',
    });
  } else if (entryPointCount === 1) {
    insights.push({
      id: 'single-entry',
      title: 'Single Entry Point',
      detail: 'One executable entry point — a focused, single-surface project.',
      severity: 'good',
      tooltip: 'Entry points are inferred from conventional filenames such as main, app, index, or server.',
      icon: 'entrypoint',
    });
  }

  // ── Dependency surface ─────────────────────────────────────────────────
  if (dependencyCount >= HIGH_DEPENDENCY_COUNT) {
    insights.push({
      id: 'high-deps',
      title: 'High Dependency Surface',
      detail: `${dependencyCount} declared dependencies to audit and keep current.`,
      severity: 'warn',
      tooltip:
        `Resolved from the repository's dependency manifests. Above ~${HIGH_DEPENDENCY_COUNT} packages, ` +
        'upgrade and vulnerability review becomes a recurring maintenance cost.',
      icon: 'dependency',
    });
  } else if (dependencyCount > 0) {
    insights.push({
      id: 'lean-deps',
      title: 'Lean Dependency Surface',
      detail: `${dependencyCount} declared ${dependencyCount === 1 ? 'dependency' : 'dependencies'}.`,
      severity: 'good',
      tooltip:
        'Resolved from the repository dependency manifests. A small external surface keeps ' +
        'upgrades and security review cheap.',
      icon: 'dependency',
    });
  }

  // ── Repository scale ───────────────────────────────────────────────────
  const filesPerDir = directoryCount > 0 ? fileCount / directoryCount : fileCount;
  if (fileCount >= DENSE_FILE_COUNT || filesPerDir >= DENSE_FILES_PER_DIR) {
    insights.push({
      id: 'dense-repo',
      title: 'Dense Repository',
      detail: `${fileCount.toLocaleString()} files across ${directoryCount.toLocaleString()} directories.`,
      severity: 'warn',
      tooltip:
        `Averages ${filesPerDir.toFixed(1)} files per directory. Large or densely packed trees ` +
        'take longer to navigate, so lean on the reading path and graph rather than browsing.',
      icon: 'scale',
    });
  } else {
    insights.push({
      id: 'compact-repo',
      title: 'Compact Repository',
      detail: `${fileCount.toLocaleString()} files across ${directoryCount.toLocaleString()} directories.`,
      severity: 'good',
      tooltip:
        `Averages ${filesPerDir.toFixed(1)} files per directory — small enough to explore directly.`,
      icon: 'scale',
    });
  }

  // ── Onboarding effort ──────────────────────────────────────────────────
  if (readingSteps > 0) {
    const fast = readingMinutes <= FAST_ONBOARDING_MINUTES;
    insights.push({
      id: 'onboarding',
      title: fast ? 'Fast Onboarding' : 'Extended Onboarding',
      detail: `Recommended reading path spans ${readingSteps} files, about ${readingMinutes} minutes.`,
      severity: fast ? 'good' : 'warn',
      tooltip:
        'Estimated from the ranked reading path at roughly six minutes of attentive reading per file. ' +
        'Treat it as relative effort, not a precise duration.',
      icon: 'onboarding',
    });
  }

  // ── Monorepo shape ─────────────────────────────────────────────────────
  const { isMonorepo, workspaces } = detectMonorepo(structure);
  if (isMonorepo) {
    insights.push({
      id: 'monorepo',
      title: 'Monorepo Detected',
      detail: `${workspaces.length} workspaces under shared directories.`,
      severity: 'good',
      tooltip:
        `Detected conventional workspace roots: ${workspaces.slice(0, 6).join(', ')}` +
        `${workspaces.length > 6 ? '…' : ''}. Shared packages are usually the highest-leverage reading.`,
      icon: 'monorepo',
    });
  }

  // ── Documentation ──────────────────────────────────────────────────────
  const docCount = countDocumentation(structure);
  if (docCount >= 5) {
    insights.push({
      id: 'strong-docs',
      title: 'Strong Documentation',
      detail: `${docCount} documentation files available to read first.`,
      severity: 'good',
      tooltip:
        'Counts Markdown files matching conventional documentation names (README, ARCHITECTURE, ' +
        'CONTRIBUTING, docs/, and similar).',
      icon: 'docs',
    });
  } else if (docCount === 0) {
    insights.push({
      id: 'no-docs',
      title: 'Sparse Documentation',
      detail: 'No conventional documentation files detected.',
      severity: 'warn',
      tooltip:
        'No Markdown files matched conventional documentation names. Expect to rely on code ' +
        'reading and the AI chat instead of prose.',
      icon: 'docs',
    });
  }

  // ── Tests ──────────────────────────────────────────────────────────────
  const testCount = countTestFiles(structure);
  if (testCount > 0) {
    insights.push({
      id: 'tests-present',
      title: 'Automated Tests Present',
      detail: `${testCount} test ${testCount === 1 ? 'file' : 'files'} detected in the tree.`,
      severity: 'good',
      tooltip:
        'Counts files whose path contains test, spec, or __tests__. This measures presence, ' +
        'not coverage — no tests were executed.',
      icon: 'tests',
    });
  } else {
    insights.push({
      id: 'no-tests',
      title: 'No Tests Detected',
      detail: 'No files matching common test naming conventions.',
      severity: 'warn',
      tooltip:
        'No path contained test, spec, or __tests__. Tests may exist under a non-standard ' +
        'layout, so treat this as a hint rather than a verdict.',
      icon: 'tests',
    });
  }

  // ── Language spread ────────────────────────────────────────────────────
  if (techStack.length > 0) {
    const polyglot = techStack.length >= 5;
    insights.push({
      id: 'stack-spread',
      title: polyglot ? 'Polyglot Codebase' : 'Focused Stack',
      detail: `${techStack.length} stack ${techStack.length === 1 ? 'signal' : 'signals'}: ${techStack.slice(0, 3).join(', ')}${techStack.length > 3 ? '…' : ''}.`,
      severity: polyglot ? 'warn' : 'good',
      tooltip: polyglot
        ? 'Several languages or frameworks were detected. Polyglot repositories demand broader ' +
          'reviewer expertise and more toolchain setup.'
        : 'A small number of languages and frameworks were detected, which keeps the required ' +
          'context narrow.',
      icon: 'language',
    });
  }

  return insights.sort((a, b) => SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity]);
}

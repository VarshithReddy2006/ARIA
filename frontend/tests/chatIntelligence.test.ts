import { test, describe } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import {
  detectChatIntent,
  generateSuggestedPrompts,
  generateFollowUpPrompts,
  redactSecrets,
  resolvePronouns,
  parseInteractiveSegments,
  parseAnswerHierarchy,
  deduplicateSources,
  deriveFileRoleAndSignificance,
} from '../src/lib/chatIntelligence.ts';

const INTERACTIVE = 'src/components/interactive';
const CHAT_INTERFACE = join(INTERACTIVE, 'ChatInterface.tsx');

function read(path: string): string {
  return readFileSync(path, 'utf8');
}

describe('ARIA Chat & Engineering Copilot — 10/10 Verification', () => {
  // ── 1. Intent Detection Suite ─────────────────────────────────────────────
  test('1. Intent Detection classifies engineering queries accurately', () => {
    // Overview
    assert.equal(detectChatIntent('What does this repository do?').intent, 'OVERVIEW');
    assert.equal(detectChatIntent('What is this project?').intent, 'OVERVIEW');

    // Architecture
    assert.equal(detectChatIntent('What is the architecture and data flow?').intent, 'ARCHITECTURE');
    assert.equal(detectChatIntent('How is the system structured into layers?').intent, 'ARCHITECTURE');

    // File explanation
    assert.equal(detectChatIntent('Where is URL feature extraction implemented?').intent, 'FILE_EXPLANATION');
    assert.equal(detectChatIntent('What does app.py do?').intent, 'FILE_EXPLANATION');

    // Symbol explanation
    assert.equal(detectChatIntent('Where is normalize_prediction defined?').intent, 'SYMBOL_EXPLANATION');

    // Call graph
    assert.equal(detectChatIntent('What calls normalize_prediction?').intent, 'CALL_GRAPH');
    assert.equal(detectChatIntent('Who calls extract_features()?').intent, 'CALL_GRAPH');

    // Impact analysis
    assert.equal(detectChatIntent('If I delete utils.py what breaks?').intent, 'IMPACT_ANALYSIS');
    assert.equal(detectChatIntent('What would break if I change features.py?').intent, 'IMPACT_ANALYSIS');

    // Change planning
    assert.equal(detectChatIntent('How would I add authentication to this service?').intent, 'CHANGE_PLANNING');
    assert.equal(detectChatIntent('What files would I need to modify to implement rate limiting?').intent, 'CHANGE_PLANNING');

    // API
    assert.equal(detectChatIntent('What API endpoints exist in this codebase?').intent, 'API');
    assert.equal(detectChatIntent('Where is POST /predict route declared?').intent, 'API');

    // Dead code
    assert.equal(detectChatIntent('What code appears unused or unreferenced?').intent, 'DEAD_CODE');

    // Git history
    assert.equal(detectChatIntent('What has changed recently in git history?').intent, 'GIT_HISTORY');

    // Health
    assert.equal(detectChatIntent('Why is the repository health score low?').intent, 'HEALTH');

    // Reading path
    assert.equal(detectChatIntent('What should I read first to onboard?').intent, 'READING_PATH');
  });

  // ── 2. Dynamic Suggested Prompts ──────────────────────────────────────────
  test('2. Dynamic suggested prompts are tailored to repository signals', () => {
    const mlPrompts = generateSuggestedPrompts({
      repoName: 'VarshithReddy2006/PhishingWebsite_Detection',
      techStack: ['Python', 'Flask'],
      dependencies: ['torch', 'scikit-learn', 'flask', 'joblib'],
      entryPoints: ['app.py'],
      cyclesCount: 0,
      readingSteps: 5,
      healthScore: 88,
    });

    assert.ok(mlPrompts.some(p => p.includes('machine learning') || p.includes('API flow')), 'Must tailor for ML + Web API');
    assert.ok(mlPrompts.some(p => p.includes('entry point app.py')), 'Must reference real entry point app.py');
    assert.equal(mlPrompts.length, 4, 'Must return 4 curated prompts');

    const cyclePrompts = generateSuggestedPrompts({
      repoName: 'org/complex-monolith',
      techStack: ['TypeScript'],
      dependencies: ['express'],
      entryPoints: ['src/index.ts'],
      cyclesCount: 3,
      healthScore: 65,
    });
    assert.ok(cyclePrompts.some(p => p.includes('3 architectural cycles')), 'Must highlight detected cycles');
    assert.ok(cyclePrompts.some(p => p.includes('bottlenecks') || p.includes('warnings')), 'Must highlight health warnings when score < 80');
  });

  // ── 3. Contextual Follow-up Synthesis ─────────────────────────────────────
  test('3. Contextual follow-up questions derive from query intent and citations', () => {
    const followUps = generateFollowUpPrompts(
      'What calls Backend/app.py?',
      'CALL_GRAPH',
      'Backend/app.py is invoked by the WSGI runner.',
      ['Backend/app.py', 'Backend/features.py']
    );

    assert.ok(followUps.length >= 2, 'Must generate follow-ups');
    assert.ok(followUps.some(f => f.includes('chain') || f.includes('callers') || f.includes('Call Graph')), 'Must offer call graph drill-downs');

    const impactFollowUps = generateFollowUpPrompts(
      'What breaks if I change features.py?',
      'IMPACT_ANALYSIS',
      'Several classifier routines depend on features.py',
      ['Backend/features.py']
    );
    assert.ok(impactFollowUps.some(f => f.includes('implementation order') || f.includes('tests')), 'Must suggest testing or order follow-ups');
  });

  // ── 4. Secret & Sensitive Data Redaction ───────────────────────────────────
  test('4. Secret redaction neutralizes sensitive tokens before display', () => {
    const rawWithSecrets = `
      OpenAI: sk-abc12345678901234567890_testKey
      GitHub: ghp_1234567890abcdef1234567890abcdef12
      Auth: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.t-kJ...secret1234567890
      AWS: AKIAIOSFODNN7EXAMPLE
      Password: password: "SuperSecretPassword123"
    `;

    const clean = redactSecrets(rawWithSecrets);

    assert.ok(!clean.includes('sk-abc12345678901234567890_testKey'), 'OpenAI key must be redacted');
    assert.ok(clean.includes('[REDACTED_KEY]'), 'Must replace with safe label');
    assert.ok(!clean.includes('ghp_1234567890abcdef1234567890abcdef12'), 'GitHub token must be redacted');
    assert.ok(clean.includes('[REDACTED_GH_TOKEN]'), 'Must replace with safe label');
    assert.ok(!clean.includes('AKIAIOSFODNN7EXAMPLE'), 'AWS key must be redacted');
    assert.ok(clean.includes('[REDACTED_AWS_CREDENTIAL]'), 'Must replace with safe label');
  });

  // ── 5. Pronoun & Contextual Entity Memory ─────────────────────────────────
  test('5. Pronoun resolution preserves contextual subject in follow-up queries', () => {
    const query1 = resolvePronouns('What does it do?', 'Backend/app.py');
    assert.ok(query1.includes('referring to Backend/app.py'), 'Must clarify "it"');

    const query2 = resolvePronouns('Where are those functions used?', 'extract_features');
    assert.ok(query2.includes('referring to extract_features'), 'Must clarify "those functions"');

    const independentQuery = resolvePronouns('Explain the database schema', 'Backend/app.py');
    assert.equal(independentQuery, 'Explain the database schema', 'Must not mutate queries that do not use pronouns');
  });

  // ── 6. Interactive Tokenizer & Confidence States ───────────────────────────
  test('6. Interactive tokenizer extracts clickable file paths and confidence states', () => {
    const text = 'According to [VERIFIED] evidence in Backend/app.py, the function extract_features() initializes model inference.';
    const segments = parseInteractiveSegments(text);

    assert.ok(segments.some(s => s.type === 'confidence' && s.value === 'VERIFIED'), 'Must extract VERIFIED badge');
    assert.ok(segments.some(s => s.type === 'file' && s.value === 'Backend/app.py'), 'Must extract file token');
    assert.ok(segments.some(s => s.type === 'symbol' && s.value === 'extract_features'), 'Must extract symbol token');
  });

  // ── 7. Progressive Evidence & Answer Hierarchy ────────────────────────────
  test('7. Answer hierarchy parses key files, evidence items, and grounding status', () => {
    const sources = ['Backend/app.py', 'Backend/features.py', 'Backend/utils.py', 'Backend/app.py'];
    const deduped = deduplicateSources(sources);
    assert.equal(deduped.length, 3, 'Duplicate source references must be deduplicated');

    const hierarchy = parseAnswerHierarchy(
      'The prediction pipeline begins in Backend/app.py, extracts features via Backend/features.py, and executes classification in Backend/utils.py.',
      sources,
      95
    );

    assert.equal(hierarchy.groundingStatus, 'VERIFIED');
    assert.equal(hierarchy.keyFiles.length, 3);
    assert.equal(hierarchy.keyFiles[0].filePath, 'Backend/app.py');
    assert.ok(hierarchy.keyFiles[0].role.includes('Entry Point'));

    assert.equal(hierarchy.evidenceItems.length, 3);
    assert.equal(hierarchy.evidenceItems[0].level, 'VERIFIED');
    assert.ok(hierarchy.evidenceItems[0].whyItMatters.length > 10, 'Must provide why it matters explanation');

    // Partial grounding check
    const partialHierarchy = parseAnswerHierarchy('Some partial info', [], 45);
    assert.equal(partialHierarchy.groundingStatus, 'PARTIALLY GROUNDED');

    // Insufficient evidence check
    const unknownHierarchy = parseAnswerHierarchy('ARIA could not establish this from the indexed repository data.', ['src/unknown.ts'], 20);
    assert.equal(unknownHierarchy.groundingStatus, 'INSUFFICIENT EVIDENCE');
  });

  // ── 8. Semantic File Role & Significance Derivation ───────────────────────
  test('8. deriveFileRoleAndSignificance assigns appropriate roles without hallucinations', () => {
    const appRole = deriveFileRoleAndSignificance('Backend/app.py');
    assert.ok(appRole.role.includes('Entry Point'));
    assert.equal(appRole.level, 'VERIFIED');

    const featRole = deriveFileRoleAndSignificance('Backend/features.py');
    assert.ok(featRole.role.includes('Feature Engineering'));

    const utilRole = deriveFileRoleAndSignificance('Backend/utils.py');
    assert.ok(utilRole.role.includes('Utility'));

    const testRole = deriveFileRoleAndSignificance('tests/test_api.py');
    assert.ok(testRole.role.includes('Test Suite'));
  });

  // ── 9. ChatInterface Component Contract ───────────────────────────────────
  test('9. ChatInterface component implements Repository Engineering Copilot contracts', () => {
    assert.ok(existsSync(CHAT_INTERFACE), 'ChatInterface component must exist');
    const src = read(CHAT_INTERFACE);

    assert.ok(src.includes('Repository Engineering Copilot'), 'Header must reflect Copilot identity');
    assert.ok(src.includes('detectChatIntent'), 'Must integrate intent detection');
    assert.ok(src.includes('dynamicPrompts'), 'Must render dynamic suggested prompts');
    assert.ok(src.includes('followUps'), 'Must render follow-up prompt chips');
    assert.ok(src.includes('redactSecrets'), 'Must apply secret redaction');
    assert.ok(src.includes('handleCrossSurfaceAction'), 'Must support cross-surface action bar');
    assert.ok(src.includes('aria-chat-history:'), 'Must isolate conversation persistence per repository');
    assert.ok(src.includes('handleClearHistory'), 'Must support clearing conversation history');
    assert.ok(src.includes('KeyFilesSection'), 'Must render Key Files section');
    assert.ok(src.includes('ProgressiveEvidencePanel'), 'Must render Progressive Evidence Panel');
    assert.ok(src.includes('EvidenceBadge'), 'Must render Evidence Level Badges');
  });
});

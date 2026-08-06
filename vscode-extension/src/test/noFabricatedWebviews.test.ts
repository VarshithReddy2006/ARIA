import * as assert from 'assert';
import * as fs from 'fs';
import * as path from 'path';

describe('No Fabricated Webview Statistics (R-002)', () => {
  it('asserts no webview file in src/ contains hardcoded Entities or Relationships statistics', () => {
    const srcDir = path.resolve(__dirname, '../../src');

    function scanDirectory(dir: string): string[] {
      let results: string[] = [];
      const list = fs.readdirSync(dir);
      list.forEach((file) => {
        const fullPath = path.join(dir, file);
        const stat = fs.statSync(fullPath);
        if (stat && stat.isDirectory()) {
          results = results.concat(scanDirectory(fullPath));
        } else if (file.endsWith('.ts') || file.endsWith('.tsx') || file.endsWith('.html')) {
          results.push(fullPath);
        }
      });
      return results;
    }

    const files = fs.existsSync(srcDir) ? scanDirectory(srcDir) : [];
    const forbiddenPatterns = [
      /Entities:\s*\d+/i,
      /Relationships:\s*\d+/i,
      /Mastery Progress:\s*\d+%/i,
    ];

    const violations: string[] = [];

    files.forEach((filePath) => {
      const content = fs.readFileSync(filePath, 'utf-8');
      forbiddenPatterns.forEach((pattern) => {
        if (pattern.test(content)) {
          violations.push(`${path.basename(filePath)} matched forbidden pattern ${pattern.toString()}`);
        }
      });
    });

    assert.strictEqual(
      violations.length,
      0,
      `Fabricated repository statistics detected in webviews:\n${violations.join('\n')}`
    );
  });

  it('asserts fabricated view files (KnowledgeGraphView, LearningView, ArchitectureView, CopilotView) do not exist', () => {
    const viewsDir = path.resolve(__dirname, '../../src/views');
    assert.strictEqual(
      fs.existsSync(viewsDir),
      false,
      'src/views directory should be completely removed'
    );
  });
});

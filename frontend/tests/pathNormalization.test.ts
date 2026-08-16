import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { normalizeGraphPath } from '../src/lib/graphPathUtils.ts';

describe('normalizeGraphPath', () => {
  it('preserves clean repository-relative path', () => {
    assert.strictEqual(normalizeGraphPath('fastapi/routing.py'), 'fastapi/routing.py');
  });

  it('strips leading ./ from path', () => {
    assert.strictEqual(normalizeGraphPath('./fastapi/routing.py'), 'fastapi/routing.py');
  });

  it('strips leading / from path', () => {
    assert.strictEqual(normalizeGraphPath('/fastapi/routing.py'), 'fastapi/routing.py');
  });

  it('converts Windows backslashes to forward slashes', () => {
    assert.strictEqual(normalizeGraphPath('fastapi\\routing.py'), 'fastapi/routing.py');
    assert.strictEqual(normalizeGraphPath('fastapi\\dependencies\\utils.py'), 'fastapi/dependencies/utils.py');
  });

  it('strips repository slug prefix when provided', () => {
    assert.strictEqual(normalizeGraphPath('fastapi/fastapi/routing.py', 'fastapi'), 'fastapi/routing.py');
    assert.strictEqual(normalizeGraphPath('fastapi/fastapi/fastapi/routing.py', 'fastapi/fastapi'), 'fastapi/routing.py');
  });

  it('decodes URL-encoded characters in path', () => {
    assert.strictEqual(normalizeGraphPath('fastapi%2Frouting.py'), 'fastapi/routing.py');
    assert.strictEqual(normalizeGraphPath('docs%2Fen%2Fdocs%2Fjs%2Fcustom.js'), 'docs/en/docs/js/custom.js');
  });

  it('handles empty or blank paths gracefully', () => {
    assert.strictEqual(normalizeGraphPath(''), '');
    assert.strictEqual(normalizeGraphPath('   '), '');
  });

  it('strips trailing slashes from path', () => {
    assert.strictEqual(normalizeGraphPath('fastapi/routing.py/'), 'fastapi/routing.py');
    assert.strictEqual(normalizeGraphPath('fastapi/dependencies///'), 'fastapi/dependencies');
  });
});

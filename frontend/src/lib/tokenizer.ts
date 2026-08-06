/**
 * Token-based Safe Code Syntax Tokenizer.
 *
 * Tokenizes raw code text into structured Token objects.
 * Tokens are rendered directly as native React JSX elements.
 *
 * GUARANTEE: Zero string HTML manipulation, zero regex tag replacements,
 * and zero dangerouslySetInnerHTML. Completely immune to attribute corruption.
 */

export interface Token {
  type: 'keyword' | 'string' | 'comment' | 'number' | 'operator' | 'plain';
  text: string;
}

const KEYWORDS = new Set([
  'class',
  'def',
  'return',
  'const',
  'let',
  'var',
  'function',
  'import',
  'from',
  'export',
  'default',
  'interface',
  'extends',
  'as',
  'async',
  'await',
  'if',
  'else',
  'for',
  'while',
  'try',
  'catch',
  'finally',
  'raise',
  'throw',
  'new',
  'typeof',
  'instanceof',
  'public',
  'private',
  'protected',
  'readonly',
  'type',
  'void',
  'any',
  'string',
  'number',
  'boolean',
  'symbol',
  'self',
  'cls',
  'None',
  'True',
  'False',
  'null',
  'undefined',
  'true',
  'false',
  'in',
  'of',
  'and',
  'or',
  'not',
  'is',
]);

/**
 * High-performance, safe regex tokenizer for code syntax highlighting.
 * Returns an array of Token objects.
 */
export function tokenizeCode(codeText: string): Token[] {
  if (!codeText) return [];

  const tokens: Token[] = [];
  // Master regex matching comments, strings, numbers, words, operators, whitespace
  const masterRegex = /(\/\/[^\n]*|#[^\n]*|\/\*[\s\S]*?\*\/)|("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`)|(\b\d+(?:\.\d+)?\b)|(\b[a-zA-Z_]\w*\b)|([{}()\[\];,.:+\-*\/=<>!&|]+)|(\s+)|([^\s\w]+)/g;

  let match: RegExpExecArray | null;
  while ((match = masterRegex.exec(codeText)) !== null) {
    const [full, comment, str, num, word, op, whitespace, other] = match;

    if (comment) {
      tokens.push({ type: 'comment', text: comment });
    } else if (str) {
      tokens.push({ type: 'string', text: str });
    } else if (num) {
      tokens.push({ type: 'number', text: num });
    } else if (word) {
      if (KEYWORDS.has(word)) {
        tokens.push({ type: 'keyword', text: word });
      } else {
        tokens.push({ type: 'plain', text: word });
      }
    } else if (op) {
      tokens.push({ type: 'operator', text: op });
    } else if (whitespace) {
      tokens.push({ type: 'plain', text: whitespace });
    } else if (other) {
      tokens.push({ type: 'plain', text: other });
    }
  }

  return tokens;
}

/**
 * Technology / dependency classification.
 *
 * Presentation-only helper: groups the flat `tech_stack` and `dependencies`
 * arrays returned by the existing analysis API into scannable categories.
 * No API contract, data model, or business logic is affected.
 */

export type TechCategory =
  | 'language'
  | 'frontend'
  | 'backend'
  | 'database'
  | 'ai'
  | 'infrastructure'
  | 'deployment'
  | 'authentication'
  | 'storage'
  | 'cloud'
  | 'monitoring'
  | 'testing'
  | 'tooling'
  | 'other';

export type CategoryTone = 'primary' | 'info' | 'success' | 'warn' | 'danger' | 'neutral';

export interface CategoryMeta {
  id: TechCategory;
  label: string;
  /** Short explanation shown as a tooltip / secondary line */
  description: string;
  tone: CategoryTone;
}

/** Display order — most architecturally significant first. */
export const CATEGORY_ORDER: TechCategory[] = [
  'language',
  'backend',
  'frontend',
  'database',
  'ai',
  'authentication',
  'storage',
  'cloud',
  'infrastructure',
  'deployment',
  'monitoring',
  'testing',
  'tooling',
  'other',
];

export const CATEGORY_META: Record<TechCategory, CategoryMeta> = {
  language:       { id: 'language',       label: 'Languages',      description: 'Primary implementation languages',      tone: 'primary' },
  backend:        { id: 'backend',        label: 'Backend',        description: 'Server frameworks and runtime services', tone: 'success' },
  frontend:       { id: 'frontend',       label: 'Frontend',       description: 'UI frameworks, styling, and rendering',   tone: 'info' },
  database:       { id: 'database',       label: 'Database',       description: 'Persistence engines, ORMs, migrations',   tone: 'warn' },
  ai:             { id: 'ai',             label: 'AI & ML',        description: 'Models, embeddings, and vector stores',   tone: 'primary' },
  authentication: { id: 'authentication', label: 'Authentication', description: 'Identity, sessions, and cryptography',    tone: 'danger' },
  storage:        { id: 'storage',        label: 'Storage',        description: 'Object storage and media processing',     tone: 'info' },
  cloud:          { id: 'cloud',          label: 'Cloud',          description: 'Managed cloud platform SDKs',             tone: 'info' },
  infrastructure: { id: 'infrastructure', label: 'Infrastructure', description: 'Containers, orchestration, proxies',      tone: 'neutral' },
  deployment:     { id: 'deployment',     label: 'Deployment',     description: 'CI/CD pipelines and hosting targets',     tone: 'neutral' },
  monitoring:     { id: 'monitoring',     label: 'Monitoring',     description: 'Logging, tracing, and error reporting',   tone: 'warn' },
  testing:        { id: 'testing',        label: 'Testing',        description: 'Test runners and assertion libraries',    tone: 'success' },
  tooling:        { id: 'tooling',        label: 'Tooling',        description: 'Build, lint, format, and utilities',      tone: 'neutral' },
  other:          { id: 'other',          label: 'Other',          description: 'Uncategorised packages',                  tone: 'neutral' },
};

/**
 * Keyword table. Classification picks the *longest* matching keyword across all
 * categories, so ordering within this table does not affect correctness.
 */
const RULES: Array<[TechCategory, string[]]> = [
  ['language', [
    'python', 'typescript', 'javascript', 'golang', 'rust', 'java', 'kotlin',
    'swift', 'ruby', 'php', 'csharp', 'c#', 'c++', 'cpp', 'scala', 'elixir',
    'erlang', 'dart', 'lua', 'perl', 'haskell', 'clojure', 'zig', 'objective-c',
    'shell', 'bash', 'powershell', 'html', 'css',
  ]],
  ['backend', [
    'fastapi', 'starlette', 'uvicorn', 'gunicorn', 'hypercorn', 'django',
    'flask', 'bottle', 'tornado', 'sanic', 'litestar', 'express', 'koa',
    'nestjs', 'hono', 'fastify', 'hapi', 'spring', 'quarkus', 'micronaut',
    'rails', 'sinatra', 'laravel', 'symfony', 'gin', 'fiber', 'echo', 'chi',
    'actix', 'axum', 'rocket', 'celery', 'pydantic', 'graphql', 'apollo',
    'grpc', 'protobuf', 'socket.io', 'websockets', 'jinja2', 'mako',
    'marshmallow', 'strawberry', 'ariadne', 'trpc',
  ]],
  ['frontend', [
    'react', 'react-dom', 'vue', 'svelte', 'sveltekit', 'angular', 'astro',
    'next', 'nuxt', 'remix', 'solid-js', 'preact', 'qwik', 'lit',
    'tailwind', 'tailwindcss', 'sass', 'scss', 'less', 'bootstrap',
    'styled-components', 'emotion', 'chakra', 'mui', 'material-ui',
    'radix-ui', 'shadcn', 'headlessui', 'framer-motion', 'gsap',
    'redux', 'zustand', 'mobx', 'recoil', 'jotai', 'react-query',
    'react-router', 'react-markdown', 'reactflow', 'react-flow', 'cytoscape',
    'd3', 'three', 'chart.js', 'recharts', 'echarts', 'visx',
    'lucide', 'heroicons', 'react-icons', 'font-awesome', 'jquery',
    'clsx', 'class-variance-authority', 'tailwind-merge', 'prismjs', 'shiki',
  ]],
  ['database', [
    'postgres', 'postgresql', 'psycopg', 'asyncpg', 'mysql', 'mariadb',
    'sqlite', 'sqlite3', 'aiosqlite', 'mongodb', 'mongoose', 'pymongo',
    'motor', 'redis', 'memcached', 'sqlalchemy', 'alembic', 'prisma',
    'typeorm', 'drizzle', 'knex', 'sequelize', 'mikro-orm', 'peewee',
    'tortoise', 'databases', 'cassandra', 'scylla', 'dynamodb', 'neo4j',
    'clickhouse', 'duckdb', 'influxdb', 'couchdb', 'elasticsearch',
    'opensearch', 'cockroach', 'planetscale', 'libsql',
  ]],
  ['ai', [
    'openai', 'anthropic', 'gemini', 'google-generativeai', 'generativeai',
    'cohere', 'mistral', 'ollama', 'llama-index', 'llamaindex', 'langchain',
    'langgraph', 'langsmith', 'haystack', 'dspy', 'transformers',
    'sentence-transformers', 'huggingface', 'torch', 'pytorch', 'tensorflow',
    'keras', 'jax', 'flax', 'onnx', 'scikit-learn', 'sklearn', 'xgboost',
    'lightgbm', 'catboost', 'numpy', 'pandas', 'scipy', 'polars',
    'chromadb', 'chroma', 'pinecone', 'weaviate', 'qdrant', 'milvus', 'faiss',
    'lancedb', 'pgvector', 'tiktoken', 'spacy', 'nltk', 'gensim', 'litellm',
    'instructor', 'guardrails', 'deepseek', 'vllm', 'diffusers',
  ]],
  ['authentication', [
    'auth0', 'clerk', 'next-auth', 'authjs', 'passport', 'jwt', 'pyjwt',
    'jose', 'jsonwebtoken', 'oauth', 'oauthlib', 'authlib', 'keycloak',
    'okta', 'bcrypt', 'argon2', 'passlib', 'scrypt', 'cryptography',
    'pynacl', 'itsdangerous', 'casbin', 'lucia-auth', 'supertokens',
  ]],
  ['storage', [
    's3', 'boto3', 'botocore', 'minio', 'cloudinary', 'uploadthing',
    'multer', 'sharp', 'pillow', 'imagemagick', 'ffmpeg', 'fsspec',
    'smart-open', 'aiofiles',
  ]],
  ['cloud', [
    'aws', 'aws-sdk', 'azure', 'gcp', 'google-cloud', 'cloudflare',
    'digitalocean', 'linode', 'supabase', 'firebase', 'appwrite', 'planetsca',
    'upstash', 'neon',
  ]],
  ['infrastructure', [
    'docker', 'dockerfile', 'docker-compose', 'kubernetes', 'k8s', 'helm',
    'terraform', 'pulumi', 'ansible', 'nginx', 'apache', 'caddy', 'traefik',
    'envoy', 'consul', 'vault', 'vagrant', 'podman', 'rabbitmq', 'kafka',
    'nats', 'zookeeper', 'temporal',
  ]],
  ['deployment', [
    'vercel', 'netlify', 'heroku', 'railway', 'fly.io', 'render',
    'github-actions', 'gitlab-ci', 'circleci', 'jenkins', 'travis',
    'argocd', 'flux', 'serverless', 'sst', 'wrangler',
  ]],
  ['monitoring', [
    'sentry', 'datadog', 'prometheus', 'grafana', 'opentelemetry', 'otel',
    'newrelic', 'new-relic', 'elastic-apm', 'jaeger', 'statsd',
    'loguru', 'structlog', 'winston', 'pino', 'bunyan', 'logging',
    'psutil', 'py-spy',
  ]],
  ['testing', [
    'pytest', 'unittest', 'nose', 'hypothesis', 'tox', 'coverage',
    'jest', 'vitest', 'mocha', 'chai', 'jasmine', 'karma', 'ava', 'tap',
    'cypress', 'playwright', 'puppeteer', 'selenium', 'webdriver',
    'testing-library', 'enzyme', 'supertest', 'faker', 'factory-boy',
    'responses', 'respx', 'freezegun', 'moto',
  ]],
  ['tooling', [
    'eslint', 'prettier', 'stylelint', 'biome', 'oxlint',
    'ruff', 'mypy', 'pyright', 'black', 'isort', 'flake8', 'pylint',
    'bandit', 'pre-commit', 'babel', 'webpack', 'rollup', 'esbuild', 'swc',
    'parcel', 'turbo', 'turbopack', 'nx', 'lerna', 'vite', 'gulp', 'grunt',
    'poetry', 'pipenv', 'setuptools', 'hatch', 'flit', 'uv', 'pdm',
    'npm', 'yarn', 'pnpm', 'bun', 'husky', 'lint-staged', 'commitlint',
    'typescript-eslint', '@types', 'tsx', 'ts-node', 'tsup', 'tsc',
    'networkx', 'dagre', 'graphlib', 'lodash', 'ramda', 'underscore',
    'axios', 'requests', 'httpx', 'aiohttp', 'urllib3', 'got', 'node-fetch',
    'dotenv', 'python-dotenv', 'pyyaml', 'yaml', 'toml', 'orjson', 'ujson',
    'click', 'typer', 'argparse', 'rich', 'tqdm', 'colorama', 'tabulate',
    'zod', 'joi', 'yup', 'ajv', 'nanoid', 'uuid', 'date-fns', 'dayjs',
    'moment', 'luxon', 'arrow', 'pendulum', 'tenacity', 'backoff',
    'cachetools', 'diskcache', 'watchdog', 'chokidar', 'tree-sitter',
    'gitpython', 'pygithub', 'simple-git', 'octokit', 'postcss',
    'autoprefixer', 'jsdom', 'cheerio', 'beautifulsoup', 'lxml',
    'markdown', 'remark', 'rehype', 'unified', 'mdx',
  ]],
];

/** Strips version specifiers, extras, scopes, and normalises separators. */
export function normalizeTechName(raw: string): string {
  let name = (raw ?? '').toString().trim().toLowerCase();

  // Drop everything after a version / comparison operator
  name = name.split(/[<>=!~;[(]/)[0];
  // Drop npm version ranges like "react@^18.2.0"
  name = name.replace(/@[\d^~*>=<].*$/, '');
  // Keep the "@types" signal but flatten other scopes: "@astrojs/react" -> "astrojs/react"
  if (!name.startsWith('@types')) name = name.replace(/^@/, '');
  name = name.replace(/_/g, '-').trim();

  return name;
}

/**
 * Classifies a single technology or package name.
 * Uses longest-keyword-wins so specific names beat generic substrings
 * (e.g. "google-generativeai" -> ai, not "google-cloud" -> cloud).
 */
export function classifyTech(raw: string): TechCategory {
  const name = normalizeTechName(raw);
  if (!name) return 'other';

  let bestCategory: TechCategory = 'other';
  let bestWeight = 0;

  for (const [category, keywords] of RULES) {
    for (const keyword of keywords) {
      if (!name.includes(keyword)) continue;
      // Exact matches always beat partial matches.
      const weight = name === keyword ? keyword.length + 1000 : keyword.length;
      if (weight > bestWeight) {
        bestWeight = weight;
        bestCategory = category;
      }
    }
  }

  return bestCategory;
}

export interface TechGroup {
  meta: CategoryMeta;
  items: string[];
}

/**
 * Groups a flat list into ordered, non-empty categories.
 * Items are de-duplicated (case-insensitively) and sorted alphabetically.
 */
export function groupTech(items: string[]): TechGroup[] {
  const buckets = new Map<TechCategory, string[]>();
  const seen = new Set<string>();

  for (const item of items ?? []) {
    const label = (item ?? '').toString().trim();
    if (!label) continue;

    const dedupeKey = label.toLowerCase();
    if (seen.has(dedupeKey)) continue;
    seen.add(dedupeKey);

    const category = classifyTech(label);
    const bucket = buckets.get(category);
    if (bucket) bucket.push(label);
    else buckets.set(category, [label]);
  }

  return CATEGORY_ORDER.filter((category) => buckets.has(category)).map((category) => ({
    meta: CATEGORY_META[category],
    items: (buckets.get(category) ?? []).sort((a, b) =>
      a.localeCompare(b, undefined, { sensitivity: 'base' }),
    ),
  }));
}

/** Tailwind class fragments for a category tone — chip styling. */
export const TONE_CHIP: Record<CategoryTone, string> = {
  primary: 'border-primary/30 bg-primary/5 text-primary',
  info:    'border-info/30 bg-info/5 text-info',
  success: 'border-success/30 bg-success/5 text-success',
  warn:    'border-warn/30 bg-warn/5 text-warn',
  danger:  'border-danger/30 bg-danger/5 text-danger',
  neutral: 'border-border bg-surface-2 text-text-muted',
};

/** Tailwind class fragments for a category tone — indicator dot. */
export const TONE_DOT: Record<CategoryTone, string> = {
  primary: 'bg-primary',
  info:    'bg-info',
  success: 'bg-success',
  warn:    'bg-warn',
  danger:  'bg-danger',
  neutral: 'bg-text-subtle',
};

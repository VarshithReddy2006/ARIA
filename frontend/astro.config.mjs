import { defineConfig } from 'astro/config';
import react from '@astrojs/react';
import tailwind from '@astrojs/tailwind';
import vercel from '@astrojs/vercel';
import node from '@astrojs/node';

/*
 * Deployment target.
 *
 * `output: 'server'` means every page is rendered by an adapter at request time,
 * so the adapter is not optional — without a matching one the build produces no
 * servable pages. Two targets are supported:
 *
 *   vercel (default) — Serverless Functions, used by the hosted deployment.
 *   node             — standalone Node server, used by the Docker image
 *                      (Dockerfile.frontend) so ARIA is self-hostable via
 *                      `docker compose up`.
 *
 * Selected with ARIA_DEPLOY_TARGET so the hosted Vercel build keeps its existing
 * behaviour with no configuration change.
 */
const deployTarget = process.env.ARIA_DEPLOY_TARGET ?? 'vercel';

if (!['vercel', 'node'].includes(deployTarget)) {
  throw new Error(
    `ARIA_DEPLOY_TARGET must be 'vercel' or 'node', received '${deployTarget}'.`,
  );
}

export default defineConfig({
  output: 'server',
  adapter:
    deployTarget === 'node'
      ? node({ mode: 'standalone' })
      : vercel({
          // Uses Node.js 20.x runtime for Vercel Serverless Functions
        }),
  integrations: [
    react(),
    tailwind({
      applyBaseStyles: false,
    }),
  ],
  vite: {
    server: {
      watch: {
        ignored: ['**/.vercel/**', '**/dist/**', '**/.astro/**'],
      },
    },
    optimizeDeps: {
      include: ['reactflow', 'dagre', 'react-markdown', 'remark-gfm', 'lucide-react', 'framer-motion'],
    },
    build: {
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (id.includes('node_modules')) {
              if (id.includes('reactflow') || id.includes('@reactflow') || id.includes('dagre')) {
                return 'vendor-graphs';
              }
              if (id.includes('react-markdown') || id.includes('remark') || id.includes('micromark') || id.includes('unified') || id.includes('mdast') || id.includes('unist')) {
                return 'vendor-markdown';
              }
              if (id.includes('lucide-react')) {
                return 'vendor-icons';
              }
              if (id.includes('framer-motion')) {
                return 'vendor-motion';
              }
            }
          },
        },
      },
    },
  },
});

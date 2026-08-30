import { defineConfig } from 'astro/config';
import react from '@astrojs/react';
import tailwind from '@astrojs/tailwind';
import vercel from '@astrojs/vercel';

export default defineConfig({
  output: 'server',
  adapter: vercel({
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
